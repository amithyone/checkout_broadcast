"""Normalize compact BLE wire {p,alg,sig} → verify envelope (CheckoutNow / Cheko path)."""

from __future__ import annotations

from typing import Any


def normalize_ble_packet(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept full envelope or compact wire. Signature covers expanded payload keys."""
    if isinstance(raw.get("payload"), dict):
        return {
            "payload": raw["payload"],
            "signature_alg": raw.get("signature_alg") or raw.get("alg") or "HMAC-SHA256",
            "signature": raw.get("signature") or raw.get("sig") or "",
        }

    p = raw.get("p")
    if not isinstance(p, dict):
        return raw

    sid = str(p.get("sid") or "").strip()
    tid = str(p.get("tid") or "").strip()
    sig = str(raw.get("sig") or raw.get("signature") or "").strip()
    if not sid or not tid or not sig:
        return raw

    protocol_version: Any = p.get("v", 2.1)
    if isinstance(protocol_version, str) and protocol_version.strip().replace(".", "", 1).isdigit():
        protocol_version = float(protocol_version)

    amt_present = "amt" in p
    amt = int(p["amt"]) if amt_present else 0
    kind = str(p.get("k") or "").strip().lower()

    payload: dict[str, Any] = {
        "protocol_version": protocol_version,
        "timestamp_ms": int(p.get("ts") or 0),
        "session_uuid_v4": sid,
        "terminal_id": tid,
        "transaction_details": {"total_amount_ngn": amt},
    }
    if kind in {"presence", "idle", "beacon", "pos_checkout", "checkout"}:
        payload["session_kind"] = "presence" if kind in {"presence", "idle", "beacon"} else "pos_checkout"

    msk = str(p.get("msk") or "").strip()
    if msk:
        payload["account_info_public_display"] = {"masked_account_suffix": msk}

    return {
        "payload": payload,
        "signature_alg": str(raw.get("alg") or raw.get("signature_alg") or "ed25519"),
        "signature": sig,
    }


def is_presence_payload(payload: dict[str, Any]) -> bool:
    kind = str(payload.get("session_kind") or "").strip().lower()
    if kind in {"presence", "idle", "beacon"}:
        return True
    tx = payload.get("transaction_details") or {}
    try:
        amount = int(tx.get("total_amount_ngn") or 0)
    except (TypeError, ValueError):
        amount = 0
    return amount <= 0
