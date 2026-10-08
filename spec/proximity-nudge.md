# Shop-nearby alerts (optional)

Lets a customer's phone say "MIDAS AGRO is open — tap to pay" when they walk up to a till. Optional for banks; nothing in the checkout or verify flow depends on it.

The alert only **opens the till list** (Pay at shop). It never selects a till, fills an amount, or pays. The customer still taps their till, checks the bank-verified shop name and confirms with PIN or biometrics.

## Flow

1. The phone listens quietly for tills (Android only — see [Phones](#phones)).
2. When a till is near (smoothed RSSI ≥ −80 dBm), the phone reports it to the bank server.
3. The server looks up the shop, debounces, and sends a push with `type=pay_at_shop`.
4. If the server says it did not push (`notified: false`), the phone may show the same text as a local notification.
5. Tapping either notification opens the Pay at shop list, with the named till listed first.

## `POST {broadcastApi}/proximity`

Authenticated as the signed-in customer (`Authorization: Bearer …`). `{broadcastApi}` is the same base as `/verify-broadcast` (e.g. `https://bank.example/api/v1/broadcast`).

Request:

```json
{
  "terminal_id": "CP-1RK8Z",
  "session_uuid": null,
  "rssi": -68,
  "source": "background",
  "platform": "android"
}
```

| Field | Notes |
|-------|-------|
| `terminal_id` | Hint from the advert local name when it starts with `CP-` (Cheko advertises the terminal ID). `null` when unknown. Never trust it for payment — it is unsigned. |
| `session_uuid` | Set only when the phone already read the signed packet (foreground). |
| `rssi` | Smoothed dBm, for logs and server-side thresholds. |
| `source` | `background` (listener) or `foreground` (Pay at shop open). |
| `platform` | `android` or `ios`. |

Response (HTTP 200):

```json
{
  "ok": true,
  "notified": true,
  "merchant_name": "MIDAS AGRO",
  "title": "Checkout Nearby Available",
  "body": "MIDAS AGRO is open — tap to pay"
}
```

- `notified: true` — the server sent a push; the phone shows nothing itself.
- `notified: false` — no push (unknown till, cooldown, push disabled). The phone may show `title`/`body` locally; if `merchant_name` is missing, use a generic "A shop is open — tap to pay".
- `401` — session expired; stop listening until the app signs in again.

Server rules:

- Resolve `terminal_id` to the registered merchant name (never show a Bluetooth device name).
- Only alert for active tills whose merchant accepts Pay at shop.
- Debounce per customer and till (CheckoutPay uses a cooldown of several minutes).
- Push data: `type=pay_at_shop`, `terminal_id`, `merchant_name`.

## Phones

**Android.** A foreground service (type `connectedDevice`) with a quiet ongoing notification, switchable off in settings. Battery rules:

- `SCAN_MODE_LOW_POWER`, a hardware filter on service `cbbc0001-…`, and batched results (`setReportDelay(5000)`), so the OS can keep scanning with the screen off. Tills that only advertise a name are found by the foreground Pay at shop scan instead.
- No GATT connections in the background.
- Report each till at most once every 3 minutes, and at most 10 reports per hour.
- Pause while the app's own Pay at shop or Nearby Pay scan runs.

The Android SDK's `ShopNearbyScanner` implements the scan, smoothing and rate limits with no networking — the bank app decides what to do with each `ShopNearbyHit`.

**iPhone.** iOS does not allow background scans for arbitrary tills, so there is no background listener. Server pushes still arrive, and the Pay at shop screen works while open.
