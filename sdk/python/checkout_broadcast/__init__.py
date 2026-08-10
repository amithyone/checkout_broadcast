"""Checkout Broadcast — cross-platform payment broadcast SDK (Python)."""

from checkout_broadcast.addon import CheckoutBroadcastAddon, CheckoutBroadcastConfig
from checkout_broadcast.amount import from_packet_amount, to_packet_amount
from checkout_broadcast.api_url import normalize_bank_api_url, sync_signing_key_url, verify_broadcast_url
from checkout_broadcast.errors import RoleNotAllowedError, VerificationError
from checkout_broadcast.protocol import CheckoutData, SignedPacket, VerifiedPayment
from checkout_broadcast.wire_format import (
    encode_wire_envelope,
    normalize_ble_read_for_verify,
    wire_to_verify_envelope,
)

__all__ = [
    "CheckoutBroadcastAddon",
    "CheckoutBroadcastConfig",
    "CheckoutData",
    "RoleNotAllowedError",
    "SignedPacket",
    "VerificationError",
    "VerifiedPayment",
    "encode_wire_envelope",
    "from_packet_amount",
    "normalize_bank_api_url",
    "normalize_ble_read_for_verify",
    "sync_signing_key_url",
    "to_packet_amount",
    "verify_broadcast_url",
    "wire_to_verify_envelope",
]
