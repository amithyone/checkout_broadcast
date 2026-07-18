# Checkout Broadcast v2.1 — Wallet receive profile (draft)

**Status:** Draft / deferred from v2.0 POS rollout.  
**Audience:** CheckoutNow and third-party wallet apps exploring cross-app receive.

---

## Purpose

v2.0 is **POS-first**: signed merchant terminals broadcast checkout intent to any implementing wallet.

v2.1 adds an optional **`broadcast_kind: "wallet_receive"`** profile so a **CheckoutNow user** (or any wallet app) can broadcast a **signed receive handle** that other wallet apps understand — without exposing plain pay codes over open BLE like proprietary Nearby Pay.

This is **secondary** to POS receive. Implement POS v2.0 before wallet profile.

---

## Coexistence

| Profile | `broadcast_kind` | Sender | Receiver |
|---------|------------------|--------|----------|
| POS checkout (v2.0) | omitted or `"pos_checkout"` | Merchant POS | Any wallet |
| Wallet receive (v2.1) | `"wallet_receive"` | Wallet app | Any wallet app |
| CheckoutNow Nearby Pay | N/A (separate UUID) | CheckoutNow | CheckoutNow only |

See [coexistence-with-proprietary-nearby.md](./coexistence-with-proprietary-nearby.md).

---

## Payload extension (backward compatible)

When `broadcast_kind` is `"wallet_receive"`, the v2.0 payload gains:

```json
{
  "protocol_version": 2.1,
  "broadcast_kind": "wallet_receive",
  "timestamp_ms": 1720000000000,
  "session_uuid_v4": "550e8400-e29b-41d4-a716-446655440000",
  "terminal_id": "WALLET-CN-abc123",
  "transaction_details": {
    "currency_code": "NGN",
    "total_amount_ngn": 5000,
    "item_count": 1
  },
  "wallet_receive": {
    "display_name": "Amithy O.",
    "handle_type": "checkoutnow_user",
    "handle_id": "usr_…",
    "note": "Lunch split"
  },
  "account_info_public_display": {
    "bank_name_hash": "sha256:…",
    "masked_account_suffix": "***1234"
  }
}
```

- **`terminal_id`** for wallet senders is a registered **wallet broadcaster ID**, not a shop POS ID.
- Signing uses the same HMAC rules as v2.0 ([signing-rules.md](./signing-rules.md)).
- BLE transport unchanged ([ble-transport.md](./ble-transport.md)).

---

## Verification API

Wallet receivers POST the signed envelope to **`POST /verify-broadcast`** on **their** bank API (same as POS).

Bank registry rows for wallet broadcasters include:

| Field | POS terminal | Wallet broadcaster |
|-------|--------------|-------------------|
| `terminal_id` | `POS-LAG-001` | `WALLET-CN-…` |
| `signing_key` | POS secret | Wallet app secret |
| `merchant_name` | Shop name | User display name |
| Settlement account | Merchant NUBAN | User NUBAN (from registry, not BLE) |

Response shape unchanged from v2.0.

---

## Security notes

1. Never put raw pay codes in wallet broadcasts — use signed handles only.
2. Amount is optional for “request any amount” flows; banks may require `total_amount_ngn > 0`.
3. Replay protection: same `session_uuid_v4` rules as POS.
4. CheckoutNow Nearby Pay (`a7c5c816-…`) remains for backward-compatible CN↔CN P2P.

---

## Implementation order (CheckoutNow)

1. Ship POS receive (“Pay at shop”) on v2.0.
2. Publish this draft; gather OPay/Kuda/GTBank feedback.
3. Add wallet broadcaster registration to check-outpay.com admin.
4. Optional CheckoutNow **send** profile behind feature flag — **do not** replace Nearby Pay until v2.1 is stable.

---

## Open questions

- Industry-wide wallet handle namespace (`handle_type` values)?
- Cross-bank settlement vs same-bank-only wallet receive?
- Maximum broadcast TTL for wallet receive (10 min default)?

Feedback: open an issue in the public `checkout_broadcast` repository.
