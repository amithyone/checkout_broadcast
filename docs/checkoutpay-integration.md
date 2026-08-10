# CheckoutPay integration guide

How **POS terminals**, **wallet apps**, and **third-party services** integrate with CheckoutPay **Pay at shop** on `check-outpay.com`.

This matches what **CheckoutNow** ships in production (compact BLE wire → expand → verify).

## URLs

| Env var / config | Value |
|------------------|-------|
| Wallet app base | `EXPO_PUBLIC_CHECKOUT_BROADCAST_API=https://check-outpay.com/api/v1/broadcast` |
| Verify endpoint | `POST …/verify-broadcast` |
| Sync signing key (POS) | `POST …/terminals/sync-signing-key` |
| Health | `GET …/health` |

**Base URL must end at `/api/v1/broadcast`** (not the site root). Python helper: `normalize_bank_api_url()`.

Full contract: [spec/verify-api.md](../spec/verify-api.md) · BLE wire: [spec/ble-transport.md](../spec/ble-transport.md)

## Terminal credentials (from merchant dashboard)

After admin enables Pay at shop, merchants open **Dashboard → Pay at shop** and copy:

| Credential | Used by | Notes |
|------------|---------|-------|
| **Terminal ID** | POS + verify | e.g. `CP-1RK8Z` |
| **Merchant ID** | POS integrations | e.g. `MCH-…` |
| **API key** | CheckoutPay API (`bk_…`) | Optional for other CheckoutPay features |
| **Signing key** | POS only | Ed25519 private key (base64) — **never** put in wallet app |

CheckoutPay stores only the **public key** for verification.

## POS (sender) — production shape

1. Sign the **expanded** canonical payload with **Ed25519**.
2. Broadcast compact GATT JSON `{ p, alg, sig }` (see [ble-transport.md](../spec/ble-transport.md)).
3. Put checkout amount in **kobo** (`amt`: ₦25.00 → `2500`).
4. Idle till / “Pay at shop” without a cart: omit `amt` or `amt: 0`, optional `"k":"presence"`; refresh `ts` and re-sign periodically.
5. Keep **one** signing key on disk for POS + BLE sidecar (Cheko: `%APPDATA%\Cheko POS\cheko-config.json`). After dashboard rotate, call sync-signing-key / Settings “Test connection”.

### Compact wire helpers (Python)

```python
from checkout_broadcast import (
    encode_wire_envelope,
    to_packet_amount,
    wire_to_verify_envelope,
)

kobo = to_packet_amount(25.00, "ed25519")  # 2500
wire = encode_wire_envelope({"payload": payload, "signature_alg": "ed25519", "signature": sig})
# GATT advertise `wire`; wallet expands:
envelope = wire_to_verify_envelope(wire)
```

### Sync signing key (POS Settings)

```http
POST /api/v1/broadcast/terminals/sync-signing-key
Content-Type: application/json
X-Terminal-Api-Key: bk_…

{ "terminal_id": "CP-1RK8Z", "signing_key": "<base64 ed25519 seed>" }
```

Used by Cheko “Test connection” to update the terminal’s signing seed in CheckoutPay so live verify matches this POS (open-until-paid verify still applies).

Python SDK (full envelope for local/dev; for Cheko production prefer compact wire under 512 bytes):

```python
from checkout_broadcast import CheckoutBroadcastAddon, CheckoutBroadcastConfig, CheckoutData

addon = CheckoutBroadcastAddon(CheckoutBroadcastConfig(
    role="send",
    terminal_id="CP-1RK8Z",
    signing_key=os.environ["CHECKOUT_SIGNING_KEY"],  # from dashboard
    signature_alg="ed25519",
    bank_api_url="https://check-outpay.com/api/v1/broadcast",
    bank_name="RUBIES MFB",  # must match registered settlement bank
    masked_account_suffix="***1234",
    transport="ble",
))

addon.start()
# amount_ngn here is major Naira in the open SDK helper — Cheko wire uses kobo on BLE
addon.send_checkout(CheckoutData(amount_ngn=2500, item_count=3))
```

## Wallet app (receiver) — required expand step

```typescript
import {
  CheckoutBroadcastAddon,
  normalizeBleReadForVerify,
  verifyRequestBody,
  wireKoboToNaira,
} from "@checkout-broadcast/web";

// After reading GATT UTF-8 JSON:
const envelope = normalizeBleReadForVerify(gattJson);
if (!envelope) throw new Error("Unrecognized BLE packet");

const res = await fetch("https://check-outpay.com/api/v1/broadcast/verify-broadcast", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(verifyRequestBody(envelope)),
});
const body = await res.json();
if (!body.valid) throw new Error(body.error ?? "verify failed");

const amountMajor =
  envelope.wireSource === "wire" ? wireKoboToNaira(body.amount_ngn) : body.amount_ngn;

if (body.session_kind === "presence" || amountMajor <= 0) {
  // customer enters amount
} else {
  // pre-fill transfer with amountMajor + body.recipient_account / recipient_bank_code
}
```

CheckoutPay’s Laravel verify controller **also** expands compact `{p,alg,sig}` if the wallet posts wire JSON directly — but wallet apps should still expand locally so timestamps and UX (presence / kobo) are correct before the HTTP call.

### Common mistakes

| Symptom | Cause |
|---------|--------|
| `Invalid signature` on real Cheko till | Posted compact wire **without** expand, or invented `currency_code` / `item_count` / `bank_name` during expand |
| Amount 100× too large | Treated kobo as whole Naira — use `÷ 100` for wire |
| Presence opens ₦0 transfer | Idle beacon — prompt for amount when `session_kind=presence` or amount 0 |
| `timestamp_ms` missing | Dropped `ts` during expand |
| `Bank name mismatch` | POS bank / msk ≠ dashboard settlement account |
| `Invalid signature` after Settings save | Electron + BLE sidecar used **different** config files / keys — unify path and re-sync |
| Verify OK, phone still fails | Stale BLE session — start a **new** checkout after key sync |

## Laravel deploy (CheckoutPay)

Reference controller: [`deploy/laravel/BroadcastVerifyController.php`](../deploy/laravel/BroadcastVerifyController.php) (Cheko-proven):

- Expands compact `{p,alg,sig}` on the server
- **Open until paid** (presence / unpaid checkout sessions not burned on first verify)
- Merchant active check + presence time window
- Routes snippet: [`deploy/laravel/routes-snippet.php`](../deploy/laravel/routes-snippet.php)

## Open SDK vs CheckoutPay production

| | Open SDK demos | CheckoutPay / CheckoutNow production |
|--|----------------|--------------------------------------|
| BLE JSON | Full `{payload, signature_alg, signature}` | Compact `{p, alg, sig}` |
| Signature | Often HMAC-SHA256 | **Ed25519** |
| Amount on wire | Whole Naira in many fixtures | **Kobo** |
| Presence | Not in older demos | Idle till supported |
| Terminal registration | `POST /terminals/register` + admin key | Merchant dashboard |

Both can hit the same CheckoutPay verify endpoint when expanded correctly.

## Testing

```bash
# Reference bank API (local)
./deploy/smoke-test.sh

# Expand helper (Node)
node -e "import { normalizeBleReadForVerify } from './demos/web-receiver/ble-wire-expand.js'; console.log(normalizeBleReadForVerify({p:{v:2.1,sid:'…',tid:'CP-1',ts:Date.now(),amt:649,msk:'***1234'},alg:'ed25519',sig:'x'}))"
```
