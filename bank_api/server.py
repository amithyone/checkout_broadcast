"""Checkout Broadcast reference bank verification API.

Banks can deploy this server to test SDK integration before building their own backend.
Replace SQLite + admin key with your HSM, vault, and enterprise auth for production.
"""

from __future__ import annotations

import logging
import sys
import base64
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk" / "python"))

from checkout_broadcast.protocol import (
    SignedPacket,
    is_timestamp_valid,
    parse_timestamp_ms,
    payload_for_signing,
)
from checkout_broadcast.signing import (
    _ed25519_signing_key,
    bank_display_matches,
    generate_ed25519_keypair,
    hash_bank_name,
    normalize_signature_alg,
    verify_packet,
)

from bank_api.auth import RateLimiter, require_admin_key
from bank_api.ble_wire import is_presence_payload, normalize_ble_packet
from bank_api.config import Settings
from bank_api.database import BankDatabase

logger = logging.getLogger(__name__)
settings = Settings.from_env()
db = BankDatabase(settings.database_path)
verify_limiter = RateLimiter(settings.rate_limit_verify_per_minute)


def admin_auth(x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key")) -> None:
    require_admin_key(settings, x_admin_key)


def ping_public_usage() -> None:
    """Forward one anonymous ok to the OSS Vercel counter. Never fails verify."""
    url = settings.usage_stats_url
    token = settings.usage_stats_token
    if not url or not token:
        return
    try:
        import urllib.request

        req = urllib.request.Request(
            f"{url}/usage/hit",
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        logger.debug("CHECKOUT_USAGE_STATS_URL hit skipped", exc_info=True)


class TerminalRegistration(BaseModel):
    terminal_id: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    signing_key: Optional[str] = Field(default=None, min_length=16, max_length=4096)
    public_key: Optional[str] = Field(default=None, max_length=512)
    signature_alg: Optional[str] = Field(default="HMAC-SHA256")
    generate_signing_key: bool = False
    merchant_name: str = Field(min_length=1, max_length=128)
    bank_name: str = Field(min_length=1, max_length=64)
    masked_account_suffix: str = Field(pattern=r"^\*{3}[0-9]{4}$")
    account_number: Optional[str] = Field(default=None, pattern=r"^[0-9]{10}$")
    recipient_bank_code: Optional[str] = Field(default=None, pattern=r"^[0-9]{3,6}$")


class VerifyFailure(BaseModel):
    valid: bool = False
    error: str


class VerifySuccess(BaseModel):
    valid: bool = True
    merchant_name: str
    amount_ngn: int
    masked_account_suffix: str
    session_uuid: str
    terminal_id: str
    session_kind: Optional[str] = None
    recipient_account: Optional[str] = None
    recipient_bank_code: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    purged = db.purge_expired_sessions()
    if purged:
        logger.info("Purged %d expired sessions on startup", purged)
    if settings.admin_api_key == "change-me-before-production":
        logger.warning(
            "CHECKOUT_BANK_ADMIN_KEY is using the default value — set a strong key before deployment"
        )
    yield


app = FastAPI(
    title="Checkout Broadcast Reference Bank API",
    description="Reference verification server for banks testing Checkout Broadcast integration.",
    version="1.5.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, Any]:
    stats = db.stats()
    return {"status": "ready", **stats}


@app.post("/terminals/register", dependencies=[Depends(admin_auth)])
def register_terminal(body: TerminalRegistration) -> dict[str, Any]:
    signature_alg = normalize_signature_alg(body.signature_alg or "HMAC-SHA256")
    signing_key = body.signing_key or ""
    public_key = body.public_key

    if signature_alg == "ED25519":
        if body.generate_signing_key:
            generated = generate_ed25519_keypair()
            signing_key = generated["signing_key"]
            public_key = generated["public_key"]
        elif public_key is None and not signing_key:
            raise HTTPException(status_code=422, detail="public_key or signing_key required for ed25519 terminals")
        elif public_key is None and signing_key:
            public_key = base64.b64encode(bytes(_ed25519_signing_key(signing_key).verify_key)).decode("ascii")
    elif not signing_key or len(signing_key) < 16:
        raise HTTPException(status_code=422, detail="signing_key must be at least 16 characters for HMAC-SHA256")

    db.upsert_terminal(
        terminal_id=body.terminal_id,
        signing_key=signing_key,
        public_key=public_key,
        signature_alg=signature_alg,
        merchant_name=body.merchant_name,
        bank_name=body.bank_name,
        bank_name_hash=hash_bank_name(body.bank_name),
        masked_account_suffix=body.masked_account_suffix,
        account_number=body.account_number,
        recipient_bank_code=body.recipient_bank_code,
    )
    logger.info("Registered terminal %s alg=%s", body.terminal_id, signature_alg)
    response: dict[str, Any] = {
        "status": "registered",
        "terminal_id": body.terminal_id,
        "signature_alg": signature_alg,
    }
    if signature_alg == "ED25519" and signing_key:
        response["signing_key"] = signing_key
        response["public_key"] = public_key
    return response


@app.get("/terminals", dependencies=[Depends(admin_auth)])
def list_terminals() -> dict[str, Any]:
    return {"terminals": db.list_terminals_public()}


@app.get("/terminals/{terminal_id}", dependencies=[Depends(admin_auth)])
def get_terminal(terminal_id: str) -> dict[str, Any]:
    terminal = db.get_terminal(terminal_id)
    if not terminal:
        raise HTTPException(status_code=404, detail="Terminal not found")
    return {
        "terminal_id": terminal_id,
        "merchant_name": terminal["merchant_name"],
        "bank_name": terminal["bank_name"],
        "masked_account_suffix": terminal["masked_account_suffix"],
        "recipient_bank_code": terminal.get("recipient_bank_code"),
        "active": bool(terminal["active"]),
    }


@app.post("/verify-broadcast")
async def verify_broadcast(request: Request) -> dict[str, Any]:
    client_ip = request.client.host if request.client else "unknown"
    if not verify_limiter.allow(client_ip):
        retry = verify_limiter.retry_after(client_ip)
        return JSONResponse(
            status_code=429,
            content={"valid": False, "error": "Rate limit exceeded", "retry_after_seconds": retry},
            headers={"Retry-After": str(retry)},
        )

    try:
        raw = await request.json()
    except Exception:
        return VerifyFailure(error="Invalid packet").model_dump()
    if not isinstance(raw, dict):
        return VerifyFailure(error="Invalid packet").model_dump()

    normalized = normalize_ble_packet(raw)
    payload = normalized.get("payload")
    if not isinstance(payload, dict):
        # Fallback: pydantic-shaped body already expanded
        try:
            packet = SignedPacket.model_validate(raw)
            payload = payload_for_signing(packet.payload)
            normalized = {
                "payload": payload,
                "signature_alg": packet.signature_alg,
                "signature": packet.signature,
            }
        except Exception:
            return VerifyFailure(error="Invalid packet").model_dump()

    terminal_id = payload.get("terminal_id")
    if not terminal_id:
        return VerifyFailure(error="Unknown terminal_id").model_dump()
    terminal = db.get_terminal(str(terminal_id))
    if not terminal:
        return VerifyFailure(error="Unknown terminal_id").model_dump()

    timestamp_ms = parse_timestamp_ms(payload)
    if timestamp_ms is None:
        return VerifyFailure(error="Missing timestamp_ms in payload").model_dump()
    if not is_timestamp_valid(timestamp_ms):
        return VerifyFailure(error="Timestamp outside allowed window").model_dump()

    session = str(payload.get("session_uuid_v4") or "")
    if not session:
        return VerifyFailure(error="Invalid session").model_dump()

    presence = is_presence_payload(payload)
    session_kind = "presence" if presence else "pos_checkout"
    if not presence and not db.consume_session(session, str(terminal_id)):
        return VerifyFailure(error="Session UUID already used (replay)").model_dump()

    display = payload.get("account_info_public_display") or {}
    if not isinstance(display, dict):
        display = {}
    if not bank_display_matches(
        terminal["bank_name"],
        display,
        terminal["bank_name_hash"],
        terminal.get("masked_account_suffix") or "",
    ):
        return VerifyFailure(error="Bank name mismatch").model_dump()

    signature_alg = normalized.get("signature_alg") or terminal.get("signature_alg") or "HMAC-SHA256"
    signature = str(normalized.get("signature") or "")
    if not verify_packet(
        payload,
        signature_alg,
        signature,
        signing_key=terminal.get("signing_key") or "",
        public_key=terminal.get("public_key"),
    ):
        return VerifyFailure(error="Invalid signature").model_dump()

    tx = payload.get("transaction_details") or {}
    try:
        amount = int(tx.get("total_amount_ngn") or 0)
    except (TypeError, ValueError):
        amount = 0
    if not presence:
        db.increment_ok_count()
        ping_public_usage()
    return VerifySuccess(
        merchant_name=terminal["merchant_name"],
        amount_ngn=0 if presence else amount,
        session_kind=session_kind,
        masked_account_suffix=terminal["masked_account_suffix"],
        session_uuid=session,
        terminal_id=str(terminal_id),
        recipient_account=terminal.get("account_number"),
        recipient_bank_code=terminal.get("recipient_bank_code"),
    ).model_dump()


@app.get("/usage/public")
def usage_public() -> dict[str, Any]:
    """Badge-safe total: successful checkout verifies only. No merchant data."""
    return {"ok": True, "ok_count": db.get_ok_count()}


@app.post("/usage/hit")
async def usage_hit(request: Request) -> dict[str, Any]:
    """Banks that run their own verify: POST empty JSON after each successful checkout. Counts as 1."""
    client_ip = request.client.host if request.client else "unknown"
    if not verify_limiter.allow(f"usage:{client_ip}"):
        retry = verify_limiter.retry_after(f"usage:{client_ip}")
        return JSONResponse(
            status_code=429,
            content={"ok": False, "error": "Rate limit exceeded", "retry_after_seconds": retry},
            headers={"Retry-After": str(retry)},
        )
    total = db.increment_ok_count()
    ping_public_usage()
    return {"ok": True, "ok_count": total}


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    uvicorn.run(
        "bank_api.server:app",
        host=settings.listen_host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
