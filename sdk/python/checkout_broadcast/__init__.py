"""Checkout Broadcast — cross-platform payment broadcast SDK (Python)."""

from checkout_broadcast.addon import CheckoutBroadcastAddon, CheckoutBroadcastConfig
from checkout_broadcast.errors import RoleNotAllowedError, VerificationError
from checkout_broadcast.protocol import CheckoutData, SignedPacket, VerifiedPayment

__all__ = [
    "CheckoutBroadcastAddon",
    "CheckoutBroadcastConfig",
    "CheckoutData",
    "RoleNotAllowedError",
    "SignedPacket",
    "VerificationError",
    "VerifiedPayment",
]
