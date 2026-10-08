# Checkout Broadcast — one-page overview

**An open protocol that lets a shop till send a signed payment request to the customer's banking app over Bluetooth, so the transfer opens pre-filled with the right merchant and amount.**

MIT licensed · In production with CheckoutNow and Cheko / CheckoutPay · [github.com/amithyone/checkout_broadcast](https://github.com/amithyone/checkout_broadcast)

---

## The problem

At Nigerian counters, "pay by transfer" is the default, and it is slow and error-prone:

- The customer types a 10-digit account number, picks a bank, and types the amount while a queue waits.
- Mistyped accounts and amounts cause failed or misdirected transfers.
- Merchants and POS agents wait on "I've sent it" with no reliable way to match the payment to the sale.
- QR codes help, but the customer has to open a scanner and aim it, and static QR codes carry no amount.

## How it works

1. **Till:** the POS totals the sale and broadcasts a packet over Bluetooth LE containing the terminal ID, amount (in kobo), a one-time session ID, and an Ed25519 signature.
2. **Bank:** the customer's banking app forwards the packet to its bank's `/verify-broadcast` endpoint. The bank checks the signature against the registered terminal key, rejects replays and stale packets, and returns the merchant name and account.
3. **Customer:** the transfer screen opens pre-filled with a locked amount. The customer confirms with their PIN, and the bank sends a normal transfer using the session ID as the idempotency key.

The money moves over existing rails (NIP). Checkout Broadcast only changes how the transfer is started.

## Why it matters

| For | Benefit |
|-----|---------|
| Banks and wallets | Fewer mistyped transfers and disputes, a modern in-store experience, no new settlement rail |
| POS software and PTSPs | A small add-on for Android or Windows/Linux POS apps; most modern Android POS terminals have Bluetooth |
| POS agents and merchants | Shorter queues, exact amounts, a reference to match each payment |

It complements NQR rather than competing with it: no camera, no printed code, and the amount comes signed from the till.

## Security model

- **Integrity:** the till signs the full payload with Ed25519. The bank holds only the public key. Changing the amount breaks the signature.
- **Authenticity:** only terminals registered with the bank verify. A fake till broadcasting its own account fails.
- **Replay protection:** each checkout session ID is burned after use, and stale timestamps are rejected.
- **Privacy:** packets are signed, not encrypted, so they carry only a masked account suffix. The full account comes from the bank, never from the packet.

Details: [SECURITY.md](../SECURITY.md).

## What integration involves

**Banks and wallets**
1. Add a `POST /verify-broadcast` endpoint (reference implementations in Python/FastAPI and Laravel). See the [verify API spec](../spec/verify-api.md).
2. Add a terminal registry where merchants or PTSPs register till public keys.
3. Add a "Pay at shop" screen in the app that scans for broadcasts (Android and iOS receive modules are included).

**POS software and PTSPs**
1. Generate an Ed25519 key per terminal and register the public key with the bank or aggregator.
2. After checkout, call the SDK to broadcast the signed packet (Python SDK for Windows/Linux today; Android send path in progress).
3. Optionally broadcast a "presence" packet while idle so customers can pay any amount.

Guides: [banking apps](banking-app-integration.md) · [POS apps](pos-app-integration.md) · [BLE wire format](../spec/ble-transport.md)

## Status

- **In production:** CheckoutNow wallet ("Pay at shop") and Cheko / CheckoutPay merchant tills with a Laravel verify backend.
- **Ready:** Python POS SDK (send and receive), TypeScript receive SDK, Android and iOS receive modules, reference bank API, conformance tests.
- **In progress:** Android and iOS send (POS on phone), PyPI and npm packages.

## What we're looking for

- **Banks and wallets** willing to run a pilot with a handful of merchants.
- **PTSPs and POS app makers** willing to add the broadcast to one terminal model.
- **NIBSS and Open Banking Nigeria** feedback on making this a shared standard for proximity payment initiation.

**Contact:** [GitHub Discussions](https://github.com/amithyone/checkout_broadcast/discussions) · amithyone@gmail.com
