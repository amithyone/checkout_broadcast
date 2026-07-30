# POS App Integration Guide

This guide is for **Point-of-Sale (POS) developers** — shop terminals, Windows cashier apps, merchant POS software (e.g. integrated with Kuda/OPay merchant tools).

Your app plays the **sender** role: after checkout is complete (items scanned, total calculated), you broadcast a signed payment request so nearby customers can pay from their banking app.

---

## 1. What you need before coding

| Requirement | Description |
|-------------|-------------|
| **Terminal ID** | Unique ID for this POS, e.g. `POS-LAG-001`. Issued when merchant registers with the bank. |
| **Signing key** | HMAC secret paired with your terminal ID. Store securely — never ship in client-side web code. |
| **Merchant profile** | Registered with bank: merchant name, bank name, NUBAN/account suffix, `bank_name_hash`. |
| **Bank API URL** | Your bank's verification endpoint (production) or mock API (development). |

Register a terminal with the reference bank API during development:

```bash
export CHECKOUT_BANK_ADMIN_KEY="your-admin-secret"
export CHECKOUT_SIGNING_KEY="your-terminal-signing-key-min-16-chars"

PYTHONPATH="sdk/python:." python -m checkout_broadcast.cli register-terminal \
  --id POS-LAG-001 \
  --merchant "ABC Enterprises" \
  --bank kuda \
  --suffix "***9876" \
  --account 0123456789 \
  --bank-code 50211
```

Registration requires the `X-Admin-Key` header (set automatically by the CLI from `CHECKOUT_BANK_ADMIN_KEY`).

### CheckoutPay merchants (Pay at shop)

If the merchant uses **CheckoutPay** (`check-outpay.com`), skip manual registration — credentials come from **Dashboard → Pay at shop**:

- Terminal ID, Merchant ID, Signing key (Ed25519, base64)
- Set `signature_alg="ed25519"` in the SDK config
- Set `bank_name` to match the merchant's settlement bank exactly

See **[CheckoutPay integration guide](../docs/checkoutpay-integration.md)**.

---

## 2. Choose your SDK

| Platform | SDK path | Install |
|----------|----------|---------|
| **Windows / Linux POS** | `sdk/python/` | `pip install -e .` from `checkout_broadcast/` |
| **Web merchant dashboard** | `sdk/typescript/` | `npm install` in `sdk/typescript/` (send limited on web — prefer Windows for POS) |
| **Android POS** | `sdk/android/` | Add AAR module (send via BLE — phase 2) |

**Recommended for Nigerian SME POS:** Python SDK on **Windows** with `transport="ble"`.

---

## 3. Integration steps (all platforms)

1. Add the SDK dependency to your POS project.
2. Initialize the addon with **`role: "send"`** (or `"both"` if your app also receives).
3. Call **`start()`** when the cashier opens the payment screen.
4. After checkout total is finalized, call **`sendCheckout({ amountNgn, itemCount })`**.
5. Call **`stop()`** when leaving the payment screen or after timeout.

**Important:** Only broadcast **after checkout completion** — not while items are still being scanned. This saves battery and reduces signal clutter in busy markets.

---

## 4. Python / Windows integration

### Install

```bash
cd checkout_broadcast
pip install -r requirements.txt

# For real BLE on Windows/Linux:
pip install -r requirements-ble.txt
```

### Minimal integration (~15 lines)

```python
from checkout_broadcast import CheckoutBroadcastAddon, CheckoutBroadcastConfig, CheckoutData

addon = CheckoutBroadcastAddon(CheckoutBroadcastConfig(
    role="send",
    terminal_id="POS-LAG-001",
    signing_key=os.environ["CHECKOUT_SIGNING_KEY"],  # from secure store
    bank_api_url="https://api.yourbank.ng/checkout",
    bank_name="kuda",
    masked_account_suffix="***9876",
    transport="ble",  # use "simulated" in unit tests
    on_send_complete=lambda session_id: print(f"Broadcast sent: {session_id}"),
    on_error=lambda err: show_cashier_error(str(err)),
))

def on_checkout_complete(cart):
    addon.start()
    addon.send_checkout(CheckoutData(
        amount_ngn=int(cart.total_kobo / 100),  # or direct NGN integer
        item_count=len(cart.items),
    ))
    show_cashier_message("Waiting for customer payment…")

def on_payment_screen_closed():
    addon.stop()
```

### Wire into your existing POS flow

```python
# Example: hook after your existing cart.total is approved
class PaymentController:
    def __init__(self):
        self.broadcast = CheckoutBroadcastAddon(CheckoutBroadcastConfig(
            role="send",
            terminal_id=settings.TERMINAL_ID,
            signing_key=settings.SIGNING_KEY,
            bank_api_url=settings.BANK_API_URL,
            transport="ble",
        ))

    def begin_payment_collection(self, order):
        self.broadcast.start()

    def checkout_finalized(self, order):
        """Call ONLY when cashier taps 'Charge customer' / checkout complete."""
        self.broadcast.send_checkout(CheckoutData(
            amount_ngn=order.total_ngn,
            item_count=order.line_count,
        ))

    def cancel_payment_collection(self):
        self.broadcast.cancel_checkout()
        self.broadcast.stop()
```

### CLI test (development)

```bash
# Simulated (no radio)
PYTHONPATH="sdk/python:." python -m checkout_broadcast.cli demo-send --amount 2500 --items 3

# Real BLE (Windows/Linux with bleak installed)
PYTHONPATH="sdk/python:." python -m checkout_broadcast.cli demo-send --transport ble --amount 2500
```

---

## 5. TypeScript / Web integration

Web browsers **cannot act as BLE peripherals**, so web-based POS should either:

- Run the **Python SDK on a Windows machine** behind the counter, or
- Use `transport: "simulated"` for demos only

If your merchant dashboard runs in Electron or Tauri on Windows, embed the Python SDK or call a local helper service.

```typescript
import { CheckoutBroadcastAddon } from "@checkout-broadcast/web";

const addon = new CheckoutBroadcastAddon({
  role: "send",
  terminalId: "POS-LAG-001",
  signingKey: process.env.CHECKOUT_SIGNING_KEY!,
  bankApiUrl: "https://api.yourbank.ng/checkout",
  transport: "simulated", // web cannot BLE-advertise
});

await addon.start();
await addon.sendCheckout({ amountNgn: 2500, itemCount: 3 });
```

---

## 6. Android POS (phase 2)

The Android SDK stub is at `sdk/android/`. BLE peripheral (advertise) support is planned for phase 2. Until then, use the **Windows Python SDK** for POS send.

```kotlin
// Future API (receive/send roles enforced the same way)
val addon = CheckoutBroadcastAddon(CheckoutBroadcastConfig(
    role = "send",
    terminalId = "POS-LAG-001",
    signingKey = secureStore.getSigningKey(),
    bankApiUrl = "https://api.yourbank.ng/checkout",
    transport = "ble",
))
```

---

## 7. Transport options

| Transport | When to use |
|-----------|-------------|
| `simulated` | Unit tests, CI, same-machine dev demos |
| `ble` | Production — customer phones receive over Bluetooth |

**BLE requirements (production):**

- Windows or Linux POS with Bluetooth 4.0+
- Install: `pip install -r requirements-ble.txt`
- POS must be within ~10 m of customer phone
- See [BLE transport spec](../spec/ble-transport.md) for GATT UUIDs

**macOS note:** Python BLE send is not supported on macOS. Use a Windows POS device or simulated transport for Mac dev.

---

## 8. Payload your app sends

The SDK builds and signs this automatically. You only pass `amountNgn` and `itemCount`.

```json
{
  "payload": {
    "protocol_version": 2.0,
    "timestamp_ms": 1720000000000,
    "session_uuid_v4": "550e8400-e29b-41d4-a716-446655440000",
    "terminal_id": "POS-LAG-001",
    "transaction_details": {
      "currency_code": "NGN",
      "total_amount_ngn": 2500,
      "item_count": 3
    },
    "account_info_public_display": {
      "bank_name_hash": "sha256:1ab138fd...",
      "masked_account_suffix": "***9876"
    }
  },
  "signature_alg": "HMAC-SHA256",
  "signature": "<base64>"
}
```

The **amount is locked by the signature**. If an attacker changes the amount in transit, the banking app’s bank API verification fails.

---

## 9. Error handling

| Error | Cause | POS action |
|-------|-------|------------|
| `RoleNotAllowedError` | Misconfigured role | Ensure `role="send"` |
| `TransportError` | BLE unavailable / wrong OS | Fall back to QR or manual account entry |
| Missing signing key | Config error | Load from secure store; do not hardcode |

```python
addon = CheckoutBroadcastAddon(CheckoutBroadcastConfig(
    role="send",
    terminal_id=terminal_id,
    signing_key=signing_key,
    bank_api_url=bank_api_url,
    transport="ble",
    on_error=lambda e: pos_ui.show_fallback_payment_methods(),
))
```

Always offer a **fallback** (manual account number, QR, USSD) if broadcast fails.

---

## 10. Security checklist for POS vendors

- [ ] Store `signing_key` in OS secure storage (Windows Credential Manager, not plain config files)
- [ ] Register each physical terminal with the bank before go-live
- [ ] Rotate signing keys if a device is lost or compromised
- [ ] Broadcast only after checkout complete — never on idle
- [ ] Use HTTPS for any bank API calls from the POS (registration, status)
- [ ] Do not log full signing keys or customer account numbers

---

## 11. Go-live checklist

1. [ ] Bank has registered your `terminal_id` and merchant profile
2. [ ] Signing key provisioned securely on each POS device
3. [ ] BLE tested: `demo-send --transport ble` on Windows POS + banking app receive on phone
4. [ ] Fallback payment path tested when BLE is off or unavailable
5. [ ] Cashier trained: "Customer should open their banking app near the terminal"

---

## 12. Related docs

- [Banking app integration guide](banking-app-integration.md) — share with partner banks
- [Signing rules](../spec/signing-rules.md)
- [BLE transport](../spec/ble-transport.md)
- [Unified addon API](../spec/addon-api.md)
