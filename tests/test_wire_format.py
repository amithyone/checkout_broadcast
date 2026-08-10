import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk" / "python"))

from checkout_broadcast.amount import from_packet_amount, to_packet_amount
from checkout_broadcast.api_url import normalize_bank_api_url, sync_signing_key_url
from checkout_broadcast.wire_format import (
    encode_wire_envelope,
    is_wire_packet,
    wire_to_verify_envelope,
)


def test_kobo_roundtrip():
    assert to_packet_amount(25.00, "ed25519") == 2500
    assert from_packet_amount(2500, "ed25519") == 25.0


def test_presence_omits_amt():
    envelope = {
        "payload": {
            "protocol_version": 2.1,
            "session_uuid_v4": "11111111-1111-4111-8111-111111111111",
            "terminal_id": "CP-TEST",
            "timestamp_ms": 1_700_000_000_000,
            "transaction_details": {"total_amount_ngn": 0},
            "account_info_public_display": {"masked_account_suffix": "***1234"},
        },
        "signature_alg": "ed25519",
        "signature": "abc",
    }
    wire = encode_wire_envelope(envelope)
    assert is_wire_packet(wire)
    assert "amt" not in wire["p"]
    expanded = wire_to_verify_envelope(wire)
    assert expanded["payload"]["transaction_details"]["total_amount_ngn"] == 0
    assert "session_kind" not in expanded["payload"]
    assert expanded["signature"] == "abc"


def test_checkout_wire_keeps_amt():
    envelope = {
        "payload": {
            "protocol_version": 2.1,
            "session_uuid_v4": "11111111-1111-4111-8111-111111111111",
            "terminal_id": "CP-TEST",
            "timestamp_ms": 1_700_000_000_000,
            "transaction_details": {"total_amount_ngn": 2500},
            "account_info_public_display": {"masked_account_suffix": "***1234"},
        },
        "signature_alg": "ed25519",
        "signature": "sig",
    }
    wire = encode_wire_envelope(envelope)
    assert wire["p"]["amt"] == 2500
    expanded = wire_to_verify_envelope(wire)
    assert expanded["payload"]["transaction_details"]["total_amount_ngn"] == 2500


def test_normalize_bank_api_url():
    assert normalize_bank_api_url("https://check-outpay.com") == (
        "https://check-outpay.com/api/v1/broadcast"
    )
    assert sync_signing_key_url().endswith("/terminals/sync-signing-key")
