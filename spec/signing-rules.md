# Checkout Broadcast — Signing Rules (v2.0)

All SDKs MUST produce identical signatures for the same payload and key.

## Canonical JSON

1. Serialize only the `payload` object (not the signed envelope).
2. Use UTF-8 encoding.
3. Sort object keys recursively in lexicographic (ASCII) order.
4. No whitespace between tokens (`separators=(",", ":")` in Python, no pretty-print).
5. Numbers: JSON number format (no trailing decimals on integers).

## HMAC-SHA256

```
message = canonical_json(payload)
signature = Base64(HMAC-SHA256(key=signing_key_utf8, message=message))
```

- `signing_key` is the terminal secret registered with the bank (UTF-8 string).
- Output `signature` is standard Base64 (with padding).
- Envelope: `"signature_alg": "HMAC-SHA256"`.

## Ed25519 (CheckoutPay / CheckoutNow Pay at shop)

Used when terminals are provisioned from the CheckoutPay merchant dashboard (`signature_alg: ed25519`).

```
message = canonical_json(payload)
signature = Base64(Ed25519_sign(message, terminal_private_key))
```

- POS stores the **private key** (`signing_key`, base64 — 32-byte seed or 64-byte libsodium secret key).
- Bank server stores only the **public key** (`public_key`, base64, 32 bytes).
- Envelope: `"signature_alg": "ed25519"` (case-insensitive).
- Canonical JSON rules are **identical** to HMAC-SHA256.

## Required payload field: timestamp_ms

Every signed payload **must** include:

```json
"timestamp_ms": 1738123456789
```

- Milliseconds since Unix epoch.
- Set at packet creation time on the POS (`Date.now()`, `time.time()*1000`).
- Wallet apps must POST the signed packet **unchanged** — never add or omit `timestamp_ms` after signing.
- Banks reject missing values with `Missing timestamp_ms in payload`.
- Reject if outside ±10 minutes of server time.

## Signed Envelope

```json
{
  "payload": { ... },
  "signature_alg": "HMAC-SHA256",
  "signature": "<base64>"
}
```

`signature_alg` may also be `"ed25519"` for CheckoutPay-provisioned terminals. See [signing-rules.md](signing-rules.md).

## Validation Window

- Reject if `abs(now_ms - payload.timestamp_ms) > 600_000` (10 minutes).
- Reject if `session_uuid_v4` was already consumed for that `terminal_id`.

## Bank Name Hash

```
bank_name_hash = "sha256:" + hex(SHA256(normalized_bank_name_utf8))
```

Normalize: trim whitespace, lowercase.
