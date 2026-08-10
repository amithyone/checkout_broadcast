import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "sample_packet.json"
SIGNING_KEY = "test-signing-key-min-16-chars"


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
