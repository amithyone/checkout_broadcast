# CheckoutPay integration guide

How **POS terminals**, **wallet apps**, and **third-party services** integrate with CheckoutPay **Pay at shop** on `check-outpay.com`.

## URLs

| Env var / config | Value |
|------------------|-------|
| Wallet app base | `EXPO_PUBLIC_CHECKOUT_BROADCAST_API=https://check-outpay.com/api/v1/broadcast` |
| Verify endpoint | `POST …/verify-broadcast` |
| Health | `GET …/health` |

Full contract: [spec/verify-api.md](../spec/verify-api.md)

## Terminal credentials (from merchant dashboard)

After admin enables Pay at shop, merchants open **Dashboard → Pay at shop** and copy:

| Credential | Used by | Notes |
|------------|---------|-------|
| **Terminal ID** | POS + verify | e.g. `CP-1RK8Z` |
| **Merchant ID** | POS integrations | e.g. `MCH-…` |
| **API key** | CheckoutPay API (`bk_…`) | Optional for other CheckoutPay features |
| **Signing key** | POS only | Ed25519 private key (base64) — **never** put in wallet app |

CheckoutPay stores only the **public key** for verification.

## POS (sender) — Python example (Ed25519)

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
addon.send_checkout(CheckoutData(amount_ngn=2500, item_count=3))
```

The SDK automatically sets `payload.timestamp_ms = int(time.time() * 1000)` before signing.

## Wallet app (receiver)

```typescript
import { CheckoutBroadcastAddon } from "@checkout-broadcast/web";

const addon = new CheckoutBroadcastAddon({
  role: "receive",
  bankApiUrl: "https://check-outpay.com/api/v1/broadcast",
  transport: "ble",
  onPaymentReceived: (payment) => prefillTransfer(payment),
  onError: (err) => showManualTransferFallback(err.message),
});

await addon.start();
```

The SDK:

- Validates `timestamp_ms` is present before calling the bank
- POSTs the **unchanged** signed BLE packet to `/verify-broadcast`
- Surfaces backend `error` strings (e.g. `Missing timestamp_ms in payload`)

## Common mistakes

| Symptom | Cause |
|---------|--------|
| `timestamp_ms undefined` in app logs | POS did not include field, or app rebuilt payload without it |
| `Missing timestamp_ms in payload` from API | Same — fix on POS; app must forward full JSON |
| `Timestamp outside allowed window` | Stale BLE packet or wrong device clock |
| `Invalid signature` | Wrong signing key or modified payload after sign |
| `Bank name hash mismatch` | POS `bank_name` ≠ merchant settlement bank in dashboard |

## Open SDK vs CheckoutPay

| | Open SDK (v2.0) | CheckoutPay Pay at shop |
|--|-----------------|-------------------------|
| Signature | HMAC-SHA256 | Ed25519 |
| `protocol_version` | `2.0` | `1` or `2.0` |
| Terminal registration | `POST /terminals/register` + admin key | Merchant dashboard auto-provisions |
| Reference | [pos-app-integration.md](pos-app-integration.md) | This guide |

Both work on the same CheckoutPay verify endpoint.

## Testing

```bash
# Reference bank API (local)
./deploy/smoke-test.sh

# Against CheckoutPay staging/production
PYTHONPATH="sdk/python:." python -m checkout_broadcast.cli demo-send \
  --amount 2500 \
  --bank-url https://check-outpay.com/api/v1/broadcast
```

Run conformance tests: `pytest tests/test_conformance.py -k golden`

## Further reading

- [banking-app-integration.md](banking-app-integration.md) — receiver UX and Android/iOS
- [pos-app-integration.md](pos-app-integration.md) — HMAC POS flow
- [deploy/checkoutpay-production.md](../deploy/checkoutpay-production.md) — server deploy notes
