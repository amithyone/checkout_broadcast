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


def encode_wire_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """Full verify envelope → short-key BLE wire. Presence omits `amt` (or amt:0)."""
    payload = envelope["payload"]
    tx = payload.get("transaction_details") or {}
    acct = payload.get("account_info_public_display") or {}
    amount = int(tx.get("total_amount_ngn", 0) or 0)
    p: dict[str, Any] = {
        "v": payload.get("protocol_version", PROTOCOL_VERSION),
        "sid": payload["session_uuid_v4"],
        "tid": payload["terminal_id"],
        "ts": payload["timestamp_ms"],
        "msk": acct.get("masked_account_suffix", "***0000"),
    }
    # Checkout: include amt. Presence: omit amt (expand → 0).
    if amount > 0:
        p["amt"] = amount
    return {
        "p": p,
        "alg": envelope.get("signature_alg", "ed25519"),
        "sig": envelope.get("signature", ""),
    }


def wire_to_verify_envelope(wire: dict[str, Any]) -> dict[str, Any]:
    """Short-key BLE wire → canonical { payload, signature_alg, signature } for verify."""
    if not is_wire_packet(wire):
        return wire

    p = wire["p"]
    # Omit amt or amt:0 → presence (total_amount_ngn: 0)
    if "amt" not in p or p.get("amt") is None:
        amount = 0
    else:
        amount = max(int(p["amt"]), 0)

    payload = build_minimal_online_payload(
        terminal_id=str(p["tid"]),
        amount_ngn=amount,
        session_uuid_v4=str(p["sid"]),
        timestamp_ms=int(p["ts"]),
        masked_account_suffix=str(p.get("msk", "***0000")),
    )
    if "v" in p:
        payload["protocol_version"] = p["v"]

    alg = wire.get("alg") or wire.get("signature_alg") or "ed25519"
    sig = wire.get("sig") or wire.get("signature") or ""
    return {"payload": payload, "signature_alg": alg, "signature": sig}


def normalize_ble_read_for_verify(gatt_json: dict[str, Any]) -> dict[str, Any]:
    """Accept wire or legacy envelope from a GATT read."""
    if is_wire_packet(gatt_json):
        return wire_to_verify_envelope(gatt_json)
    if isinstance(gatt_json.get("payload"), dict):
        return {
            "payload": gatt_json["payload"],
            "signature_alg": gatt_json.get("signature_alg")
            or gatt_json.get("alg")
            or "ed25519",
            "signature": gatt_json.get("signature") or gatt_json.get("sig") or "",
        }
    raise ValueError("Unrecognized BLE checkout packet")


def wire_byte_size(wire: dict[str, Any]) -> int:
    return len(json.dumps(wire, separators=(",", ":")).encode("utf-8"))


def is_presence_amount(amount: int | float | None) -> bool:
    return amount is None or int(amount) <= 0
