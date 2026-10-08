# Checkout Broadcast — Verify API contract

Wallet/banking apps (and bank backends) verify signed POS broadcasts with:

**`POST /verify-broadcast`**

**CheckoutPay production:** `https://check-outpay.com/api/v1/broadcast/verify-broadcast`

BLE transport and compact wire: [ble-transport.md](ble-transport.md).

---

## Working path (CheckoutNow / Cheko)

What production POS and CheckoutNow actually do:

1. POS advertises GATT service `cbbc0001-…` / char `cbbc0002-…` with compact JSON `{ p, alg, sig }` (Ed25519; `amt` in **kobo**).
2. Wallet reads GATT → **`normalizeBleReadForVerify` / expand** → canonical envelope.
3. Wallet POSTs expanded body to `/verify-broadcast` (CheckoutPay Laravel also expands if you POST compact wire).
4. Use registry `recipient_account` / `recipient_bank_code` from the response.
5. Take the amount from the **signed packet**: wire `amt` is kobo, so transfer amount = `amt ÷ 100`. Presence (`0` / omitted / `session_kind: presence`) → let the customer enter amount.

Do **not** assume “POST the GATT JSON byte-for-byte” unless your backend expands compact wire (CheckoutPay does).

---

## Request (expanded envelope)

Content-Type: `application/json`. The body is self-authenticating (signed by the till), so the reference server needs no auth header. Wallets may send their usual customer session headers — CheckoutNow does, and your bank can require them for rate limiting and audit.

```json
{
  "payload": {
    "protocol_version": 2.1,
    "timestamp_ms": 1738123456789,
    "session_uuid_v4": "550e8400-e29b-41d4-a716-446655440000",
    "terminal_id": "CP-1RK8Z",
    "session_kind": "pos_checkout",
    "transaction_details": {
      "total_amount_ngn": 649
    },
    "account_info_public_display": {
      "masked_account_suffix": "***4863"
    }
  },
  "signature_alg": "ed25519",
  "signature": "<base64>"
}
```

Compact wire (what is often on BLE) — expand before verify if the server does not:

```json
{
  "p": { "v": 2.1, "sid": "…", "tid": "CP-1RK8Z", "ts": 1738123456789, "amt": 649, "msk": "***4863" },
  "alg": "ed25519",
  "sig": "…"
}
```

### Payload fields

| Field | Type | Notes |
|-------|------|-------|
| `protocol_version` | number | Production wire uses `2.1`; `1` / `2` / `2.0` also seen |
| `timestamp_ms` | integer | **Required.** Epoch ms at POS sign time |
| `session_uuid_v4` | UUID string | Per checkout; presence may reuse while idle |
| `terminal_id` | string | Registered terminal ID |
| `session_kind` | string | Optional: `presence` \| `pos_checkout` |
| `transaction_details.total_amount_ngn` | integer | Wire/Cheko: **kobo**. `0` = presence. Legacy HMAC demos may use whole Naira |
| `transaction_details.currency_code` / `item_count` | — | Optional; **do not invent** on expand if POS did not sign them |
| `account_info_public_display.masked_account_suffix` | string | Often the only display field on wire (`msk`) |
| `account_info_public_display.bank_name` / `bank_name_hash` | string | Optional on wire; server may match msk against registry |

### Signature algorithms

| `signature_alg` | Who uses it | Server verifies with |
|-----------------|-------------|----------------------|
| `ed25519` / `ED25519` | **CheckoutPay / Cheko production** | Terminal `public_key` |
| `HMAC-SHA256` | Open SDK demos / older POS | Terminal `signing_key` (shared secret) |

---

## Success response (HTTP 200)

```json
{
  "valid": true,
  "merchant_name": "MIDAS AGRO",
  "amount_ngn": 649,
  "session_kind": "pos_checkout",
  "masked_account_suffix": "***4863",
  "session_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "terminal_id": "CP-1RK8Z",
  "recipient_account": "0123456789",
  "recipient_bank_code": "058"
}
```

| Field | Notes |
|-------|--------|
| `amount_ngn` | Echo of the signed amount (kobo for wire/Cheko). Receivers use the packet amount (`amt ÷ 100`) |
| `session_kind` | `presence` or `pos_checkout` when server supports it |
| `session_status` | Optional: `open` \| `paid` \| `cancelled` |
| `merchant_name` | From **registry**. Wallet must show this; customer confirms the shop. Not on BLE. An enrolled thief still verifies — the name is *their* business, not the store the payer is in. |
| `recipient_*` | From **registry** — never trust BLE alone for payout account |

Receivers should also accept the fields wrapped in `{ "data": { … } }` and these aliases: `merchantName`, `session_uuid_v4`, `account_number` (for `recipient_account`), `bank_code` (for `recipient_bank_code`). If `merchant_name` is missing, show "Shop".

---

## Failure response

Most failures are **HTTP 200 with `valid: false`**; some are 4xx (`422` invalid packet, `429` rate limit).

```json
{
  "valid": false,
  "error": "Unknown terminal_id"
}
```

Receivers must treat **both** as failure: a non-2xx status, or `valid === false` (at the top level or inside `data`). Show `error` (or `message`) to the user. Closed sessions return `{ "valid": false, "error": "Session already paid", "session_status": "paid" }` — hide that till from the picker.

### Standard error strings

| `error` | Meaning | Fix |
|---------|---------|-----|
| `Missing timestamp_ms in payload` | Missing/zero timestamp | POS must set before signing; expand must keep `ts` → `timestamp_ms` |
| `Timestamp outside allowed window` | Older than ~10 minutes | Fresh sign / refresh presence `ts` |
| `Invalid signature` | Wrong key, or expanded fields ≠ what POS signed | Expand only signed keys; sync keys |
| `Bank name mismatch` / `Bank name hash mismatch` | Display bank ≠ registry | Match dashboard settlement bank / msk |
| `Unknown terminal_id` | Not registered | Register / enable Pay at shop |
| `Session UUID already used (replay)` | Checkout session already verified | New checkout session from POS |
| `Session already paid` | Session closed (`session_status: paid` / `cancelled`) | Customer already paid, or cashier cancelled |
| `Pay at shop is not active for this merchant` | CheckoutPay only | Enable in merchant dashboard |
| `Rate limit exceeded` | Too many verifies | Retry after `retry_after_seconds` |

---

## Receiver checklist (banking / wallet app)

1. Find tills and read `cbbc0002` as in [ble-transport.md](ble-transport.md#receiver-finding-tills-and-reading-the-packet) (unfiltered scan, read only, never pair).
2. Parse UTF-8 JSON → **`normalizeBleReadForVerify`** (expand compact `{p,alg,sig}`). Skip sessions already handled.
3. Don't reject on packet age locally — the server decides whether the session is still open.
4. `POST` `{ payload, signature_alg, signature }` to `/verify-broadcast`.
5. Failure = non-2xx **or** `valid: false`. Show `error` / `message`.
6. On success: pre-fill transfer from **server** `recipient_*` + merchant name; amount from the packet (`amt ÷ 100`).
7. Presence (`session_kind: presence`, or no / zero amount): ask the customer for the amount.
8. Pay with `session_uuid` as the idempotency key and remark `Payment at {merchant_name}`.

## Sender checklist (POS)

1. Prefer **Ed25519** + compact wire under 512 bytes for CheckoutPay.
2. Put amount in **kobo** as `amt` / signed `total_amount_ngn`.
3. Sign **expanded** canonical payload, then compress to `{p,alg,sig}` for BLE.
4. Idle till: omit/`amt: 0`, refresh `ts` + re-sign; do not require a cart.
5. New `session_uuid_v4` when starting a real checkout payment.

Reference: [`deploy/laravel/BroadcastVerifyController.php`](../deploy/laravel/BroadcastVerifyController.php), [`demos/web-receiver/ble-wire-expand.js`](../demos/web-receiver/ble-wire-expand.js), [`sdk/typescript/src/bleWire.ts`](../sdk/typescript/src/bleWire.ts).
