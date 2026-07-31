import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk" / "python"))

from checkout_broadcast.protocol import parse_timestamp_ms
from checkout_broadcast.signing import (
    generate_ed25519_keypair,
    sign_packet,
    verify_packet,
)


def test_generate_ed25519_keypair():
    keys = generate_ed25519_keypair()
    assert "public_key" in keys
    assert "signing_key" in keys


def test_ed25519_sign_and_verify_roundtrip():
    keys = generate_ed25519_keypair()
    payload = {
        "protocol_version": 1,
        "timestamp_ms": int(time.time() * 1000),
        "session_uuid_v4": "550e8400-e29b-41d4-a716-446655440000",
        "terminal_id": "TERM-ED",
        "transaction_details": {"currency_code": "NGN", "total_amount_ngn": 1000, "item_count": 1},
        "account_info_public_display": {
            "bank_name_hash": "sha256:abc",
            "masked_account_suffix": "***1234",
        },
    }
    alg, signature = sign_packet(payload, keys["signing_key"], "ed25519")
    assert alg == "ed25519"
    assert verify_packet(payload, alg, signature, public_key=keys["public_key"])


def test_parse_timestamp_ms():
    assert parse_timestamp_ms({"timestamp_ms": 1700000000000}) == 1700000000000
    assert parse_timestamp_ms({}) is None
    assert parse_timestamp_ms({"timestamp_ms": 0}) is None
    assert parse_timestamp_ms({"timestamp_ms": None}) is None
