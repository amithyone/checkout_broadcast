# Checkout Broadcast

Open-source SDK for **frictionless POS-to-banking-app payments** in Nigeria.

After checkout, a shop terminal broadcasts a **signed payment request** over Bluetooth. The customer's banking app receives it, verifies it with the bank server, and **pre-fills the transfer screen** — no manual account typing.

[![CI](https://github.com/checkout-broadcast/checkout-broadcast/actions/workflows/ci.yml/badge.svg)](https://github.com/checkout-broadcast/checkout-broadcast/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Features

- Signed protocol v2.0 (HMAC-SHA256 or Ed25519, replay protection)
- Drop-in SDK addon: `send` / `receive` / `both` roles
- Python (Windows/Linux POS), TypeScript (Web), Android & iOS stubs
- **Reference bank API** for banks to test before production rollout
- Simulated transport for CI and local dev

## Quick start

```bash
git clone https://github.com/checkout-broadcast/checkout-broadcast.git
cd checkout-broadcast
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Set CHECKOUT_BANK_ADMIN_KEY and CHECKOUT_SIGNING_KEY (min 16 chars)

# Terminal 1 — reference bank API
PYTHONPATH="sdk/python:." python -m checkout_broadcast.cli run-bank

# Terminal 2 — register terminal + send checkout
export CHECKOUT_SIGNING_KEY="your-secret-key-min-16-chars"
export CHECKOUT_BANK_ADMIN_KEY="change-me-before-production"
PYTHONPATH="sdk/python:." python -m checkout_broadcast.cli register-terminal
PYTHONPATH="sdk/python:." python -m checkout_broadcast.cli demo-send --amount 2500
```

## Integration guides

| Audience | Guide |
|----------|-------|
| **POS / shop terminal apps** | [docs/pos-app-integration.md](docs/pos-app-integration.md) |
| **Banking / wallet apps** | [docs/banking-app-integration.md](docs/banking-app-integration.md) |
| **CheckoutPay Pay at shop** | [docs/checkoutpay-integration.md](docs/checkoutpay-integration.md) |
| **Verify API contract** | [spec/verify-api.md](spec/verify-api.md) |
| **Overview** | [docs/README.md](docs/README.md) |
| **vs CheckoutNow Nearby Pay** | [spec/coexistence-with-proprietary-nearby.md](spec/coexistence-with-proprietary-nearby.md) |

## CheckoutNow Nearby Pay vs Checkout Broadcast

| | Nearby Pay (CheckoutNow only) | Checkout Broadcast (open) |
|--|------------------------------|---------------------------|
| Purpose | Wallet P2P inside CheckoutNow | POS → any wallet app |
| BLE | Advert + pay code | GATT + signed JSON |
| UUID | `a7c5c816-…` | `cbbc0001-…` |
| Verify | CheckoutNow scan-resolve | Bank `verify-broadcast` |

Nearby Pay is **not** part of this repo's open protocol. See coexistence spec above.

## Project structure

```
checkout_broadcast/
├── sdk/python/          # POS SDK (sender) — primary implementation
├── sdk/typescript/      # Web banking SDK (receiver)
├── sdk/android/         # Android SDK
├── sdk/ios/             # iOS Swift Package
├── bank_api/            # Reference bank verification server
├── spec/                # Protocol, signing, BLE specs
├── docs/                # Integration documentation
├── demos/               # Web receiver demo
└── tests/               # Conformance & bank API tests
```

## Bank testing (Docker)

```bash
docker compose up --build
# API: http://127.0.0.1:8090/health
```

## Install from package registries

```bash
# Python (POS SDK)
pip install checkout-broadcast
pip install "checkout-broadcast[ble]"    # BLE on Windows/Linux

# Web / Node (banking app SDK)
npm install @checkout-broadcast/web
```

See **[docs/publishing.md](docs/publishing.md)** for maintainer release steps (PyPI, npm, Maven).

## Security

See [SECURITY.md](SECURITY.md). Report vulnerabilities privately before opening public issues.

**Production banks** must replace the reference SQLite server with HSM-backed keys, enterprise auth, and audited infrastructure.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
