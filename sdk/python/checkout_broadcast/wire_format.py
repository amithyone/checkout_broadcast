"""Minimal BLE wire format (short keys) ↔ canonical verify envelope.

Production path used by CheckoutNow / Cheko POS:
  POS signs expanded canonical payload → compresses to {p,alg,sig} for GATT.
  Wallet expands before POST /verify-broadcast (or bank expands).

Important: expand must recreate the exact signed payload keys (no invented fields).
"""

from __future__ import annotations

import json
from typing import Any

PROTOCOL_VERSION = 2.1


def is_wire_packet(data: dict[str, Any]) -> bool:
    return isinstance(data.get("p"), dict)


def build_minimal_online_payload(
    *,
    terminal_id: str,
    amount_ngn: int,
    session_uuid_v4: str,
    timestamp_ms: int,
    masked_account_suffix: str,
) -> dict[str, Any]:
    """
    Canonical payload signed for verify — no merchant/bank (from terminal registry).

    amount_ngn == 0 → presence / idle till (phone shows amount keypad).
    amount_ngn > 0 → locked checkout amount (integer kobo for Ed25519/Cheko).
    """
    return {
        "protocol_version": PROTOCOL_VERSION,
        "session_uuid_v4": session_uuid_v4,
        "terminal_id": terminal_id,
        "timestamp_ms": timestamp_ms,
        "transaction_details": {"total_amount_ngn": max(int(amount_ngn), 0)},
        "account_info_public_display": {"masked_account_suffix": masked_account_suffix},
    }


PRESENCE_KINDS = frozenset({"presence", "idle", "beacon"})
CHECKOUT_KINDS = frozenset({"pos_checkout", "checkout"})


def encode_wire_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """Full verify envelope → short-key BLE wire. Presence omits `amt` (or amt:0).

    `msk` and `k` are written only when the signed payload has them, so expanding the wire
    recreates exactly the payload that was signed.
    """
    payload = envelope["payload"]
    tx = payload.get("transaction_details") or {}
    acct = payload.get("account_info_public_display") or {}
    amount = int(tx.get("total_amount_ngn", 0) or 0)
    p: dict[str, Any] = {
        "v": payload.get("protocol_version", PROTOCOL_VERSION),
        "sid": payload["session_uuid_v4"],
        "tid": payload["terminal_id"],
        "ts": payload["timestamp_ms"],
    }
    msk = str(acct.get("masked_account_suffix") or "").strip()
    if msk:
        p["msk"] = msk
    kind = str(payload.get("session_kind") or "").strip().lower()
    if kind:
        p["k"] = kind
    # Checkout: include amt. Presence: omit amt (expand → 0).
    if amount > 0:
        p["amt"] = amount
    return {
        "p": p,
        "alg": envelope.get("signature_alg", "ed25519"),
        "sig": envelope.get("signature", ""),
    }


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def is_presence_wire(p: dict[str, Any]) -> bool:
    kind = str(p.get("k") or "").strip().lower()
    if kind in PRESENCE_KINDS or p.get("amt") is None:
        return True
    return _as_number(p.get("amt")) == 0


def wire_to_verify_envelope(wire: dict[str, Any]) -> dict[str, Any]:
    """Short-key BLE wire → canonical { payload, signature_alg, signature } for verify.

    Matches sdk/typescript/src/bleWire.ts, bank_api/ble_wire.py and the CheckoutNow app. Adds
    `session_kind` only when `k` is sent and `account_info_public_display` only when `msk` is
    non-empty — inventing either breaks the signature.
    """
    if not is_wire_packet(wire):
        return wire

    p = wire["p"]
    raw_v = p.get("v")
    if isinstance(raw_v, (int, float)) and not isinstance(raw_v, bool):
        protocol_version: Any = raw_v
    else:
        protocol_version = _as_number(raw_v) if raw_v is not None else None
        if protocol_version is None:
            protocol_version = PROTOCOL_VERSION

    presence = is_presence_wire(p)
    amount = 0 if presence else int(round(_as_number(p.get("amt")) or 0))

    payload: dict[str, Any] = {
        "protocol_version": protocol_version,
        "timestamp_ms": int(_as_number(p.get("ts")) or 0),
        "session_uuid_v4": str(p["sid"]).strip(),
        "terminal_id": str(p["tid"]).strip(),
        "transaction_details": {"total_amount_ngn": amount},
    }
    kind = str(p.get("k") or "").strip().lower()
    if kind in PRESENCE_KINDS:
        payload["session_kind"] = "presence"
    elif kind in CHECKOUT_KINDS:
        payload["session_kind"] = "pos_checkout"
    msk = str(p.get("msk") or "").strip()
    if msk:
        payload["account_info_public_display"] = {"masked_account_suffix": msk}

    alg = str(wire.get("alg") or wire.get("signature_alg") or "").strip() or "ed25519"
    sig = str(wire.get("sig") or wire.get("signature") or "").strip()
    return {"payload": payload, "signature_alg": alg, "signature": sig}


def normalize_ble_read_for_verify(gatt_json: dict[str, Any]) -> dict[str, Any]:
    """Accept wire or legacy envelope from a GATT read."""
    if is_wire_packet(gatt_json):
        return wire_to_verify_envelope(gatt_json)
    if isinstance(gatt_json.get("payload"), dict):
        return {
            "payload": gatt_json["payload"],
            "signature_alg": str(gatt_json.get("signature_alg") or "").strip() or "HMAC-SHA256",
            "signature": gatt_json.get("signature") or gatt_json.get("sig") or "",
        }
    raise ValueError("Unrecognized BLE checkout packet")


def wire_byte_size(wire: dict[str, Any]) -> int:
    return len(json.dumps(wire, separators=(",", ":")).encode("utf-8"))


def is_presence_amount(amount: int | float | None) -> bool:
    return amount is None or int(amount) <= 0
