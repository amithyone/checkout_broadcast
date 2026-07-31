# Banking App Integration Guide

This guide is for **mobile banking and wallet app developers** — Kuda, OPay, PalmPay, GTBank, Access Bank, and similar apps used by customers to send money.

Your app plays the **receiver** role: listen for nearby checkout broadcasts, verify them with **your bank's backend**, then pre-fill the transfer screen so the customer only confirms with PIN or biometrics.

---

## 1. What you need before coding

| Requirement | Description |
|-------------|-------------|
| **Bank verification API** | Backend endpoint that validates signed broadcasts (see §6). |
| **Merchant terminal registry** | Database of registered POS terminals, signing keys, and merchant names. |
| **SDK (receive role)** | Android AAR, iOS Swift Package, or Web/TypeScript bundle. |
| **BLE permissions** | Android `BLUETOOTH_SCAN`, iOS `NSBluetoothAlwaysUsageDescription`, etc. |

The SDK calls **your** bank API — it does not move money by itself. After verification, your app runs your existing transfer flow.

### Adopter quick start (OPay, Kuda, GTBank)

Each bank implements the same receive pipeline; only `bankApiUrl` and your terminal registry differ.

| Bank | Example verify URL | Golden test fixture |
|------|-------------------|---------------------|
| **OPay** | `https://api.opayweb.com/checkout/v1` | [`tests/fixtures/golden_opay_pos.json`](../tests/fixtures/golden_opay_pos.json) |
| **Kuda** | `https://api.kuda.com/checkout/v1` | [`tests/fixtures/golden_kuda_pos.json`](../tests/fixtures/golden_kuda_pos.json) |
| **GTBank** | `https://api.gtbank.com/checkout/v1` | [`tests/fixtures/golden_gtbank_pos.json`](../tests/fixtures/golden_gtbank_pos.json) |

Run conformance tests locally:

```bash
cd checkout_broadcast
pip install -r requirements.txt
pytest tests/test_conformance.py -k golden
```

Register each golden `terminal_id` in your staging registry with signing key `test-signing-key-min-16-chars`, POST the fixture envelope to `/verify-broadcast`, expect `valid: true`.

**CheckoutNow** (reference implementer): `https://check-outpay.com/api/v1/broadcast/verify-broadcast` — see [deploy/checkoutpay-production.md](../deploy/checkoutpay-production.md).

**Do not confuse with CheckoutNow Nearby Pay** — proprietary P2P uses different BLE UUIDs; see [coexistence spec](../spec/coexistence-with-proprietary-nearby.md).

---

## 2. Choose your SDK

| Platform | SDK path | Default role |
|----------|----------|--------------|
| **Android** | `sdk/android/checkout-broadcast/` | `receive` |
| **iOS** | `sdk/ios/CheckoutBroadcast/` | `receive` |
| **Web (PWA)** | `sdk/typescript/` or `demos/web-receiver/checkout-broadcast.js` | `receive` |
| **React Native** | Wrap native Android/iOS modules | `receive` |

**Do not** set `role: "send"` in a consumer banking app unless you also operate merchant POS products.

---

## 3. Integration steps (all platforms)

1. Add SDK dependency.
2. Initialize with **`role: "receive"`** and your **`bankApiUrl`**.
3. Set **`onPaymentReceived`** callback → pre-fill transfer UI.
4. Set **`onError`** → show friendly message, allow manual transfer.
5. Call **`start()`** when user opens "Pay" / "Transfer" / home screen (or dedicated "Pay at shop" screen).
6. Call **`stop()`** when user leaves the screen.

The SDK handles BLE scanning, local timestamp checks, and the HTTP call to your verification API.

---

## 4. Customer journey (what your UI should do)

```
1. Customer finishes shopping; cashier completes checkout on POS
2. Customer opens YOUR banking app (or already has it open)
3. SDK receives broadcast → calls your bank API → onPaymentReceived fires
4. You show: "Pay ABC Enterprises — ₦2,500 — ***9876"
5. Transfer screen pre-filled:
   - Recipient name: ABC Enterprises (from bank API response)
   - Amount: ₦2,500 (locked — do not allow edit if verification said so)
   - Account: resolved from bank registry (not from BLE packet alone)
6. Customer reviews → PIN / Face ID → your normal debit API
```

**Push notification (optional):** Use `onPaymentReceived` to trigger a local notification: *"Pay at ABC Enterprises — ₦2,500"*.

---

## 5. Android integration

### Add module

Include `sdk/android/checkout-broadcast` as a Gradle module in your app.

### Permissions (`AndroidManifest.xml`)

```xml
<uses-permission android:name="android.permission.BLUETOOTH_SCAN"
    android:usesPermissionFlags="neverForLocation" />
<uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
<uses-feature android:name="android.hardware.bluetooth_le" android:required="false" />
```

### Kotlin example

```kotlin
import com.checkoutbroadcast.CheckoutBroadcastAddon
import com.checkoutbroadcast.CheckoutBroadcastConfig
import com.checkoutbroadcast.VerifiedPayment

class PayAtShopController(private val activity: Activity) {
    private val addon = CheckoutBroadcastAddon(
        CheckoutBroadcastConfig(
            role = "receive",
            bankApiUrl = "https://api.yourbank.ng/checkout",
            transport = "ble",
            androidContext = activity.applicationContext,
            onPaymentReceived = { payment -> showPrefilledTransfer(payment) },
            onError = { err -> showManualTransferFallback() },
        ),
    )

    fun onPayScreenVisible() {
        addon.start()
    }

    fun onPayScreenHidden() {
        addon.stop()
    }

    private fun showPrefilledTransfer(payment: VerifiedPayment) {
        TransferActivity.launch(
            context = activity,
            recipientName = payment.merchantName,
            amountNgn = payment.amountNgn,
            maskedAccount = payment.maskedAccountSuffix,
            sessionUuid = payment.sessionUuid,
            terminalId = payment.terminalId,
        )
    }
}
```

The addon scans for GATT service `cbbc0001-…`, connects, reads the signed JSON characteristic, and POSTs to your `/verify-broadcast` endpoint.

### Amount locking

If your bank API returns `valid: true`, treat the amount as **verified**. Disable amount editing on the transfer screen unless the user explicitly chooses "Pay different amount" (which skips broadcast verification).

---

## 6. iOS integration

### Add Swift Package

Add local package: `sdk/ios/CheckoutBroadcast/`

### Info.plist

```xml
<key>NSBluetoothAlwaysUsageDescription</key>
<string>Used to detect nearby shop payment requests so we can pre-fill your transfer.</string>
```

### Swift example

```swift
import CheckoutBroadcast

final class PayAtShopManager {
    private var addon: CheckoutBroadcastAddon?

    func startListening() {
        var config = CheckoutBroadcastConfig(
            role: "receive",
            bankApiUrl: "https://api.yourbank.ng/checkout",
            transport: "ble"
        )
        config.onPaymentReceived = { [weak self] payment in
            self?.presentTransfer(payment: payment)
        }
        config.onError = { error in
            // Log and allow manual transfer
        }

        let addon = CheckoutBroadcastAddon(config: config)
        try? addon.start()
        self.addon = addon
    }

    func stopListening() {
        addon?.stop()
    }

    private func presentTransfer(payment: VerifiedPayment) {
        // Push your existing transfer view controller
    }
}
```

The addon uses `CheckoutBleReceiver` internally for scan → connect → GATT read → verify.

---

## 7. Web / PWA integration

Web Bluetooth works in **Chrome/Edge** on desktop and Android (not Safari/iOS).

### Serve demo or embed bundle

```html
<script type="module">
  import { CheckoutBroadcastAddon } from "./checkout-broadcast.js";

  const addon = new CheckoutBroadcastAddon({
    role: "receive",
    bankApiUrl: "https://api.yourbank.ng/checkout",
    transport: "ble",
    onPaymentReceived: (p) => {
      document.getElementById("recipient").value = p.merchantName;
      document.getElementById("amount").value = p.amountNgn;
    },
    onError: (e) => console.error(e),
  });

  await addon.start();
  await addon.requestBleDevice(); // user picks POS from browser dialog
</script>
```

**Requirements:**

- Site served over **HTTPS** (or `localhost` for dev)
- User gesture required before `requestBleDevice()` (button click)

For production web banking, prefer the **native Android/iOS SDK** — Web Bluetooth is best for merchant kiosks or internal tools.

---

## 8. Bank backend API (required)

Your bank must implement verification. The SDK POSTs the full signed envelope to your API.

### `POST /verify-broadcast`

**Request body:** signed packet (same JSON the POS broadcast).

**Success response (200):**

```json
{
  "valid": true,
  "merchant_name": "ABC Enterprises",
  "amount_ngn": 2500,
  "masked_account_suffix": "***9876",
  "session_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "terminal_id": "POS-LAG-001",
  "recipient_account": "0123456789",
  "recipient_bank_code": "50211"
}
```

**Failure response (200 with valid=false or 4xx):**

```json
{
  "valid": false,
  "error": "Session UUID already used (replay)"
}
```

### Verification steps (your backend MUST implement)

1. Look up `terminal_id` in merchant registry — reject unknown terminals.
2. Reject if `payload.timestamp_ms` is missing or not a positive integer (`Missing timestamp_ms in payload`).
3. Validate `timestamp_ms` within ±10 minutes of server time.
4. Reject if `session_uuid_v4` was already used for this terminal (replay).
5. Verify signature:
   - **HMAC-SHA256:** recompute HMAC over canonical payload JSON with terminal `signing_key`
   - **Ed25519:** verify detached signature with terminal `public_key` (CheckoutPay Pay at shop)
6. Verify `bank_name_hash` matches registered merchant.
7. Return merchant display name and **full recipient account** from registry (not from untrusted BLE fields alone).
8. Mark session UUID as consumed **before** returning success (or allow idempotent retries — CheckoutPay allows retry after successful verify).

Reference implementation: [`bank_api/server.py`](../bank_api/server.py)

### `POST /terminals/register` (merchant onboarding)

**Requires header:** `X-Admin-Key: <CHECKOUT_BANK_ADMIN_KEY>`

Used when a shop registers their POS with the bank. Not called from consumer banking apps.

Example:

```bash
curl -X POST http://127.0.0.1:8090/terminals/register \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: change-me-before-production" \
  -d '{
    "terminal_id": "POS-LAG-001",
    "signing_key": "your-terminal-key-min-16-chars",
    "merchant_name": "ABC Enterprises",
    "bank_name": "kuda",
    "masked_account_suffix": "***9876",
    "account_number": "0123456789",
    "recipient_bank_code": "50211"
  }'
```

---

## 9. Hook into your existing transfer / debit flow

After `onPaymentReceived`, call your **existing** transfer API. Pass `session_uuid` for idempotency:

```kotlin
// Pseudocode — adapt to your API
suspend fun completeBroadcastPayment(payment: VerifiedPayment) {
    val verifyResponse = bankApi.verifyBroadcast(...)  // SDK already did this
    transferApi.initiateTransfer(
        recipientAccount = verifyResponse.recipientAccount,
        recipientBankCode = verifyResponse.recipientBankCode,
        amountNgn = payment.amountNgn,
        idempotencyKey = payment.sessionUuid,
        narration = "Payment at ${payment.merchantName}",
    )
}
```

The broadcast SDK verifies intent and amount integrity. **Money movement stays in your existing payment rails.**

---

## 10. Error handling

| Error | Meaning | UX |
|-------|---------|-----|
| `Missing timestamp_ms in payload` | POS/app dropped required field | "Ask cashier to send payment again" |
| `VerificationError` | Bad signature, replay, or expired timestamp | "Could not verify shop payment. Enter details manually." |
| `TransportError` | BLE off or unsupported | Prompt to enable Bluetooth |
| `RoleNotAllowedError` | Dev misconfiguration | Fix SDK config — not user-facing |

```typescript
onError: (error) => {
  if (error.name === "VerificationError") {
    showToast("Payment request could not be verified");
  } else {
    showToast("Bluetooth unavailable — use manual transfer");
  }
  navigateToManualTransfer();
}
```

---

## 11. Security checklist for banks

- [ ] Terminal registry with revocable signing keys
- [ ] Session UUID replay table (per terminal, TTL ≥ 10 min)
- [ ] Server-side signature verification — never trust client-only checks
- [ ] Return recipient account from registry, not from BLE payload alone
- [ ] Rate-limit `/verify-broadcast` per device/IP
- [ ] Audit log: terminal_id, session_uuid, amount, customer device id
- [ ] Amount shown to customer must match verified `amount_ngn`

---

## 12. Testing without hardware

### Simulated transport (same device / CI)

```bash
# Terminal 1
PYTHONPATH="sdk/python:." python -m checkout_broadcast.cli run-bank
PYTHONPATH="sdk/python:." python -m checkout_broadcast.cli register-terminal

# Terminal 2 — acts as POS
PYTHONPATH="sdk/python:." python -m checkout_broadcast.cli demo-send

# Your banking app integration tests can mock POST /verify-broadcast
```

### Web demo

```bash
cd checkout_broadcast/demos/web-receiver
python3 -m http.server 8080
# Open http://localhost:8080 — Start listening → Simulate incoming packet
```

Point `bankApiUrl` at `http://127.0.0.1:8090` during development.

---

## 13. Go-live checklist

1. [ ] `/verify-broadcast` deployed to production with registry DB
2. [ ] Android/iOS BLE permissions and App Store privacy strings approved
3. [ ] Transfer screen pre-fill tested with real POS terminal
4. [ ] Replay attack tested (same packet twice → second rejected)
5. [ ] Tamper test (changed amount in packet → rejected)
6. [ ] Fallback manual transfer always available
7. [ ] Idempotency on debit API using `session_uuid`

---

## 14. FAQ

**Does this replace NIP/inter-bank transfer APIs?**  
No. It only pre-fills and verifies payment intent. Your existing debit/transfer API still moves money.

**Does the customer need internet?**  
Yes — for bank API verification. BLE delivers the broadcast; HTTPS verifies it.

**Can one banking app receive from any bank's POS?**  
Only if your bank verifies terminals registered with **your** registry. Cross-bank would require industry-wide terminal registry (future).

**PCI-DSS?**  
Broadcast contains masked suffix only. Full account resolution happens server-side. Consult compliance for your debit flow.

---

## 15. Related docs

- [POS app integration guide](pos-app-integration.md) — share with merchant / POS partners
- [Coexistence with proprietary nearby pay](../spec/coexistence-with-proprietary-nearby.md)
- [Signing rules](../spec/signing-rules.md)
- [BLE transport](../spec/ble-transport.md)
- [Unified addon API](../spec/addon-api.md)
- [Golden conformance fixtures](../tests/fixtures/)
- [Mock bank server reference](../bank_api/server.py)
- Future wallet P2P: [wallet-broadcast v2.1 draft](../spec/wallet-broadcast-v2.1-draft.md)
