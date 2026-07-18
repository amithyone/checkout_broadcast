<?php

namespace App\Http\Controllers\Api;

use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\RateLimiter;
use Illuminate\Support\Str;

/**
 * Checkout Broadcast verify API for check-outpay.com
 * Port of checkout_broadcast/bank_api/server.py — drop into checkout Laravel app.
 */
class BroadcastVerifyController extends Controller
{
    private const MAX_AGE_MS = 600_000;

    public function health(): JsonResponse
    {
        $terminals = DB::table('broadcast_terminals')->where('active', 1)->count();
        return response()->json([
            'ok' => true,
            'terminals' => $terminals,
        ]);
    }

    public function verifyBroadcast(Request $request): JsonResponse
    {
        $key = 'broadcast-verify:' . $request->ip();
        if (RateLimiter::tooManyAttempts($key, (int) config('broadcast.rate_limit_verify', 120))) {
            return response()->json([
                'valid' => false,
                'error' => 'Rate limit exceeded',
            ], 429);
        }
        RateLimiter::hit($key, 60);

        $packet = $request->all();
        $payload = $packet['payload'] ?? null;
        if (! is_array($payload)) {
            return response()->json(['valid' => false, 'error' => 'Invalid packet'], 422);
        }

        $terminalId = $payload['terminal_id'] ?? '';
        $terminal = DB::table('broadcast_terminals')
            ->where('terminal_id', $terminalId)
            ->where('active', 1)
            ->first();

        if (! $terminal) {
            return response()->json(['valid' => false, 'error' => 'Unknown terminal_id']);
        }

        $timestampMs = (int) ($payload['timestamp_ms'] ?? 0);
        if (abs((int) (microtime(true) * 1000) - $timestampMs) > self::MAX_AGE_MS) {
            return response()->json(['valid' => false, 'error' => 'Timestamp outside allowed window']);
        }

        $session = $payload['session_uuid_v4'] ?? '';
        if ($session === '' || ! $this->consumeSession($session, $terminalId)) {
            return response()->json(['valid' => false, 'error' => 'Session UUID already used (replay)']);
        }

        $display = $payload['account_info_public_display'] ?? [];
        if (($display['bank_name_hash'] ?? '') !== $terminal->bank_name_hash) {
            return response()->json(['valid' => false, 'error' => 'Bank name hash mismatch']);
        }

        if (! $this->verifySignature($payload, $terminal->signing_key, $packet['signature'] ?? '')) {
            return response()->json(['valid' => false, 'error' => 'Invalid signature']);
        }

        $amount = (int) ($payload['transaction_details']['total_amount_ngn'] ?? 0);

        return response()->json([
            'valid' => true,
            'merchant_name' => $terminal->merchant_name,
            'amount_ngn' => $amount,
            'masked_account_suffix' => $terminal->masked_account_suffix,
            'session_uuid' => $session,
            'terminal_id' => $terminalId,
            'recipient_account' => $terminal->account_number,
            'recipient_bank_code' => $terminal->recipient_bank_code,
        ]);
    }

    public function registerTerminal(Request $request): JsonResponse
    {
        $adminKey = $request->header('X-Admin-Key');
        if ($adminKey !== config('broadcast.admin_key')) {
            return response()->json(['error' => 'Unauthorized'], 401);
        }

        $data = $request->validate([
            'terminal_id' => 'required|string|max:64',
            'signing_key' => 'required|string|min:16|max:256',
            'merchant_name' => 'required|string|max:128',
            'bank_name' => 'required|string|max:64',
            'masked_account_suffix' => 'required|regex:/^\*{3}[0-9]{4}$/',
            'account_number' => 'nullable|digits:10',
            'recipient_bank_code' => 'nullable|string|max:6',
        ]);

        $bankNameHash = 'sha256:' . hash('sha256', strtolower(trim($data['bank_name'])));

        DB::table('broadcast_terminals')->updateOrInsert(
            ['terminal_id' => $data['terminal_id']],
            [
                'signing_key' => $data['signing_key'],
                'merchant_name' => $data['merchant_name'],
                'bank_name' => $data['bank_name'],
                'bank_name_hash' => $bankNameHash,
                'masked_account_suffix' => $data['masked_account_suffix'],
                'account_number' => $data['account_number'] ?? null,
                'recipient_bank_code' => $data['recipient_bank_code'] ?? null,
                'active' => 1,
                'updated_at' => now(),
                'created_at' => now(),
            ]
        );

        return response()->json(['ok' => true, 'terminal_id' => $data['terminal_id']]);
    }

    private function consumeSession(string $sessionUuid, string $terminalId): bool
    {
        if (! Str::isUuid($sessionUuid)) {
            return false;
        }
        $exists = DB::table('broadcast_used_sessions')->where('session_uuid', $sessionUuid)->exists();
        if ($exists) {
            return false;
        }
        DB::table('broadcast_used_sessions')->insert([
            'session_uuid' => $sessionUuid,
            'terminal_id' => $terminalId,
            'used_at' => (int) (microtime(true) * 1000),
        ]);

        return true;
    }

    /** Canonical JSON HMAC-SHA256 — must match spec/signing-rules.md */
    private function verifySignature(array $payload, string $signingKey, string $signatureB64): bool
    {
        if ($signatureB64 === '') {
            return false;
        }
        $canonical = json_encode($this->sortKeysRecursive($payload), JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        $expected = base64_encode(hash_hmac('sha256', $canonical, $signingKey, true));

        return hash_equals($expected, $signatureB64);
    }

    private function sortKeysRecursive(array $data): array
    {
        ksort($data);
        foreach ($data as $key => $value) {
            if (is_array($value)) {
                $data[$key] = $this->sortKeysRecursive($value);
            }
        }

        return $data;
    }
}
