# Checkout Broadcast — Integration Overview

Checkout Broadcast lets Nigerian businesses accept payments without customers typing account numbers manually. After a POS checkout completes, a **signed broadcast** is sent over BLE. The customer's **banking app** receives it, verifies it with your bank API, and pre-fills the transfer screen.

## Who integrates what

| App type | Role | SDK | Typical platform |
|----------|------|-----|------------------|
| **POS / shop terminal** | `send` | Python SDK | Windows, Linux |
| **Banking / wallet app** | `receive` | Android, iOS, Web SDK | Android, iOS, browser |

## Documentation

- **[POS app integration guide](pos-app-integration.md)** — for shop terminals, Windows POS, merchant dashboards
- **[Banking app integration guide](banking-app-integration.md)** — for Kuda, OPay, GTBank, and other wallet/banking apps
- **[CheckoutPay integration guide](checkoutpay-integration.md)** — Pay at shop on `check-outpay.com` (Ed25519, dashboard credentials)
- **[Verify API contract](../spec/verify-api.md)** — request/response and error strings for `/verify-broadcast`
- **[Unified addon API](../spec/addon-api.md)** — cross-platform API contract
- **[Signing rules](../spec/signing-rules.md)** — HMAC-SHA256 and Ed25519 verification
- **[BLE transport](../spec/ble-transport.md)** — GATT service UUIDs and radio flow

## End-to-end flow

```
POS checkout complete
    → SDK signs payload (amount + terminal ID + session UUID)
    → BLE broadcast (or simulated in dev)
    → Banking app receives packet
    → Banking app calls YOUR bank API: POST /verify-broadcast
    → Bank API validates signature + replay + merchant registry
    → Banking app pre-fills transfer UI
    → Customer confirms with PIN / biometrics
    → Normal bank transfer API debits customer account
```

## Quick start (development)

```bash
cd checkout_broadcast
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Terminal 1 — mock bank API
PYTHONPATH="sdk/python:." python -m checkout_broadcast.cli run-bank

# Terminal 2 — register merchant terminal + send checkout
PYTHONPATH="sdk/python:." python -m checkout_broadcast.cli register-terminal
PYTHONPATH="sdk/python:." python -m checkout_broadcast.cli demo-send --amount 2500
```

## Security model (summary)

- **Integrity:** HMAC-SHA256 or Ed25519 over canonical JSON — amount cannot be tampered in transit
- **Replay:** 10-minute timestamp window + one-time session UUID per terminal
- **Spoofing:** Terminal must be registered in bank merchant registry before broadcast is accepted
- **Confidentiality:** Account numbers are masked in the broadcast; full details come only from bank API after verification

## Support matrix

| Platform | POS send | Banking receive |
|----------|----------|-----------------|
| Windows | Python + BLE | — |
| Linux | Python + BLE | Python + BLE |
| macOS | Simulated dev only | Web Bluetooth / iOS |
| Android | Phase 2 | Android SDK (BLE scan) |
| iOS | Phase 2 | iOS SDK (CoreBluetooth) |
| Web | — | TypeScript / browser bundle |
