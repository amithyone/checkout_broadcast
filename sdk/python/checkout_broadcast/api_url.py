"""CheckoutPay broadcast API base URL helpers (Cheko / POS Settings)."""

from __future__ import annotations

DEFAULT_BANK_API_URL = "https://check-outpay.com/api/v1/broadcast"


def normalize_bank_api_url(url: str | None) -> str:
    """Ensure CheckoutPay base ends at /api/v1/broadcast (not bare site root)."""
    u = (url or "").strip().rstrip("/")
    if not u:
        return DEFAULT_BANK_API_URL
    if u.lower().endswith("/verify-broadcast"):
        u = u[: -len("/verify-broadcast")].rstrip("/")
    lowered = u.lower()
    if "check-outpay.com" in lowered and "/api/v1/broadcast" not in lowered:
        return DEFAULT_BANK_API_URL
    return u


def sync_signing_key_url(bank_api_url: str | None = None) -> str:
    return f"{normalize_bank_api_url(bank_api_url)}/terminals/sync-signing-key"


def verify_broadcast_url(bank_api_url: str | None = None) -> str:
    return f"{normalize_bank_api_url(bank_api_url)}/verify-broadcast"
