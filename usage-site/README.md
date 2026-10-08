# Public usage stats (Vercel)

Anonymous `ok` counter for [amithyone.github.io/checkout_broadcast](https://amithyone.github.io/checkout_broadcast/). No amounts, accounts, or terminals.

Anonymous POST is **rejected**. Only an enrolled **verify server** (bank, PSB, MMO, or CheckoutPay) with a secret token can increment. Listing every CBN bank on this hostname would not stop spam — anyone can still POST. Ownership of the verify hostname is proven over HTTPS instead.

## Deploy

1. Vercel project, **Root Directory** `usage-site`.
2. KV / Upstash Redis: `KV_REST_API_URL` + `KV_REST_API_TOKEN` (or Upstash Redis REST pair).
3. `USAGE_ADMIN_SECRET` — min 16 chars, used only to enroll reporters.
4. Production URL: `https://checkout-broadcast-stats.vercel.app`

## Enroll a bank verify host

The bank publishes:

`https://<verify-host>/.well-known/checkout-broadcast-usage.json`

```json
{ "host": "api.example-bank.com", "name": "Example Bank" }
```

Then the maintainer:

```http
POST /usage/enroll
Authorization: Bearer <USAGE_ADMIN_SECRET>
Content-Type: application/json

{ "host": "api.example-bank.com", "name": "Example Bank" }
```

Vercel fetches that well-known file over HTTPS (must match `host`) and returns a **one-time** token. Put it on the bank server as `CHECKOUT_USAGE_STATS_TOKEN`. Never commit it.

Who may be enrolled: CBN-licensed deposit banks, PSBs, MMOs / wallets, and merchant verify hosts such as CheckoutPay — each with a live `/verify-broadcast`. Not every `.ng` website, and not phones or POS apps.

## Hit

```http
POST /usage/hit
Authorization: Bearer <CHECKOUT_USAGE_STATS_TOKEN>
Content-Type: application/json

{}
```

No token → 401, count unchanged. Rate-limited per token.

## Public

`GET /usage/public` → `{ ok, ok_count, reporters: [{ host, name }] }`

Reporters are enrolled verify hosts only. Git never stores tokens or payments.
