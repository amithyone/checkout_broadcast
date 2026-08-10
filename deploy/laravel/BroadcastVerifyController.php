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
 *
 * Accepts:
 * - Full envelope { payload, signature_alg, signature }
 * - Compact BLE wire { p, alg, sig } (expanded before Ed25519 / HMAC verify)
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

        $packet = $this->normalizeBlePacket($request->all());
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

        $amount = (int) ($payload['transaction_details']['total_amount_ngn'] ?? 0);
        $kindRaw = strtolower(trim((string) ($payload['session_kind'] ?? '')));
        $isPresence = $kindRaw === 'presence' || $kindRaw === 'idle' || $kindRaw === 'beacon' || $amount <= 0;
        $sessionKind = $isPresence ? 'presence' : 'pos_checkout';

        $session = $payload['session_uuid_v4'] ?? '';
        // Presence / idle beacons may reuse the same UUID while the till is idle —
        // do not burn replay protection until a checkout amount is verified.
        if ($session === '') {
            return response()->json(['valid' => false, 'error' => 'Invalid session']);
        }
        if (! $isPresence && ! $this->consumeSession($session, $terminalId)) {
            return response()->json(['valid' => false, 'error' => 'Session UUID already used (replay)']);
        }
        if ($isPresence && ! Str::isUuid($session)) {
            return response()->json(['valid' => false, 'error' => 'Invalid session']);
        }

        $display = $payload['account_info_public_display'] ?? [];
        if (! $this->bankDisplayMatches($terminal->bank_name, $terminal->bank_name_hash, $display, $terminal->masked_account_suffix ?? '')) {
            return response()->json(['valid' => false, 'error' => 'Bank name mismatch']);
        }

        $alg = strtolower(trim((string) ($packet['signature_alg'] ?? 'HMAC-SHA256')));
        if (! $this->verifySignature($payload, $terminal->signing_key, $packet['signature'] ?? '', $alg)) {
            return response()->json(['valid' => false, 'error' => 'Invalid signature']);
        }

        return response()->json([
            'valid' => true,
            'merchant_name' => $terminal->merchant_name,
            'amount_ngn' => $isPresence ? 0 : $amount,
            'session_kind' => $sessionKind,
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

    /**
     * Accept full envelope or minimal BLE wire { p, alg, sig }.
     * Wire must be expanded before Ed25519 verify — signature covers canonical payload keys.
     */
    private function normalizeBlePacket(array $raw): array
    {
        if (isset($raw['payload']) && is_array($raw['payload'])) {
            return [
                'payload' => $raw['payload'],
                'signature_alg' => $raw['signature_alg'] ?? $raw['alg'] ?? 'HMAC-SHA256',
                'signature' => $raw['signature'] ?? $raw['sig'] ?? '',
            ];
        }

        $p = $raw['p'] ?? null;
        if (! is_array($p)) {
            return $raw;
        }

        $sid = trim((string) ($p['sid'] ?? ''));
        $tid = trim((string) ($p['tid'] ?? ''));
        $sig = trim((string) ($raw['sig'] ?? $raw['signature'] ?? ''));
        if ($sid === '' || $tid === '' || $sig === '') {
            return $raw;
        }

        $protocolVersion = $p['v'] ?? 2.1;
        if (is_string($protocolVersion) && is_numeric($protocolVersion)) {
            $protocolVersion = (float) $protocolVersion;
        }

        $amtPresent = array_key_exists('amt', $p);
        $amt = $amtPresent ? (int) $p['amt'] : 0;
        $kind = strtolower(trim((string) ($p['k'] ?? '')));
        // Only put session_kind on the payload when POS sent `k` (must match signed bytes).
        $payload = [
            'protocol_version' => $protocolVersion,
            'timestamp_ms' => (int) ($p['ts'] ?? 0),
            'session_uuid_v4' => $sid,
            'terminal_id' => $tid,
            'transaction_details' => [
                'total_amount_ngn' => $amt,
            ],
        ];
        if ($kind === 'presence' || $kind === 'idle' || $kind === 'beacon') {
            $payload['session_kind'] = 'presence';
        } elseif ($kind === 'pos_checkout' || $kind === 'checkout') {
            $payload['session_kind'] = 'pos_checkout';
        }

        $msk = trim((string) ($p['msk'] ?? ''));
        if ($msk !== '') {
            $payload['account_info_public_display'] = [
                'masked_account_suffix' => $msk,
            ];
        }

        return [
            'payload' => $payload,
            'signature_alg' => $raw['alg'] ?? $raw['signature_alg'] ?? 'ed25519',
            'signature' => $sig,
        ];
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

    /**
     * Plain bank_name / bank_name_hash, or wire packets that only send masked_account_suffix.
     * Merchant + bank settlement come from terminal registry after verify.
     */
    private function bankDisplayMatches(
        string $terminalBankName,
        string $terminalBankHash,
        array $display,
        string $terminalMaskedSuffix = ''
    ): bool {
        $packetName = trim((string) ($display['bank_name'] ?? ''));
        if ($packetName !== '') {
            return $this->normalizeBankName($packetName) === $this->normalizeBankName($terminalBankName);
        }
        $packetHash = trim((string) ($display['bank_name_hash'] ?? ''));
        if ($packetHash !== '') {
            return hash_equals($terminalBankHash, $packetHash);
        }

        // Wire v2.2: only msk (or empty display) — accept if msk matches terminal, or no msk sent.
        $packetMsk = trim((string) ($display['masked_account_suffix'] ?? ''));
        if ($packetMsk === '') {
            return true;
        }
        if ($terminalMaskedSuffix === '') {
            return true;
        }

        return hash_equals($terminalMaskedSuffix, $packetMsk);
    }

    private function normalizeBankName(string $bankName): string
    {
        return strtolower(trim($bankName));
    }

    /**
     * Verify payload signature.
     * - HMAC-SHA256: signing_key is shared secret (UTF-8)
     * - ed25519: signing_key is base64 (or hex) public key; signature is base64
     */
    private function verifySignature(array $payload, string $signingKey, string $signatureB64, string $alg): bool
    {
        if ($signatureB64 === '') {
            return false;
        }

        $canonical = json_encode($this->sortKeysRecursive($payload), JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        if ($canonical === false) {
            return false;
        }

        if ($alg === 'ed25519' || $alg === 'eddsa') {
            return $this->verifyEd25519($canonical, $signingKey, $signatureB64);
        }

        // Default: HMAC-SHA256 (legacy / reference bank_api)
        $expected = base64_encode(hash_hmac('sha256', $canonical, $signingKey, true));

        return hash_equals($expected, $signatureB64);
    }

    private function verifyEd25519(string $message, string $publicKeyRaw, string $signatureB64): bool
    {
        if (! function_exists('sodium_crypto_sign_verify_detached')) {
            return false;
        }

        $signature = base64_decode($signatureB64, true);
        if ($signature === false || strlen($signature) !== SODIUM_CRYPTO_SIGN_BYTES) {
            return false;
        }

        $publicKey = $this->decodePublicKey($publicKeyRaw);
        if ($publicKey === null || strlen($publicKey) !== SODIUM_CRYPTO_SIGN_PUBLICKEYBYTES) {
            return false;
        }

        try {
            return sodium_crypto_sign_verify_detached($signature, $message, $publicKey);
        } catch (\Throwable) {
            return false;
        }
    }

    private function decodePublicKey(string $raw): ?string
    {
        $trimmed = trim($raw);
        if ($trimmed === '') {
            return null;
        }
        // strip common prefixes
        if (str_starts_with($trimmed, 'ed25519:')) {
            $trimmed = substr($trimmed, 8);
        }
        $b64 = base64_decode($trimmed, true);
        if ($b64 !== false && strlen($b64) === SODIUM_CRYPTO_SIGN_PUBLICKEYBYTES) {
            return $b64;
        }
        if (ctype_xdigit($trimmed) && strlen($trimmed) === SODIUM_CRYPTO_SIGN_PUBLICKEYBYTES * 2) {
            $hex = hex2bin($trimmed);

            return $hex === false ? null : $hex;
        }

        return null;
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
