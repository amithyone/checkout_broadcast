# Public usage count (anonymous `ok`)

Open-source protocol **does not** see live BLE. To show how many Pay at shop checkouts succeeded, verify servers send a **hit**, not a transaction.

The public host is **Vercel** (`usage-site/` in this repo). GitHub Pages only **displays** the number. Git never stores payments or the running total.

Default URL: `https://checkout-broadcast-stats.vercel.app`

## Rule

| Event | Count |
|-------|--------|
| `POST /verify-broadcast` returns `valid: true` **and** checkout (amount &gt; 0) | **+1** |
| Presence / idle (`amt` omitted or 0) | **do not** count |
| Failed verify | **do not** count |

Body of the hit: **nothing useful**. No amount, account, terminal, session, or signature.

```http
POST /usage/hit
Content-Type: application/json

{}
```

Response:

```json
{ "ok": true, "ok_count": 1284 }
```

Public read (landing + README badge):

```http
GET /usage/public
```

```json
{ "ok": true, "ok_count": 1284 }
```

Each successful checkout = **one** increment.

## Who must call it

| Implementer | What to do |
|-------------|------------|
| Bank using this `bank_api` / CheckoutPay Laravel snippet | Set `CHECKOUT_USAGE_STATS_URL`. Checkout `valid: true` already +1 locally **and** forwards to Vercel. |
| Bank with **their own** verify in any language | After successful checkout verify, `POST` empty JSON to the Vercel `/usage/hit` once. |
| Wallet / POS apps | **Do not** ping from the phone. Only the verify **server**. |

Open source cannot cryptographically force forks. CheckoutPay (or a bank contract) can **require** this for production listings. A fork that never hits is simply not in the public total.

## GitHub

GitHub Pages cannot receive POSTs. The landing at [amithyone.github.io/checkout_broadcast](https://amithyone.github.io/checkout_broadcast/) fetches `GET /usage/public`. Deploy steps: [usage-site/README.md](../usage-site/README.md).
