import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "sample_packet.json"
SIGNING_KEY = "test-signing-key-min-16-chars"
TS_SIGNING = ROOT / "sdk" / "typescript" / "dist" / "signing.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_python_and_node_signing_match():
    """Cross-SDK parity: Python and Node must produce identical signatures."""
    data = json.loads(FIXTURE.read_text())
    payload = data["payload"]
    assert "bank_name" in payload["account_info_public_display"]

    sys.path.insert(0, str(ROOT / "sdk" / "python"))
    from checkout_broadcast.signing import sign_payload

    py_sig = sign_payload(payload, SIGNING_KEY)

    node_script = """
    function normalize(v) {
      if (Array.isArray(v)) return v.map(normalize);
      if (v && typeof v === 'object') {
        return Object.keys(v).sort().reduce((a,k)=>{a[k]=normalize(v[k]);return a;},{});
      }
      if (typeof v === 'number' && Number.isInteger(v)) return v;
      return v;
    }
    const payload = JSON.parse(process.argv[1]);
    const key = process.argv[2];
    const msg = Buffer.from(JSON.stringify(normalize(payload)), 'utf8');
    process.stdout.write(require('crypto').createHmac('sha256', key).update(msg).digest('base64'));
    """
    result = subprocess.run(
        ["node", "-e", node_script, json.dumps(payload), SIGNING_KEY],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(result.stderr)

    assert result.stdout.strip() == py_sig


@pytest.mark.skipif(
    shutil.which("node") is None or not TS_SIGNING.exists(),
    reason="Node.js or built TypeScript SDK (sdk/typescript/dist) not available",
)
def test_typescript_sdk_signatures_match_python():
    """Built TypeScript SDK and Python SDK must agree on HMAC and Ed25519."""
    data = json.loads(FIXTURE.read_text())
    payload = data["payload"]

    sys.path.insert(0, str(ROOT / "sdk" / "python"))
    from checkout_broadcast.signing import (
        generate_ed25519_keypair,
        sign_payload,
        sign_payload_ed25519,
        verify_ed25519,
    )

    keypair = generate_ed25519_keypair()
    py_ed_sig = sign_payload_ed25519(payload, keypair["signing_key"])

    node_script = """
    const [modulePath, payloadJson, hmacKey, edKey, edPub, pyEdSig] = process.argv.slice(1);
    import(modulePath).then((m) => {
      const payload = JSON.parse(payloadJson);
      process.stdout.write(JSON.stringify({
        hmac: m.signPayload(payload, hmacKey),
        ed25519: m.signPayloadEd25519(payload, edKey),
        verifiesPython: m.verifyEd25519(payload, edPub, pyEdSig),
      }));
    });
    """
    result = subprocess.run(
        [
            "node",
            "-e",
            node_script,
            TS_SIGNING.as_uri(),
            json.dumps(payload),
            SIGNING_KEY,
            keypair["signing_key"],
            keypair["public_key"],
            py_ed_sig,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(result.stderr)

    out = json.loads(result.stdout)
    assert out["hmac"] == sign_payload(payload, SIGNING_KEY)
    assert out["ed25519"] == py_ed_sig
    assert verify_ed25519(payload, keypair["public_key"], out["ed25519"])
    assert out["verifiesPython"] is True
