# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.3.x   | Yes       |
| < 1.3   | No        |

## Reporting a vulnerability

**Do not open public GitHub issues for security vulnerabilities.**

Report privately through [GitHub private vulnerability reporting](https://github.com/amithyone/checkout_broadcast/security/advisories/new), or email **amithyone@gmail.com** with the subject `checkout_broadcast security`.

Include:
- Description of the issue
- Steps to reproduce
- Impact assessment
- Suggested fix (if any)

We aim to acknowledge reports within 72 hours.

## Threat model

Checkout Broadcast assumes:

- **Integrity** of amount, terminal ID, and session via a signature over the canonical payload (required). Ed25519 is the production default: the POS holds the private key and the bank stores only the public key. HMAC-SHA256 (shared secret) is supported for legacy and demo setups.
- **Replay protection** via timestamp + one-time session UUID (required). Presence (idle till, no amount) packets are not burned and must be re-signed with a fresh timestamp.
- **Account confidentiality** is NOT provided over BLE — payloads are signed but not encrypted
- **Recipient account resolution** must come from the bank registry, not from the BLE packet alone

### What an attacker can and cannot do

| Attack | Outcome |
|--------|---------|
| Fake till broadcasting its own account | Fails verify — terminal ID not registered, or signature doesn't match the registered key |
| Change the amount in a captured packet | Fails verify — signature covers the amount |
| Rebroadcast a captured checkout packet | Fails verify after first use — session UUID is burned; stale timestamps rejected |
| Read packets nearby | Possible — only masked account suffix and amount are exposed |
| Stolen POS device | Can broadcast until the terminal key is revoked at the bank — revoke on loss |
| Two tills nearby | Customer sees both with verified merchant names and picks one; the app should show the verified name before PIN entry |

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
