# Changelog

## [1.4.2] - 2026-10-08

### Changed
- Public usage hits require an enrolled verify host: HTTPS well-known domain proof plus a secret bearer token. Anonymous POST no longer increments. The landing lists enrolled reporters, not the full CBN bank directory (a name list cannot authenticate HTTP callers).

## [1.4.1] - 2026-10-08

### Added
- Vercel public usage counter (`usage-site/`): `GET /usage/public`, `POST /usage/hit` with empty JSON. GitHub Pages landing reads the total; git does not store payments.
- GitHub Pages landing: language-agnostic protocol, Android POS send, live successful-checkout count.
- Reference bank API and Laravel example forward one `ok` to `CHECKOUT_USAGE_STATS_URL` after a successful checkout verify (not presence).

## [1.4.0] - 2026-10-08

Brings the open SDKs in line with the CheckoutNow app that runs against Cheko Windows tills in production. No change to the packet format, signing, or verify endpoint — existing tills and servers keep working.

### Fixed
- **Android and iOS SDKs can now read Cheko tills.** They required the old `payload` envelope and failed on the compact `{p, alg, sig}` packet; they now expand both shapes (`BroadcastWire`)
- Android and iOS SDKs no longer use an OS service-UUID scan filter, which missed many Windows POS adverts. They scan unfiltered and match the service UUID, service data, or advert name (`CHECKOUT`, `CHEKO`, `CP-`, `CN`)
- Android and iOS SDKs no longer reject packets older than 10 minutes; a till session stays open until paid or cancelled and the server decides
- Android and iOS SDKs treat a non-2xx status **or** `valid: false` as failure, read `error` / `message`, and accept a `data` wrapper and field aliases (`account_number`, `bank_code`, `session_uuid_v4`, `merchantName`)
- Python `wire_to_verify_envelope` invented `account_info_public_display` (`***0000`) and dropped `session_kind`, breaking signatures for idle tills and tills that send no `msk`; it now matches the TypeScript SDK, `bank_api/ble_wire.py`, and the app
- Python legacy-envelope default `signature_alg` is now `HMAC-SHA256`, matching the other SDKs
- Python `encode_wire_envelope` writes `msk` and `k` only when the signed payload has them (output unchanged for `build_minimal_online_payload`)
- Android SDK build: removed an invalid version on the core `maven-publish` plugin and added the missing Gradle wrapper

### Added
- Android/iOS receivers: packet taken from advert service/manufacturer data when embedded; otherwise a queued, one-at-a-time, **read-only** GATT peek (never notify, never bond), MTU 512 on Android, 12 s timeout, 4 s per-till cooldown
- `resetSeenSessions()`, `verifyPacketJson()`, `verifyHeaders` config, `VerifiedPayment.isPresence`, and `BroadcastWire.terminalLabel()` on Android and iOS
- Shared conformance vectors `tests/fixtures/wire_vectors.json`, checked by Python SDK, reference bank, TypeScript, Kotlin, and Swift tests
- CI jobs that build and unit-test the Android and iOS SDKs
- Specs/docs: how receivers find tills and read packets, POS advert recommendations, verify failure handling (HTTP 200 + `valid:false`), response aliases, and the CheckoutNow pay-at-shop UX (till picker, idle tills, push nudge, auto-select)

### Changed (Android / iOS API)
- `VerifiedPayment.amountNgn` is now a `Double` in naira taken from the signed packet (wire `amt` kobo ÷ 100), not the server's integer `amount_ngn`
- `VerifiedPayment.maskedAccountSuffix` is now optional

## [1.3.1] - 2026-10-08

First tagged public release.

### Fixed
- TypeScript SDK now compiles: added missing `BroadcastRole` type, fixed simulated transport import path, added Node and Web Bluetooth type packages and a lockfile
- TypeScript Ed25519 signing and verification loaded keys with `KeyObject.from`, which threw at runtime; now uses `createPrivateKey` / `createPublicKey` and matches Python signatures byte-for-byte

### Added
- Cross-SDK test that runs the built TypeScript SDK against the Python SDK (HMAC and Ed25519)
- CI builds the TypeScript SDK
- README: how-it-works diagram, comparison with manual transfer / virtual accounts / USSD / NQR, platform status, adopters
- SECURITY.md: Ed25519 threat model, attacker outcomes, private reporting channel

### Changed
- Release workflow publishes to PyPI / npm only when `PUBLISH_PYPI` / `PUBLISH_NPM` repository variables are set
- Python package uses SPDX license metadata
- Versions synced to 1.3.1 across Python, npm, Android, and the reference bank API

## [1.3.0] - 2026-08-10

### Added
- Python `wire_format` encode/expand (`encode_wire_envelope`, `wire_to_verify_envelope`, presence omit `amt`)
- Python `amount` helpers (`to_packet_amount` / `from_packet_amount` — Ed25519 kobo)
- Python `api_url` helpers (`normalize_bank_api_url`, `sync_signing_key_url`)
- Docs: CheckoutPay `POST …/terminals/sync-signing-key`, single POS config path, Laravel open-until-paid notes

### Changed
- `deploy/laravel/BroadcastVerifyController.php` aligned with Cheko production (wire expand, open-until-paid, presence window, merchant active)
- Routes snippet documents `sync-signing-key`

## [1.2.0] - 2026-08-10

### Added
- [spec/ble-transport.md](spec/ble-transport.md) — compact `{p,alg,sig}` wire, kobo amounts, presence (CheckoutNow / Cheko path)
- TypeScript `normalizeBleReadForVerify` / `expandWireToVerifyPacket` (`sdk/typescript/src/bleWire.ts`)
- Reference bank API: compact wire expand + presence (no session burn) via `bank_api/ble_wire.py`

### Changed
- Docs and verify API contract now describe **expand → verify**, Ed25519 production defaults, and kobo÷100 for UI
- Web receiver demo expands compact wire before `POST /verify-broadcast`
- `bank_display_matches` accepts msk-only wire display (matches Laravel deploy controller)

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
