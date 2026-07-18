import json
import os
import sys
import tempfile
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk" / "python"))

from checkout_broadcast.addon import CheckoutBroadcastAddon, CheckoutBroadcastConfig
from checkout_broadcast.errors import RoleNotAllowedError, VerificationError
from checkout_broadcast.protocol import CheckoutData
from checkout_broadcast.signing import hash_bank_name, sign_payload, verify_signature

ADMIN_KEY = "test-admin-key-for-ci-only"
SIGNING_KEY = "test-signing-key-min-16-chars"


@pytest.fixture()
def bank_client(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        monkeypatch.setenv("CHECKOUT_BANK_DB", str(db_path))
        monkeypatch.setenv("CHECKOUT_BANK_ADMIN_KEY", ADMIN_KEY)

        import bank_api.config as config_mod
        import bank_api.database as db_mod
        import bank_api.server as server_mod

        settings = config_mod.Settings.from_env()
        server_mod.settings = settings
        server_mod.db = db_mod.BankDatabase(settings.database_path)
        server_mod.verify_limiter = server_mod.RateLimiter(settings.rate_limit_verify_per_minute)

        client = TestClient(server_mod.app)
        client.post(
            "/terminals/register",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={
                "terminal_id": "POS-LAG-001",
                "signing_key": SIGNING_KEY,
                "merchant_name": "ABC Enterprises",
                "bank_name": "kuda",
                "masked_account_suffix": "***9876",
                "account_number": "0123456789",
                "recipient_bank_code": "50211",
            },
        )
        yield client


def test_sign_and_verify_roundtrip():
    payload = {
        "protocol_version": 2.0,
        "timestamp_ms": 1720000000000,
        "session_uuid_v4": "550e8400-e29b-41d4-a716-446655440000",
        "terminal_id": "POS-LAG-001",
        "transaction_details": {
            "currency_code": "NGN",
            "total_amount_ngn": 2500,
            "item_count": 3,
        },
        "account_info_public_display": {
            "bank_name_hash": hash_bank_name("kuda"),
            "masked_account_suffix": "***9876",
        },
    }
    sig = sign_payload(payload, SIGNING_KEY)
    assert verify_signature(payload, SIGNING_KEY, sig)
    tampered = {**payload, "transaction_details": {**payload["transaction_details"], "total_amount_ngn": 9999}}
    assert not verify_signature(tampered, SIGNING_KEY, sig)


def test_role_gating_receive_cannot_send():
    addon = CheckoutBroadcastAddon(
        CheckoutBroadcastConfig(role="receive", bank_api_url="http://127.0.0.1:8090")
    )
    with pytest.raises(RoleNotAllowedError):
        addon.send_checkout(CheckoutData(amount_ngn=1000))


def test_config_validation():
    with pytest.raises(ValueError, match="signing_key"):
        CheckoutBroadcastConfig(
            role="send",
            terminal_id="POS-1",
            signing_key="short",
            bank_api_url="http://127.0.0.1:8090",
        )


def test_bank_verify_and_replay(bank_client):
    sender = CheckoutBroadcastAddon(
        CheckoutBroadcastConfig(
            role="send",
            terminal_id="POS-LAG-001",
            signing_key=SIGNING_KEY,
            bank_api_url="http://test",
            bank_name="kuda",
            transport="simulated",
        )
    )
    receiver = CheckoutBroadcastAddon(
        CheckoutBroadcastConfig(
            role="receive",
            bank_api_url="http://test",
            transport="simulated",
        )
    )
    payments = []
    receiver.config.on_payment_received = lambda p: payments.append(p)

    def _post(url, json, timeout=10.0):
        response = bank_client.post("/verify-broadcast", json=json)

        class R:
            status_code = response.status_code

            def json(self):
                return response.json()

        return R()

    original_post = httpx.post
    httpx.post = _post
    try:
        receiver.start()
        sender.start()
        packet = sender.send_checkout(CheckoutData(amount_ngn=2500, item_count=3))
        assert len(payments) == 1
        assert payments[0].amount_ngn == 2500

        with pytest.raises(VerificationError):
            receiver._handle_packet(packet)
    finally:
        httpx.post = original_post


def test_fixture_signature_matches_signing_key():
    fixture_path = ROOT / "tests" / "fixtures" / "sample_packet.json"
    data = json.loads(fixture_path.read_text())
    data["payload"]["account_info_public_display"]["bank_name_hash"] = hash_bank_name("kuda")
    sig = sign_payload(data["payload"], SIGNING_KEY)
    assert verify_signature(data["payload"], SIGNING_KEY, sig)


@pytest.mark.parametrize(
    "fixture_name",
    [
        "golden_opay_pos.json",
        "golden_kuda_pos.json",
        "golden_gtbank_pos.json",
    ],
)
def test_golden_adopter_vectors(fixture_name):
    """Golden packets for OPay, Kuda, GTBank SDK conformance."""
    path = ROOT / "tests" / "fixtures" / fixture_name
    data = json.loads(path.read_text())
    key = data.get("signing_key", SIGNING_KEY)
    payload = data["payload"]
    signature = data["signature"]
    assert verify_signature(payload, key, signature)
    bank = data.get("bank_name")
    if bank:
        assert payload["account_info_public_display"]["bank_name_hash"] == hash_bank_name(bank)


def test_golden_vectors_verify_against_bank_api(bank_client):
    """Each golden vector must pass production verify-broadcast logic."""
    import time

    for fixture_name in ("golden_opay_pos.json", "golden_kuda_pos.json", "golden_gtbank_pos.json"):
        path = ROOT / "tests" / "fixtures" / fixture_name
        data = json.loads(path.read_text())
        payload = dict(data["payload"])
        payload["session_uuid_v4"] = f"{payload['session_uuid_v4']}-{fixture_name[:8]}"
        payload["timestamp_ms"] = int(time.time() * 1000)
        key = data.get("signing_key", SIGNING_KEY)
        bank_client.post(
            "/terminals/register",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={
                "terminal_id": payload["terminal_id"],
                "signing_key": key,
                "merchant_name": f"Golden {data.get('bank_name', 'test')}",
                "bank_name": data.get("bank_name", "kuda"),
                "masked_account_suffix": payload["account_info_public_display"]["masked_account_suffix"],
                "account_number": "0123456789",
                "recipient_bank_code": "50211",
            },
        )
        envelope = {
            "payload": payload,
            "signature_alg": data.get("signature_alg", "HMAC-SHA256"),
            "signature": sign_payload(payload, key),
        }
        response = bank_client.post("/verify-broadcast", json=envelope)
        assert response.status_code == 200
        body = response.json()
        assert body["valid"] is True
        assert body["amount_ngn"] == payload["transaction_details"]["total_amount_ngn"]
