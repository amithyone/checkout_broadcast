import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

BroadcastRole = Literal["send", "receive", "both"]
TransportKind = Literal["ble", "simulated"]
SignatureAlg = Literal["HMAC-SHA256", "ed25519", "ED25519"]

MAX_AGE_MS = 600_000  # 10 minutes


class TransactionDetails(BaseModel):
    currency_code: Literal["NGN"] = "NGN"
    total_amount_ngn: int = Field(ge=1)
    item_count: int = Field(ge=1)


class AccountInfoPublicDisplay(BaseModel):
    masked_account_suffix: str
    bank_name: Optional[str] = None
    bank_name_hash: Optional[str] = None

    @model_validator(mode="after")
    def require_bank_identity(self) -> "AccountInfoPublicDisplay":
        has_name = bool(self.bank_name and self.bank_name.strip())
        has_hash = bool(self.bank_name_hash and self.bank_name_hash.strip())
        if not has_name and not has_hash:
            raise ValueError("account_info_public_display requires bank_name or bank_name_hash")
        return self


class Payload(BaseModel):
    protocol_version: Literal[2] = 2
    timestamp_ms: int = Field(ge=0)
    session_uuid_v4: str
    terminal_id: str
    transaction_details: TransactionDetails
    account_info_public_display: AccountInfoPublicDisplay


class SignedPacket(BaseModel):
    payload: Payload | dict
    signature_alg: str = "HMAC-SHA256"
    signature: str


@dataclass
class CheckoutData:
    amount_ngn: int
    item_count: int = 1


@dataclass
class VerifiedPayment:
    merchant_name: str
    amount_ngn: int
    masked_account_suffix: str
    session_uuid: str
    terminal_id: str


def build_payload(
    *,
    terminal_id: str,
    amount_ngn: int,
    item_count: int,
    bank_name: str,
    masked_account_suffix: str,
    session_uuid_v4: str | None = None,
) -> dict:
    return Payload(
        timestamp_ms=int(time.time() * 1000),
        session_uuid_v4=session_uuid_v4 or str(uuid.uuid4()),
        terminal_id=terminal_id,
        transaction_details=TransactionDetails(
            total_amount_ngn=amount_ngn,
            item_count=item_count,
        ),
        account_info_public_display=AccountInfoPublicDisplay(
            bank_name=bank_name.strip(),
            masked_account_suffix=masked_account_suffix,
        ),
    ).model_dump(exclude_none=True)


def payload_for_signing(payload: Payload | dict) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    return payload.model_dump(exclude_none=True)


def signed_packet_for_api(packet: SignedPacket) -> dict[str, Any]:
    return {
        "payload": payload_for_signing(packet.payload),
        "signature_alg": packet.signature_alg,
        "signature": packet.signature,
    }


def is_timestamp_valid(timestamp_ms: int, now_ms: Optional[int] = None) -> bool:
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    return abs(now - timestamp_ms) <= MAX_AGE_MS


def parse_timestamp_ms(payload: dict) -> int | None:
    """Return epoch milliseconds from payload.timestamp_ms, or None if missing/invalid."""
    if "timestamp_ms" not in payload:
        return None
    raw = payload["timestamp_ms"]
    if raw is None or raw == "":
        return None
    try:
        timestamp_ms = int(raw)
    except (TypeError, ValueError):
        return None
    return timestamp_ms if timestamp_ms > 0 else None


def require_timestamp_ms(payload: dict) -> int:
    timestamp_ms = parse_timestamp_ms(payload)
    if timestamp_ms is None:
        raise ValueError("Missing timestamp_ms in payload")
    return timestamp_ms
