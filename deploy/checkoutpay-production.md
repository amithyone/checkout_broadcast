# CheckoutPay production — Broadcast verify API

Deploy the reference [`bank_api/`](../bank_api/) for CheckoutNow and merchant POS terminals on **check-outpay.com**.

## Recommended production paths

| Endpoint | Method | Auth |
|----------|--------|------|
| `/api/v1/broadcast/verify-broadcast` | POST | Public (rate-limited) |
| `/api/v1/broadcast/terminals/register` | POST | Admin key / staff auth |
| `/api/v1/broadcast/terminals/{id}` | GET | Admin |
| `/api/v1/broadcast/health` | GET | Public |

Mobile app default: `EXPO_PUBLIC_CHECKOUT_BROADCAST_API=https://check-outpay.com/api/v1/broadcast`

**Implementer guide:** [docs/checkoutpay-integration.md](../docs/checkoutpay-integration.md)  
**Verify contract:** [spec/verify-api.md](../spec/verify-api.md)  
**Production Laravel source of truth:** `checkout/BROADCAST_VERIFY_API.md` in the CheckoutPay repo (Option B deploy).

## Option A — Sidecar (fastest)

Run the Python FastAPI server beside Laravel on the dev/staging box:

```bash
cd checkout_broadcast
cp .env.example .env
# CHECKOUT_BANK_ADMIN_KEY, CHECKOUT_BIND_PUBLIC=false, CHECKOUT_BANK_DB=/var/lib/checkout/broadcast.db

pip install -r requirements.txt
PYTHONPATH="sdk/python:." python -m checkout_broadcast.cli run-bank
```

Reverse-proxy `/api/v1/broadcast/` → `127.0.0.1:8090` in Apache/nginx.

## Option B — Laravel native (recommended for live)

Copy [`deploy/laravel/BroadcastVerifyController.php`](laravel/BroadcastVerifyController.php) into the checkout Laravel app:

1. Run migration [`deploy/laravel/migration_broadcast_terminals.sql`](laravel/migration_broadcast_terminals.sql) on MySQL.
2. Register routes from [`deploy/laravel/routes-snippet.php`](laravel/routes-snippet.php) in `routes/api.php`.
3. Set `.env`:
   ```
   BROADCAST_ADMIN_KEY=...
   BROADCAST_RATE_LIMIT_VERIFY=120
   ```
4. Link POS terminals to existing `businesses` rows via `terminal_id`.

## Register a test terminal

```bash
export CHECKOUT_BANK_ADMIN_KEY="your-admin-key"
export CHECKOUT_SIGNING_KEY="your-terminal-secret-min-16-chars"
PYTHONPATH="sdk/python:." python -m checkout_broadcast.cli register-terminal \
  --bank-url https://check-outpay.com/api/v1/broadcast
```

## Verify from CLI

```bash
PYTHONPATH="sdk/python:." python -m checkout_broadcast.cli demo-send \
  --amount 2500 --bank-url https://check-outpay.com/api/v1/broadcast
```

## Security checklist

- [ ] HTTPS only in production (`require_https=True` in mobile SDK config)
- [ ] Admin registration behind staff auth, not public internet
- [ ] Rate limit verify endpoint per IP
- [ ] Signing keys in vault/HSM — not in git
- [ ] Session replay table persisted (MySQL/SQLite)
- [ ] CORS restricted to wallet app origins if browser SDK used

## Docker (staging)

```bash
docker compose -f deploy/docker-compose.prod.yml up --build
curl http://127.0.0.1:8090/health
```

## Local smoke test (before production deploy)

```bash
cd checkout_broadcast
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./deploy/smoke-test.sh
```

Validates register-terminal → demo-send → verify-broadcast against the reference `bank_api`.
