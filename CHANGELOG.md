# Changelog

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
