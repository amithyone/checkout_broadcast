# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |

## Reporting a vulnerability

**Do not open public GitHub issues for security vulnerabilities.**

Email security reports to your project maintainer (configure before public launch) or use GitHub private vulnerability reporting if enabled.

Include:
- Description of the issue
- Steps to reproduce
- Impact assessment
- Suggested fix (if any)

We aim to acknowledge reports within 72 hours.

## Threat model

Checkout Broadcast assumes:

- **Integrity** of amount and terminal ID via HMAC-SHA256 (required)
- **Replay protection** via timestamp + one-time session UUID (required)
- **Account confidentiality** is NOT provided over BLE — payloads are signed but not encrypted
- **Recipient account resolution** must come from the bank registry, not from the BLE packet alone

## Reference bank API — production warnings

The included `bank_api/` server is a **testing reference**, not production infrastructure.

Before bank rollout:

| Item | Reference server | Production requirement |
|------|------------------|------------------------|
| Signing key storage | SQLite plaintext | HSM / vault / KMS |
| Admin auth | `X-Admin-Key` header | mTLS, OAuth, IP allowlist |
| Replay store | SQLite | HA database with TTL |
| Rate limiting | In-memory per IP | WAF / API gateway |
| TLS | HTTP localhost | HTTPS everywhere |
| Default admin key | `change-me-before-production` | Strong random secret |

## SDK security guidelines

### POS apps (send role)

- Store `signing_key` in OS secure storage — never in source code or web bundles
- Use `require_https=True` in production config
- Broadcast only after checkout completion
- Revoke terminal keys when devices are lost

### Banking apps (receive role)

- Always verify via bank backend — never trust BLE data alone
- Lock transfer amount when verification succeeds
- Use `session_uuid` as idempotency key for debit API
- Offer manual transfer fallback when verification fails

## BLE considerations

BLE GATT payloads are **readable by any nearby device**. The signature prevents tampering but not observation. Do not include full account numbers in broadcast payloads.

## Secrets in this repository

Never commit:

- `.env` files with real keys
- `data/*.db` with production terminals
- `dev_registry.json` (deprecated — use SQLite via `CHECKOUT_BANK_DB`)

See `.gitignore`.
