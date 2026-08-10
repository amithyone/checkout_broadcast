# BLE transport (Checkout Broadcast)

This is the **production path used by CheckoutNow / Cheko Pay at shop**. Wallet apps and POS integrators should implement this shape first.

## GATT

| Role | UUID |
|------|------|
| Service | `cbbc0001-0000-4000-8000-000000000001` |
| Packet characteristic (read / notify) | `cbbc0002-0000-4000-8000-000000000001` |

UTF-8 JSON on the packet characteristic. Keep under **~512 bytes** (typical Android GATT MTU).

## Compact wire envelope (primary)

Production POS writes a **compact** envelope, not the full verify body:

### Checkout (amount known)

`amt` is **kobo** (₦6.49 → `649`):

```json
{
  "p": {
    "v": 2.1,
    "sid": "550e8400-e29b-41d4-a716-446655440000",
    "tid": "CP-1RK8Z",
    "ts": 1738123456789,
    "amt": 649,
    "msk": "***4863"
  },
  "alg": "ed25519",
  "sig": "<base64>"
}
```

### Presence / idle till (customer enters amount)

Omit `amt`, or set `"amt": 0`. Optional `"k": "presence"`:

```json
{
  "p": {
    "v": 2.1,
    "sid": "550e8400-e29b-41d4-a716-446655440000",
    "tid": "CP-1RK8Z",
    "ts": 1738123456789,
    "msk": "***4863",
    "k": "presence"
  },
  "alg": "ed25519",
  "sig": "<base64>"
}
```

### Wire key map

| Wire | Expanded payload field |
|------|------------------------|
| `p.v` | `protocol_version` (e.g. `2.1`) |
| `p.sid` | `session_uuid_v4` |
| `p.tid` | `terminal_id` |
| `p.ts` | `timestamp_ms` |
| `p.amt` | `transaction_details.total_amount_ngn` (**kobo**) |
| `p.msk` | `account_info_public_display.masked_account_suffix` |
| `p.k` | `session_kind` (`presence` / `pos_checkout`) when present |
| `alg` | `signature_alg` (default `ed25519`) |
| `sig` | `signature` |

## Critical signing rule

The signature covers the **expanded canonical payload** (sorted JSON, no whitespace), **not** the short wire keys in `p`.

1. POS builds canonical payload → signs → then may compress to `{p,alg,sig}` for BLE.
2. Wallet **must expand** before `POST /verify-broadcast` (unless the bank backend expands).
3. Do **not** invent fields the POS did not sign (`currency_code`, `item_count`, `bank_name`, etc.) during expand — that breaks Ed25519 verify.

Reference expanders:

- App / Cheko: same logic as CheckoutNow `expandWireToVerifyPacket`
- Demo: [`demos/web-receiver/ble-wire-expand.js`](../demos/web-receiver/ble-wire-expand.js) → `normalizeBleReadForVerify`
- TypeScript SDK: `normalizeBleReadForVerify` in `@checkout-broadcast/web`
- Laravel: `BroadcastVerifyController::normalizeBlePacket`

## Amount units (kobo)

For compact wire packets:

- Signed `total_amount_ngn` / wire `amt` = **integer kobo**
- Wallet UI and bank transfer amount = **kobo ÷ 100** (major Naira)
- Legacy full envelopes may still use whole Naira — detect via wire vs legacy shape

## Presence / replay

- Presence: amount `0` / omitted — customer types amount in the wallet
- Do **not** burn `session_uuid` on presence verify (till stays idle and re-broadcasts)
- Burn session UUID only on checkout verify (`amount > 0`)
- Refresh `ts` and re-sign every few minutes while idle

## Legacy full envelope (still accepted)

Older POS / open SDK HMAC demos may broadcast:

```json
{
  "payload": { "protocol_version": 2, "timestamp_ms": …, "session_uuid_v4": …, "terminal_id": …, "transaction_details": { "total_amount_ngn": 2500, … }, "account_info_public_display": { … } },
  "signature_alg": "HMAC-SHA256",
  "signature": "…"
}
```

Receivers should accept **both** shapes via `normalizeBleReadForVerify`.
