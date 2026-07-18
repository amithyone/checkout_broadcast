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
    payload["account_info_public_display"]["bank_name_hash"] = "sha256:1ab138fd89d4c060074875dcad06de1701ccaa6f94a67dfd9ca65e8496202f7a"

    sys.path.insert(0, str(ROOT / "sdk" / "python"))
    from checkout_broadcast.signing import sign_payload

    py_sig = sign_payload(payload, SIGNING_KEY)

    node_script = """
    const crypto = require('crypto');
    function sortKeys(v) {
      if (Array.isArray(v)) return v.map(sortKeys);
      if (v && typeof v === 'object') {
        return Object.keys(v).sort().reduce((a,k)=>{a[k]=sortKeys(v[k]);return a;},{});
      }
      return v;
    }
    const payload = JSON.parse(process.argv[1]);
    const key = process.argv[2];
    const msg = Buffer.from(JSON.stringify(sortKeys(payload)), 'utf8');
    process.stdout.write(crypto.createHmac('sha256', key).update(msg).digest('base64'));
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
