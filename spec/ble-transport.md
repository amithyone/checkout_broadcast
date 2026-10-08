# BLE transport (Checkout Broadcast)

This is the **production path used by CheckoutNow / Cheko Pay at shop**. Wallet apps and POS integrators should implement this shape first.

## GATT

| Role | UUID |
|------|------|
| Service | `cbbc0001-0000-4000-8000-000000000001` |
| Packet characteristic (**read**) | `cbbc0002-0000-4000-8000-000000000001` |

UTF-8 JSON on the packet characteristic. Keep under **~512 bytes** (typical Android GATT MTU). Receivers strip trailing `\u0000` padding before parsing.

## Receiver: finding tills and reading the packet

This is what CheckoutNow does on Android and iOS against Cheko Windows tills. The Android and iOS SDKs (`BleCheckoutReceiver` / `CheckoutBleReceiver`) follow it.

1. **Scan without an OS service-UUID filter.** Many Windows POS Bluetooth adapters don't put the service UUID in the advert, so hardware filters (`ScanFilter.setServiceUuid`, `scanForPeripherals(withServices:)`) miss them. Treat an advert as a Checkout Broadcast till when any of these match:
   - `cbbc0001-…` is in the advertised service UUIDs, or
   - `cbbc0001-…` is a key in the advert service data, or
   - the advertised local name (upper-cased) contains `CHECKOUT` or `CHEKO`, or starts with `CP-` or `CN`.
2. **Use the packet from the advert when it is there.** If the service data under `cbbc0001-…`, or the manufacturer data, starts with `{`, that is the signed packet — no connection needed.
3. **Otherwise do a silent read.** Connect (LE, no auto-connect, 12 s timeout), request MTU 512 on Android (iOS negotiates automatically), discover the service, **read** `cbbc0002-…`, disconnect.
   - **Never** enable notify/indicate. Writing the CCCD often forces an Android pairing dialog.
   - **Never** bond/pair. Verification happens on the server with the packet JSON.
   - Connect to one till at a time; queue the rest.
4. **Pace and dedupe.** Wait 4 s before reading the same till again. Skip a `session_uuid` you have already handled; clear that list each time the pay-at-shop screen opens.
5. **Permissions.** Android 12+: `BLUETOOTH_SCAN` + `BLUETOOTH_CONNECT` (older: Bluetooth + fine location). iOS: `NSBluetoothAlwaysUsageDescription`. iOS only allows unfiltered scans in the foreground, so listen while the pay-at-shop screen is open.

### Sender (POS) advert recommendations

To be found by every receiver, a till should:

- include `cbbc0001-…` in the advert service UUID list where the Bluetooth stack allows it, and
- advertise a local name starting with `CP-` (Cheko uses the terminal ID, e.g. `CP-1RK8Z`) or containing `CHECKOUT`, and
- expose `cbbc0002-…` as **readable** without encryption or pairing.

Optional, for shops with several tills side by side:

- include the standard advert **Tx Power Level** field (AD type `0x0A`; on Windows `BluetoothLEAdvertisementPublisher.IncludeTransmitPowerLevel`). Receivers may log it; they don't require it. Do **not** add transmit power to the signed packet.
- consider a lower transmit power so a till is not heard across the shop. Test with real phones first — too low and customers at the counter miss it.

## Proximity filtering (optional, recommended)

A phone near the counter can hear tills across the shop. Receivers should list only tills that are in range, and **must never auto-select or auto-pay because a till seems close** — RSSI varies by about 10 dB with phone model, grip and bodies in the way. The customer always taps a till, checks the bank-verified shop name, and confirms with PIN or biometrics. That includes tills named in a push notification: they are listed first, never opened automatically.

Reference implementations: Python `checkout_broadcast.proximity.TillProximityFilter`, Android `TillProximity`, iOS `TillProximity`. Conformance vectors: [`tests/fixtures/proximity_vectors.json`](../tests/fixtures/proximity_vectors.json).

| Rule | Default |
|------|---------|
| Smooth RSSI per till with an exponential moving average: `s = α·rssi + (1−α)·s_prev` (first sample `s = rssi`). Ignore `rssi ≥ 0` (Android/iOS report `127` when unknown). | `α = 0.3` |
| A till is **in range** when `s ≥ T` **and** `s ≥ s_strongest − W` (keeps adjacent tills, hides the far side of the shop). | `T = −75 dBm`, `W = 12 dB` |
| **Hysteresis:** a shown till is hidden only after `s < T − H` or `s < s_strongest − W − H` continuously for `D`. Inside the `H` band it stays shown. | `H = 5 dB`, `D = 3 s` |
| **Stale:** a till not heard for `S` is dropped. | `S = 10 s` |
| A till named in a push (`terminal_id` / `session_uuid`) is always listed, sorted first. | — |
| Sort visible tills: push-named first, then `s` (strongest first), then terminal label. | — |
| **Fallback:** if nothing is in range but tills were heard, show "Move closer to the till" and a "Show farther tills (N)" link. Never hide the right till for good. | — |
| Don't GATT-peek tills with `s < P` (clearly far away). | `P = −90 dBm` |

Distance in metres (`10^((txPower − s) / (10·n))`) is for logs only; it is not reliable enough to decide anything.

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

Expand rules (exactly what the till signed):

- `session_kind` only when `k` is sent: `presence` / `idle` / `beacon` → `presence`; `pos_checkout` / `checkout` → `pos_checkout`.
- `account_info_public_display.masked_account_suffix` only when `msk` is non-empty.
- `total_amount_ngn` = integer `amt` (kobo), or `0` for presence.
- `protocol_version` = `v`, default `2.1`. `signature_alg` = `alg`, default `ed25519` (legacy full envelopes default to `HMAC-SHA256`).

Conformance vectors every expander must match: [`tests/fixtures/wire_vectors.json`](../tests/fixtures/wire_vectors.json).

Reference expanders:

- CheckoutNow app: `expandWireToVerifyPacket` (React Native) / `_normalizeBroadcastJson` (Flutter)
- Android SDK: `BroadcastWire.parse` · iOS SDK: `BroadcastWire.parse`
- TypeScript SDK: `normalizeBleReadForVerify` in `@checkout-broadcast/web`
- Python SDK: `checkout_broadcast.wire_format.normalize_ble_read_for_verify` · reference bank: `bank_api/ble_wire.py`
- Demo: [`demos/web-receiver/ble-wire-expand.js`](../demos/web-receiver/ble-wire-expand.js) → `normalizeBleReadForVerify`
- Laravel: `BroadcastVerifyController::normalizeBlePacket`

## Amount units (kobo)

For compact wire packets:

- Signed `total_amount_ngn` / wire `amt` = **integer kobo**
- Wallet UI and bank transfer amount = **kobo ÷ 100** (major Naira)
- Legacy full envelopes may still use whole Naira — detect via wire vs legacy shape

## Presence / replay

- Presence: amount `0` / omitted — customer types amount in the wallet
- Receivers do not reject packets on age locally: a session stays open until paid or cancelled, and the server decides
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
