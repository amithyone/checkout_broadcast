import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk" / "python"))
sys.path.insert(0, str(ROOT))

from bank_api.ble_wire import normalize_ble_packet
from checkout_broadcast.amount import from_packet_amount, to_packet_amount
from checkout_broadcast.api_url import normalize_bank_api_url, sync_signing_key_url
from checkout_broadcast.signing import (
    generate_ed25519_keypair,
    sign_payload_ed25519,
    verify_ed25519,
)
from checkout_broadcast.wire_format import (
    encode_wire_envelope,
    is_wire_packet,
    normalize_ble_read_for_verify,
    wire_to_verify_envelope,
)

VECTORS = json.loads((ROOT / "tests" / "fixtures" / "wire_vectors.json").read_text())["vectors"]
TS_BLE_WIRE = ROOT / "sdk" / "typescript" / "dist" / "bleWire.js"


def _canonical(value) -> str:
    """Sorted keys; json keeps 649 and 649.0 distinct."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


@pytest.mark.parametrize("vector", VECTORS, ids=[v["name"] for v in VECTORS])
def test_python_sdk_expands_shared_vectors(vector):
    assert _canonical(normalize_ble_read_for_verify(vector["packet"])) == _canonical(vector["verify_body"])


@pytest.mark.parametrize("vector", VECTORS, ids=[v["name"] for v in VECTORS])
def test_bank_api_expands_shared_vectors(vector):
    assert _canonical(normalize_ble_packet(vector["packet"])) == _canonical(vector["verify_body"])


@pytest.mark.skipif(
    shutil.which("node") is None or not TS_BLE_WIRE.exists(),
    reason="Node.js or built TypeScript SDK (sdk/typescript/dist) not available",
)
def test_typescript_sdk_expands_shared_vectors():
    script = """
    const [modulePath, vectorsJson] = process.argv.slice(1);
    import(modulePath).then((m) => {
      const out = JSON.parse(vectorsJson).map((v) => {
        const env = m.normalizeBleReadForVerify(v.packet);
        return env ? m.verifyRequestBody(env) : null;
      });
      process.stdout.write(JSON.stringify(out));
    });
    """
    result = subprocess.run(
        ["node", "-e", script, TS_BLE_WIRE.as_uri(), json.dumps(VECTORS)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(result.stderr)
    for vector, body in zip(VECTORS, json.loads(result.stdout)):
        assert _canonical(body) == _canonical(vector["verify_body"]), vector["name"]


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"session_kind": "presence"},
        {"account_info_public_display": {"masked_account_suffix": "***4863"}},
    ],
    ids=["no-msk-no-kind", "presence-kind", "with-msk"],
)
def test_signed_payload_survives_wire_roundtrip(extra):
    payload = {
        "protocol_version": 2.1,
        "session_uuid_v4": "22222222-2222-4222-8222-222222222222",
        "terminal_id": "CP-RT",
        "timestamp_ms": 1_700_000_000_000,
        "transaction_details": {"total_amount_ngn": 0 if extra.get("session_kind") else 1999},
        **extra,
    }
    keys = generate_ed25519_keypair()
    sig = sign_payload_ed25519(payload, keys["signing_key"])
    wire = encode_wire_envelope({"payload": payload, "signature_alg": "ed25519", "signature": sig})
    expanded = wire_to_verify_envelope(wire)
    assert _canonical(expanded["payload"]) == _canonical(payload)
    assert verify_ed25519(expanded["payload"], keys["public_key"], expanded["signature"])


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
