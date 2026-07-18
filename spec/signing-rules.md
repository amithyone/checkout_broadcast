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

## Signed Envelope

```json
{
  "payload": { ... },
  "signature_alg": "HMAC-SHA256",
  "signature": "<base64>"
}
```

## Validation Window

- Reject if `abs(now_ms - payload.timestamp_ms) > 600_000` (10 minutes).
- Reject if `session_uuid_v4` was already consumed for that `terminal_id`.

## Bank Name Hash

```
bank_name_hash = "sha256:" + hex(SHA256(normalized_bank_name_utf8))
```

Normalize: trim whitespace, lowercase.
