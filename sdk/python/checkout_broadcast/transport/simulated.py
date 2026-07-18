from __future__ import annotations

from typing import Callable

from checkout_broadcast.protocol import SignedPacket
from checkout_broadcast.transport.base import BroadcastTransport
from checkout_broadcast.transport.ble_transport import BleTransport

# Module-level bus for cross-process dev demos (HTTP bridge can attach here).
_global_listeners: list[Callable[[SignedPacket], None]] = []


class SimulatedTransport:
    """In-process pub/sub transport for development and tests."""

    def __init__(self) -> None:
        self._on_packet: Callable[[SignedPacket], None] | None = None
        self._receiving = False
        self._sending = False

    def start_send(self) -> None:
        self._sending = True

    def start_receive(self, on_packet: Callable[[SignedPacket], None]) -> None:
        self._on_packet = on_packet
        self._receiving = True
        _global_listeners.append(on_packet)

    def broadcast(self, packet: SignedPacket) -> None:
        if not self._sending:
            return
        for listener in list(_global_listeners):
            listener(packet)
        if self._on_packet:
            self._on_packet(packet)

    def stop(self) -> None:
        if self._on_packet and self._on_packet in _global_listeners:
            _global_listeners.remove(self._on_packet)
        self._receiving = False
        self._sending = False
        self._on_packet = None


def create_transport(kind: str) -> BroadcastTransport:
    if kind == "ble":
        return BleTransport()
    return SimulatedTransport()
