# Checkout Broadcast — Verify API contract

All wallet/banking apps POST signed BLE packets to **`POST /verify-broadcast`** on the bank or payment platform backend.

**CheckoutPay production:** `https://check-outpay.com/api/v1/broadcast/verify-broadcast`

## Request

No auth header. Content-Type: `application/json`.

```json
{
  "payload": {
    "protocol_version": 1,
    "timestamp_ms": 1738123456789,
    "session_uuid_v4": "550e8400-e29b-41d4-a716-446655440000",
    "terminal_id": "CP-1RK8Z",
    "transaction_details": {
      "currency_code": "NGN",
      "total_amount_ngn": 5000,
      "item_count": 3
    },
    "account_info_public_display": {
      "bank_name_hash": "sha256:…",
      "masked_account_suffix": "***1234"
    }
  },
  "signature_alg": "ed25519",
  "signature": "<base64-or-hex>"
}
```

### Required payload fields

| Field | Type | Notes |
|-------|------|-------|
| `protocol_version` | number | `1` (CheckoutPay) or `2.0` (open SDK) — both accepted |
| `timestamp_ms` | integer | **Required.** Epoch ms at POS sign time. SDK sets `Date.now()` / `time.time()*1000` |
| `session_uuid_v4` | UUID string | Fresh per checkout; replay-protected |
| `terminal_id` | string | Registered terminal ID |
| `transaction_details.total_amount_ngn` | integer | Amount in Naira (whole naira) |
| `transaction_details.item_count` | integer | Optional but recommended |
| `account_info_public_display.bank_name_hash` | string | Must match terminal registry |
| `account_info_public_display.masked_account_suffix` | string | e.g. `***1234` |

### Signature algorithms

| `signature_alg` | Who uses it | Server verifies with |
|-----------------|-------------|----------------------|
| `HMAC-SHA256` | Open SDK v2.0 POS | Terminal `signing_key` (shared secret) |
| `ed25519` / `ED25519` | CheckoutPay Pay at shop | Terminal `public_key` only |

## Success response (HTTP 200)

```json
{
  "valid": true,
  "merchant_name": "MIDAS AGRO",
  "amount_ngn": 5000,
  "masked_account_suffix": "***1234",
  "session_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "terminal_id": "CP-1RK8Z",
  "recipient_account": "0123456789",
  "recipient_bank_code": "058"
}
```

Use `recipient_account` and `recipient_bank_code` from the **server response** (registry), not from the BLE payload alone.

## Failure response (HTTP 200, `valid: false`)

```json
{
  "valid": false,
  "error": "Missing timestamp_ms in payload"
}
```

### Standard error strings

| `error` | Meaning | Fix |
|---------|---------|-----|
| `Missing timestamp_ms in payload` | `payload.timestamp_ms` absent or zero | POS must set before signing; app must not strip field |
| `Timestamp outside allowed window` | Packet older than ~10 minutes | Cashier sends a fresh payment |
| `Invalid signature` | Wrong key or tampered payload | Sync signing key / use full BLE JSON |
| `Bank name hash mismatch` | POS bank name ≠ registered bank | Match dashboard settlement bank |
| `Unknown terminal_id` | Terminal not registered | Register terminal / enable Pay at shop |
| `Session UUID already used (replay)` | Same session verified twice (legacy servers) | Fresh session from POS |
| `Pay at shop is not active for this merchant` | CheckoutPay only | Merchant enables in dashboard |
| `Rate limit exceeded` | Too many verify calls | Retry after `retry_after_seconds` |

## Receiver SDK checklist

1. Read signed JSON from BLE GATT characteristic unchanged.
2. Reject locally if `timestamp_ms` is missing (`parseTimestampMs` / `parse_timestamp_ms`).
3. POST the **full envelope** (`payload`, `signature_alg`, `signature`) to `/verify-broadcast`.
4. On success, pre-fill transfer UI from server response fields.

## Sender SDK checklist

1. Build payload with `timestamp_ms` set to **current time**.
2. Sign canonical JSON of `payload` only.
3. Broadcast `{ payload, signature_alg, signature }` over BLE.
4. Generate a **new** `session_uuid_v4` per checkout attempt.

Reference implementations: [`bank_api/server.py`](../bank_api/server.py), CheckoutPay [`BROADCAST_VERIFY_API.md`](../../checkout/BROADCAST_VERIFY_API.md).
