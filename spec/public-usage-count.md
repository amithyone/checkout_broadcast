# Public usage count (anonymous `ok`)

Open-source protocol **does not** see live BLE. To show how many Pay at shop checkouts succeeded, verify servers send a **hit**, not a transaction.

The public host is **Vercel** (`usage-site/` in this repo). GitHub Pages only **displays** the number. Git never stores payments, tokens, or the running total.

Default URL: `https://checkout-broadcast-stats.vercel.app`

## Why a CBN bank-name list is not enough

Anyone can `POST` to a public URL. Putting “all Nigerian banks” on the stats hostname (or in git) does **not** prove the caller is a bank. `Origin` / `Referer` / `Host` headers are also not proof.

What we require instead:

1. The caller is a **verify server** that already runs `POST /verify-broadcast`.
2. That server **owns an HTTPS hostname** (not a phone, not a till, not `localhost`).
3. The maintainer **enrolls** that hostname after a well-known file check.
4. Hits carry a **secret token** issued at enroll. No token → 401, count unchanged.

Eligible reporters: CBN-licensed deposit money banks, PSBs, MMOs / wallets, and merchant verify hosts such as CheckoutPay. Enroll is manual; the public page lists **enrolled reporters**, not the full CBN directory.

## Rule

| Event | Count |
|-------|--------|
| Enrolled verify server: checkout `valid: true` (amount &gt; 0) | **+1** |
| Presence / idle (`amt` omitted or 0) | **do not** count |
| Failed verify, unknown token, browser, POS, wallet app | **do not** count |

Body of the hit: **nothing useful**. No amount, account, terminal, session, or signature.

```http
POST /usage/hit
Authorization: Bearer <CHECKOUT_USAGE_STATS_TOKEN>
Content-Type: application/json

{}
```

Response:

```json
{ "ok": true, "ok_count": 1284, "host": "api.example-bank.com" }
```

Public read (landing + README badge):

```http
GET /usage/public
```

```json
{
  "ok": true,
  "ok_count": 1284,
  "reporters": [
    { "host": "api.check-outpay.com", "name": "CheckoutPay" }
  ]
}
```

## Domain proof (enroll)

On the **bank’s verify host**, not on Vercel:

`https://<verify-host>/.well-known/checkout-broadcast-usage.json`

```json
{ "host": "api.example-bank.com", "name": "Example Bank" }
```

Maintainer calls `POST /usage/enroll` with `USAGE_ADMIN_SECRET`. Vercel fetches the file over HTTPS; `host` must match. Token is returned once.

## Who must call it

| Implementer | What to do |
|-------------|------------|
| Bank using this `bank_api` / CheckoutPay Laravel snippet | After enroll, set `CHECKOUT_USAGE_STATS_URL` and `CHECKOUT_USAGE_STATS_TOKEN`. Checkout `valid: true` forwards automatically. |
| Bank with **their own** verify | Same token on their server. `POST /usage/hit` once per successful checkout. |
| Wallet / POS apps | **Do not** ping. Only the verify **server**. |

## GitHub

GitHub Pages cannot receive POSTs. The landing fetches `GET /usage/public`. Deploy: [usage-site/README.md](../usage-site/README.md).
