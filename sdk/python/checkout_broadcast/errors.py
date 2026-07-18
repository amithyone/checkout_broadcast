class BroadcastError(Exception):
    """Base error for checkout broadcast operations."""


class RoleNotAllowedError(BroadcastError):
    """Raised when an operation is not permitted for the configured role."""


class VerificationError(BroadcastError):
    """Raised when packet verification fails."""


class TransportError(BroadcastError):
    """Raised when the transport layer fails."""
