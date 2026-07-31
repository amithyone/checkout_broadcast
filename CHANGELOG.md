# Changelog

## [1.1.0] - 2026-07-30

### Added
- **Ed25519** signing and verification (CheckoutPay / CheckoutNow Pay at shop profile)
- `parse_timestamp_ms` / `parseTimestampMs` helpers — clear error when field is missing
- [spec/verify-api.md](spec/verify-api.md) — full `/verify-broadcast` contract and error strings
- [docs/checkoutpay-integration.md](docs/checkoutpay-integration.md) — CheckoutPay implementer guide
- Reference bank API: Ed25519 terminal registration, `Missing timestamp_ms in payload` error
- Tests: `tests/test_ed25519.py`, bank API Ed25519 + missing timestamp coverage

### Changed
- Python/TypeScript receiver SDKs reject packets without `timestamp_ms` before calling bank API
- Python POS config accepts `signature_alg="ed25519"` with dashboard signing key
- [spec/signing-rules.md](spec/signing-rules.md) documents Ed25519 and required `timestamp_ms`
- Banking app integration guide updated for dual signature algorithms

### Dependencies
- Python SDK now requires `PyNaCl>=1.5` for Ed25519

## [1.0.0] - 2026-07-18

### Added
- Open-source release under MIT license
- Production-hardened reference bank API (SQLite, admin auth, rate limiting, health endpoints)
- Python SDK config validation and HTTPS enforcement option
- Expanded test suite (bank API, schema, cross-SDK signing parity)
- Docker Compose for bank testing
- GitHub Actions CI
- SECURITY.md, CONTRIBUTING.md, root README

### Changed
- Bank API uses SQLite persistence instead of broken JSON registry path
- Terminal registration requires `X-Admin-Key` header
- CLI uses environment variables for secrets (no hardcoded production keys)
- Verify response includes `recipient_account` and `recipient_bank_code`

### Security
- Replay sessions persist across server restarts (SQLite)
- Rate limiting on `/verify-broadcast`
- Admin endpoints protected; public verify endpoint documented

### Known limitations
- Android/iOS send path still phase 2
- Python BLE peripheral requires Windows/Linux + bleak
- Reference bank API is for testing — banks must deploy hardened infrastructure
