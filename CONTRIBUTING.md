# Contributing to Checkout Broadcast

Thank you for helping make frictionless payments work for Nigerian businesses.

## Development setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install jsonschema  # for schema tests
```

## Running tests

```bash
PYTHONPATH="sdk/python:." pytest tests/ -v
```

## Code guidelines

- Match existing style in each SDK (Python, TypeScript, Kotlin, Swift)
- All protocol changes require updates to `spec/` and cross-SDK tests
- Never commit secrets, `.env`, or `data/*.db`
- Signing output must remain identical across SDKs — run `tests/test_cross_sdk.py`

## Pull request checklist

- [ ] Tests pass locally
- [ ] Protocol changes documented in `spec/`
- [ ] Integration docs updated if API surface changes
- [ ] No hardcoded signing keys or admin keys
- [ ] Security implications noted in PR description

## Adding a new platform SDK

1. Implement `CheckoutBroadcastAddon` with the same role gating as `spec/addon-api.md`
2. Use canonical signing from `spec/signing-rules.md`
3. Add conformance tests against `tests/fixtures/sample_packet.json`

## Questions

Open a GitHub Discussion or issue for design questions before large changes.
