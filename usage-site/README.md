# Public usage stats (Vercel)

Anonymous `ok` counter for [amithyone.github.io/checkout_broadcast](https://amithyone.github.io/checkout_broadcast/). No amounts, accounts, or terminals.

## Deploy

1. Create a Vercel project with **Root Directory** `usage-site`.
2. Add an Upstash Redis / Vercel KV store and these env vars:
   - `KV_REST_API_URL` and `KV_REST_API_TOKEN`, **or**
   - `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`
3. Suggested production URL: `https://checkout-broadcast-stats.vercel.app`
4. Import the GitHub repo `amithyone/checkout_broadcast` so pushes to `main` redeploy.

```bash
cd usage-site
npx vercel --prod
```

## Endpoints

| Method | Path | Who |
|--------|------|-----|
| `GET` | `/usage/public` | Landing page, README badge |
| `POST` | `/usage/hit` body `{}` | Verify **servers** after a successful checkout (not presence) |

Phones and POS apps must not call this. Git never stores the count.

## Banks

Set `CHECKOUT_USAGE_STATS_URL` on the verify host (Python `bank_api` and Laravel snippet forward automatically). Own-language verify: `POST` empty JSON once per successful checkout.
