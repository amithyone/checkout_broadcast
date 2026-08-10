"""Map POS decimal NGN totals to packet integers (kobo for Ed25519 / Cheko)."""

from __future__ import annotations

from checkout_broadcast.signing import normalize_signature_alg


def normalize_checkout_amount(amount: float | int) -> float:
    """Two-decimal NGN (₦9003.76)."""
    return round(float(amount), 2)


def to_packet_amount(
    amount: float | int,
    signature_alg: str,
    *,
    allow_zero: bool = False,
) -> int:
    """
    CheckoutNow / ed25519: integer kobo (9003.76 → 900376).
    Open HMAC demos: integer whole naira (2500.00 → 2500).
    Presence / idle: allow_zero=True → 0.
    """
    normalized = normalize_checkout_amount(amount)
    if allow_zero and normalized <= 0:
        return 0
    alg = normalize_signature_alg(signature_alg)
    if alg in ("ed25519", "ED25519"):
        kobo = int(round(normalized * 100))
        return max(1, kobo)
    whole = int(round(normalized))
    return max(1, whole)


def from_packet_amount(packet_amount: int, signature_alg: str) -> float:
    """Verify API / mobile display — ed25519 packets store kobo."""
    alg = normalize_signature_alg(signature_alg)
    if alg in ("ed25519", "ED25519"):
        return normalize_checkout_amount(packet_amount / 100)
    return normalize_checkout_amount(packet_amount)
