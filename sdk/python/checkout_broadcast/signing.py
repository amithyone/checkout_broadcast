import base64
import hashlib
import hmac
import json
from typing import Any


def hash_bank_name(bank_name: str) -> str:
    normalized = bank_name.strip().lower()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def canonical_json(data: dict[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_payload(payload: dict[str, Any], signing_key: str) -> str:
    message = canonical_json(payload)
    digest = hmac.new(signing_key.encode("utf-8"), message, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def verify_signature(payload: dict[str, Any], signing_key: str, signature: str) -> bool:
    expected = sign_payload(payload, signing_key)
    return hmac.compare_digest(expected, signature)
