import json
import time
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "spec" / "protocol-v2.schema.json"


def test_protocol_schema_validates_fixture():
    schema = json.loads(SCHEMA_PATH.read_text())
    fixture = json.loads((ROOT / "tests" / "fixtures" / "sample_packet.json").read_text())
    resolver = jsonschema.RefResolver.from_schema(schema)
    jsonschema.validate(
        fixture["payload"],
        schema["definitions"]["Payload"],
        resolver=resolver,
    )
