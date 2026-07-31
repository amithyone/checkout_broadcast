import base64
import hashlib
import hmac
import json
from typing import Any

try:
    from nacl.exceptions import BadSignatureError
    from nacl.signing import SigningKey, VerifyKey

    _HAS_NACL = True
except ImportError:  # pragma: no cover - optional until PyNaCl installed
    _HAS_NACL = False
    BadSignatureError = Exception  # type: ignore[misc, assignment]
    SigningKey = None  # type: ignore[misc, assignment]
    VerifyKey = None  # type: ignore[misc, assignment]


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


def normalize_signature_alg(alg: str) -> str:
    normalized = alg.strip().upper().replace("_", "-")
    if normalized == "ED25519":
        return "ED25519"
    if normalized in ("HMAC-SHA256", "HMACSHA256"):
        return "HMAC-SHA256"
    return alg.strip().upper()


def _decode_key_material(value: str, expected_length: int) -> bytes | None:
    trimmed = value.strip()
    if not trimmed:
        return None
    decoded = base64.b64decode(trimmed, validate=True)
    if len(decoded) == expected_length:
        return decoded
    if len(trimmed) == expected_length * 2 and all(c in "0123456789abcdefABCDEF" for c in trimmed):
        return bytes.fromhex(trimmed)
    return None


def _ed25519_signing_key(signing_key_b64: str) -> "SigningKey":
    if not _HAS_NACL:
        raise RuntimeError("Ed25519 requires PyNaCl: pip install PyNaCl")
    raw = _decode_key_material(signing_key_b64, 32) or _decode_key_material(signing_key_b64, 64)
    if raw is None:
        raise ValueError("Invalid Ed25519 signing key: expected base64 32- or 64-byte key material")
    seed = raw[:32]
    return SigningKey(seed)


def sign_payload_ed25519(payload: dict[str, Any], signing_key_b64: str) -> str:
    signing_key = _ed25519_signing_key(signing_key_b64)
    message = canonical_json(payload)
    signature = signing_key.sign(message).signature
    return base64.b64encode(signature).decode("ascii")


def verify_ed25519(payload: dict[str, Any], public_key_b64: str, signature: str) -> bool:
    if not _HAS_NACL:
        raise RuntimeError("Ed25519 requires PyNaCl: pip install PyNaCl")
    public_key = _decode_key_material(public_key_b64, 32)
    sig_bytes = _decode_key_material(signature, 64)
    if public_key is None or sig_bytes is None:
        return False
    message = canonical_json(payload)
    verify_key = VerifyKey(public_key)
    try:
        verify_key.verify(message, sig_bytes)
        return True
    except BadSignatureError:
        return False


def sign_packet(payload: dict[str, Any], signing_key: str, signature_alg: str = "HMAC-SHA256") -> tuple[str, str]:
    alg = normalize_signature_alg(signature_alg)
    if alg == "ED25519":
        return "ed25519", sign_payload_ed25519(payload, signing_key)
    return "HMAC-SHA256", sign_payload(payload, signing_key)


def verify_packet(
    payload: dict[str, Any],
    signature_alg: str,
    signature: str,
    *,
    signing_key: str = "",
    public_key: str | None = None,
) -> bool:
    alg = normalize_signature_alg(signature_alg)
    if alg == "ED25519":
        return public_key is not None and verify_ed25519(payload, public_key, signature)
    return verify_signature(payload, signing_key, signature)


def generate_ed25519_keypair() -> dict[str, str]:
    if not _HAS_NACL:
        raise RuntimeError("Ed25519 requires PyNaCl: pip install PyNaCl")
    signing_key = SigningKey.generate()
    return {
        "public_key": base64.b64encode(bytes(signing_key.verify_key)).decode("ascii"),
        "signing_key": base64.b64encode(signing_key.encode()).decode("ascii"),
    }
