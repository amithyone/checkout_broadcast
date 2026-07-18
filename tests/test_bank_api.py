import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk" / "python"))

from checkout_broadcast.signing import hash_bank_name, sign_payload

ADMIN_KEY = "test-admin-key-for-ci-only"
SIGNING_KEY = "test-signing-key-min-16-chars"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CHECKOUT_BANK_DB", str(tmp_path / "bank.db"))
    monkeypatch.setenv("CHECKOUT_BANK_ADMIN_KEY", ADMIN_KEY)

    import bank_api.config as config_mod
    import bank_api.database as db_mod
    import bank_api.server as server_mod

    server_mod.settings = config_mod.Settings.from_env()
    server_mod.db = db_mod.BankDatabase(server_mod.settings.database_path)
    server_mod.verify_limiter = server_mod.RateLimiter(120)
    return TestClient(server_mod.app)


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_register_requires_admin_key(client):
    response = client.post(
        "/terminals/register",
        json={
            "terminal_id": "POS-001",
            "signing_key": SIGNING_KEY,
            "merchant_name": "Test Shop",
            "bank_name": "kuda",
            "masked_account_suffix": "***9876",
        },
    )
    assert response.status_code == 401


def test_register_and_verify(client):
    reg = client.post(
        "/terminals/register",
        headers={"X-Admin-Key": ADMIN_KEY},
        json={
            "terminal_id": "POS-001",
            "signing_key": SIGNING_KEY,
            "merchant_name": "Test Shop",
            "bank_name": "kuda",
            "masked_account_suffix": "***9876",
            "account_number": "0123456789",
            "recipient_bank_code": "50211",
        },
    )
    assert reg.status_code == 200

    payload = {
        "protocol_version": 2.0,
        "timestamp_ms": int(time.time() * 1000),
        "session_uuid_v4": "11111111-1111-4111-8111-111111111111",
        "terminal_id": "POS-001",
        "transaction_details": {"currency_code": "NGN", "total_amount_ngn": 1500, "item_count": 2},
        "account_info_public_display": {
            "bank_name_hash": hash_bank_name("kuda"),
            "masked_account_suffix": "***9876",
        },
    }
    packet = {
        "payload": payload,
        "signature_alg": "HMAC-SHA256",
        "signature": sign_payload(payload, SIGNING_KEY),
    }
    verify = client.post("/verify-broadcast", json=packet)
    body = verify.json()
    assert body["valid"] is True
    assert body["amount_ngn"] == 1500
    assert body["recipient_account"] == "0123456789"

    replay = client.post("/verify-broadcast", json=packet)
    assert replay.json()["valid"] is False


def test_unknown_terminal_rejected(client):
    payload = {
        "protocol_version": 2.0,
        "timestamp_ms": int(time.time() * 1000),
        "session_uuid_v4": "22222222-2222-4222-8222-222222222222",
        "terminal_id": "UNKNOWN",
        "transaction_details": {"currency_code": "NGN", "total_amount_ngn": 100, "item_count": 1},
        "account_info_public_display": {
            "bank_name_hash": hash_bank_name("kuda"),
            "masked_account_suffix": "***9876",
        },
    }
    packet = {
        "payload": payload,
        "signature_alg": "HMAC-SHA256",
        "signature": sign_payload(payload, SIGNING_KEY),
    }
    assert client.post("/verify-broadcast", json=packet).json()["valid"] is False


def test_invalid_signature_rejected(client):
    client.post(
        "/terminals/register",
        headers={"X-Admin-Key": ADMIN_KEY},
        json={
            "terminal_id": "POS-002",
            "signing_key": SIGNING_KEY,
            "merchant_name": "Shop",
            "bank_name": "kuda",
            "masked_account_suffix": "***9876",
        },
    )
    payload = {
        "protocol_version": 2.0,
        "timestamp_ms": int(time.time() * 1000),
        "session_uuid_v4": "33333333-3333-4333-8333-333333333333",
        "terminal_id": "POS-002",
        "transaction_details": {"currency_code": "NGN", "total_amount_ngn": 500, "item_count": 1},
        "account_info_public_display": {
            "bank_name_hash": hash_bank_name("kuda"),
            "masked_account_suffix": "***9876",
        },
    }
    packet = {
        "payload": payload,
        "signature_alg": "HMAC-SHA256",
        "signature": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    }
    assert client.post("/verify-broadcast", json=packet).json()["error"] == "Invalid signature"
