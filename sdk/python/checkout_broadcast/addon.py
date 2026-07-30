from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urlparse

import httpx

from checkout_broadcast.errors import RoleNotAllowedError, VerificationError
from checkout_broadcast.protocol import (
    BroadcastRole,
    CheckoutData,
    SignedPacket,
    TransportKind,
    VerifiedPayment,
    build_payload,
    is_timestamp_valid,
    parse_timestamp_ms,
)
from checkout_broadcast.signing import normalize_signature_alg, sign_packet, verify_signature
from checkout_broadcast.transport.simulated import create_transport

logger = logging.getLogger(__name__)

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass
class CheckoutBroadcastConfig:
    role: BroadcastRole
    bank_api_url: str
    terminal_id: Optional[str] = None
    signing_key: Optional[str] = None
    merchant_name: str = "ABC Enterprises"
    bank_name: str = "kuda"
    masked_account_suffix: str = "***9876"
    transport: TransportKind = "simulated"
    signature_alg: str = "HMAC-SHA256"
    require_https: bool = False
    on_payment_received: Optional[Callable[[VerifiedPayment], None]] = None
    on_send_complete: Optional[Callable[[str], None]] = None
    on_error: Optional[Callable[[Exception], None]] = None

    def __post_init__(self) -> None:
        if self.role not in ("send", "receive", "both"):
            raise ValueError(f"Invalid role: {self.role}")
        if self.transport not in ("simulated", "ble"):
            raise ValueError(f"Invalid transport: {self.transport}")
        if not self.bank_api_url.strip():
            raise ValueError("bank_api_url is required")

        parsed = urlparse(self.bank_api_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("bank_api_url must use http or https")
        if self.require_https and parsed.scheme != "https":
            host = (parsed.hostname or "").lower()
            if host not in _LOCAL_HOSTS:
                raise ValueError("bank_api_url must use HTTPS in production (require_https=True)")

        if self.role in ("send", "both"):
            if not self.terminal_id:
                raise ValueError("terminal_id is required for send/both roles")
            alg = normalize_signature_alg(self.signature_alg)
            if alg == "HMAC-SHA256":
                if not self.signing_key or len(self.signing_key) < 16:
                    raise ValueError("signing_key must be at least 16 characters for HMAC-SHA256 send/both roles")
            elif alg == "ED25519":
                if not self.signing_key:
                    raise ValueError("signing_key (Ed25519 private key, base64) is required for ed25519 send/both roles")
            else:
                raise ValueError(f"Unsupported signature_alg: {self.signature_alg}")

        if not re.match(r"^\*{3}[0-9]{4}$", self.masked_account_suffix):
            raise ValueError("masked_account_suffix must match ***1234 format")


class CheckoutBroadcastAddon:
    def __init__(self, config: CheckoutBroadcastConfig) -> None:
        self.config = config
        self._transport = create_transport(config.transport)
        self._started = False
        self._active_checkout: dict[str, int | str] | None = None

    def _can_send(self) -> bool:
        return self.config.role in ("send", "both")

    def _can_receive(self) -> bool:
        return self.config.role in ("receive", "both")

    def _require_send_credentials(self) -> tuple[str, str]:
        terminal_id = self.config.terminal_id
        signing_key = self.config.signing_key
        if not terminal_id or not signing_key:
            raise RoleNotAllowedError("terminal_id and signing_key are required for send/both roles")
        return terminal_id, signing_key

    def start(self) -> None:
        if self._started:
            return
        if self._can_send():
            self._transport.start_send()
        if self._can_receive():
            self._transport.start_receive(self._handle_packet)
        self._started = True
        logger.debug("CheckoutBroadcastAddon started role=%s transport=%s", self.config.role, self.config.transport)

    def stop(self) -> None:
        self._transport.stop()
        self._started = False

    def send_checkout(self, data: CheckoutData) -> SignedPacket:
        if not self._can_send():
            raise RoleNotAllowedError("sendCheckout is not allowed when role is 'receive'")
        if data.amount_ngn < 1:
            raise ValueError("amount_ngn must be >= 1")
        if data.item_count < 1:
            raise ValueError("item_count must be >= 1")

        terminal_id, signing_key = self._require_send_credentials()
        reuse_session = None
        if (
            self._active_checkout
            and self._active_checkout["amount_ngn"] == data.amount_ngn
            and self._active_checkout["item_count"] == data.item_count
        ):
            reuse_session = str(self._active_checkout["session_uuid_v4"])

        payload = build_payload(
            terminal_id=terminal_id,
            amount_ngn=data.amount_ngn,
            item_count=data.item_count,
            bank_name=self.config.bank_name,
            masked_account_suffix=self.config.masked_account_suffix,
            session_uuid_v4=reuse_session,
        )
        signature_alg, signature = sign_packet(payload, signing_key, self.config.signature_alg)
        packet = SignedPacket(payload=payload, signature_alg=signature_alg, signature=signature)

        if not reuse_session:
            self._active_checkout = {
                "session_uuid_v4": payload["session_uuid_v4"],
                "amount_ngn": data.amount_ngn,
                "item_count": data.item_count,
            }

        if not self._started:
            self.start()
        self._transport.broadcast(packet)

        if self.config.on_send_complete:
            self.config.on_send_complete(payload["session_uuid_v4"])
        return packet

    def refresh_checkout(self) -> SignedPacket | None:
        if not self._active_checkout:
            return None
        return self.send_checkout(
            CheckoutData(
                amount_ngn=int(self._active_checkout["amount_ngn"]),
                item_count=int(self._active_checkout["item_count"]),
            )
        )

    def cancel_checkout(self) -> None:
        if not self._active_checkout or not self.config.terminal_id:
            self._active_checkout = None
            return
        session_uuid = str(self._active_checkout["session_uuid_v4"])
        terminal_id = self.config.terminal_id
        self._active_checkout = None
        try:
            httpx.post(
                f"{self.config.bank_api_url.rstrip('/')}/sessions/cancel",
                json={"session_uuid_v4": session_uuid, "terminal_id": terminal_id},
                timeout=10.0,
            )
        except httpx.HTTPError:
            pass

    def _handle_packet(self, packet: SignedPacket) -> None:
        try:
            payment = self._verify_locally_and_with_bank(packet)
            if self.config.on_payment_received:
                self.config.on_payment_received(payment)
        except Exception as exc:
            logger.warning("Payment receive failed: %s", exc)
            if self.config.on_error:
                self.config.on_error(exc)
            else:
                raise

    def _verify_locally_and_with_bank(self, packet: SignedPacket) -> VerifiedPayment:
        payload = packet.payload if isinstance(packet.payload, dict) else packet.payload.model_dump()
        timestamp_ms = parse_timestamp_ms(payload)
        if timestamp_ms is None:
            raise VerificationError("Missing timestamp_ms in payload")
        if not is_timestamp_valid(timestamp_ms):
            raise VerificationError("Packet timestamp is outside the 10-minute window")

        session = payload["session_uuid_v4"]

        try:
            response = httpx.post(
                f"{self.config.bank_api_url.rstrip('/')}/verify-broadcast",
                json={
                    "payload": payload,
                    "signature_alg": packet.signature_alg,
                    "signature": packet.signature,
                },
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            raise VerificationError(f"Bank API unreachable: {exc}") from exc

        if response.status_code == 429:
            raise VerificationError("Bank API rate limit exceeded — retry shortly")

        if response.status_code != 200:
            detail = "Bank verification failed"
            try:
                detail = response.json().get("detail", detail)
            except Exception:
                pass
            raise VerificationError(detail)

        body = response.json()
        if not body.get("valid"):
            raise VerificationError(body.get("error", "Invalid broadcast packet"))

        return VerifiedPayment(
            merchant_name=body["merchant_name"],
            amount_ngn=body["amount_ngn"],
            masked_account_suffix=body["masked_account_suffix"],
            session_uuid=body["session_uuid"],
            terminal_id=body["terminal_id"],
        )

    def verify_with_known_key(self, packet: SignedPacket, signing_key: str) -> bool:
        """Local signature check used in conformance tests."""
        payload = packet.payload if isinstance(packet.payload, dict) else packet.payload.model_dump()
        return verify_signature(payload, signing_key, packet.signature)
