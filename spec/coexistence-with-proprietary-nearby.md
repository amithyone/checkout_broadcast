# Coexistence: Checkout Broadcast vs CheckoutNow Nearby Pay

CheckoutNow ships **two independent Bluetooth payment systems**. They must not share UUIDs, payloads, or verification APIs.

## Checkout Broadcast (this open spec)

| Item | Value |
|------|--------|
| **Purpose** | POS terminal → customer wallet app (shop checkout) |
| **Audience** | OPay, Kuda, GTBank, CheckoutNow, any implementing wallet |
| **BLE** | GATT service `cbbc0001-0000-4000-8000-000000000001` |
| **Payload** | Signed JSON (HMAC-SHA256, protocol v2.0) |
| **Trust** | `POST /verify-broadcast` on each bank/wallet backend |
| **Sender** | Windows/Linux POS (Python SDK) |
| **Receiver** | Mobile wallet apps (`role: receive`) |

See [ble-transport.md](./ble-transport.md), [signing-rules.md](./signing-rules.md), [banking-app integration guide](../docs/banking-app-integration.md).

## CheckoutNow Nearby Pay (proprietary, not part of this spec)

| Item | Value |
|------|--------|
| **Purpose** | CheckoutNow ↔ CheckoutNow wallet P2P |
| **Audience** | CheckoutNow app only |
| **BLE** | Advertisement scan, service `a7c5c816-4b3a-4e2a-9f1d-8e2b4c6d8f0a` |
| **Payload** | Short pay code (5–6 chars) in manufacturer data |
| **Trust** | CheckoutNow `scan-resolve` + `p2p` APIs |
| **Docs** | CheckoutNow repo `docs/NEARBY_SEND.md` |

## Rules for implementers

1. **Do not** reuse Nearby Pay UUIDs or pay-code format in Checkout Broadcast packets.
2. **Do not** route Broadcast packets through CheckoutNow `scan-resolve` — wrong trust model.
3. Wallet apps may implement **Broadcast receive only** without supporting Nearby Pay.
4. CheckoutNow keeps Nearby Pay unchanged when adding Broadcast “Pay at shop” — separate UI and BLE stack.
5. Future cross-app wallet broadcasts (protocol v2.1 `wallet_receive`) are optional and documented separately; POS v2.0 remains stable.

## UUID summary

| System | Service UUID |
|--------|----------------|
| Checkout Broadcast | `cbbc0001-0000-4000-8000-000000000001` |
| CheckoutNow Nearby Pay | `a7c5c816-4b3a-4e2a-9f1d-8e2b4c6d8f0a` |

No collision — both may run on the same phone without conflict if permissions allow.
