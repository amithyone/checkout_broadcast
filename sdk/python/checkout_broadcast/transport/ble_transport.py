from __future__ import annotations

import asyncio
import json
import logging
import platform
import threading
from typing import Callable, Optional

from checkout_broadcast.errors import TransportError
from checkout_broadcast.protocol import SignedPacket
from checkout_broadcast.transport.ble_constants import PACKET_CHAR_UUID, SERVICE_UUID

logger = logging.getLogger(__name__)

_PERIPHERAL_PLATFORMS = {"Windows", "Linux"}


def _peripheral_supported() -> bool:
    return platform.system() in _PERIPHERAL_PLATFORMS


class BleTransport:
    """
    BLE GATT transport:
    - Sender: GATT peripheral exposing signed packet JSON (Windows/Linux)
    - Receiver: scans for SERVICE_UUID, connects, reads PACKET_CHAR_UUID
    """

    def __init__(self) -> None:
        self._on_packet: Optional[Callable[[SignedPacket], None]] = None
        self._sending = False
        self._receiving = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._server = None
        self._scanner = None
        self._latest_packet_bytes = b""
        self._seen_sessions: set[str] = set()
        self._scan_task: Optional[asyncio.Task] = None

    def start_send(self) -> None:
        if not _peripheral_supported():
            raise TransportError(
                f"BLE send (GATT peripheral) is not supported on {platform.system()}. "
                "Use Windows/Linux for POS send, or transport='simulated'."
            )
        self._sending = True
        self._run_async(self._start_server())

    def start_receive(self, on_packet: Callable[[SignedPacket], None]) -> None:
        self._on_packet = on_packet
        self._receiving = True
        self._run_async(self._start_scanner())

    def broadcast(self, packet: SignedPacket) -> None:
        if not self._sending:
            return
        self._latest_packet_bytes = json.dumps(packet.model_dump(), separators=(",", ":")).encode(
            "utf-8"
        )
        if self._loop and self._server:
            future = asyncio.run_coroutine_threadsafe(self._update_characteristic(), self._loop)
            future.result(timeout=10)

    def stop(self) -> None:
        if self._loop:
            future = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
            try:
                future.result(timeout=10)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
        self._thread = None
        self._loop = None
        self._sending = False
        self._receiving = False
        self._on_packet = None

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop and self._thread and self._thread.is_alive():
            return self._loop
        ready = threading.Event()

        def _run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            ready.set()
            loop.run_forever()
            loop.close()

        self._thread = threading.Thread(target=_run, name="checkout-ble", daemon=True)
        self._thread.start()
        ready.wait(timeout=5)
        if not self._loop:
            raise TransportError("Failed to start BLE event loop")
        return self._loop

    def _run_async(self, coro) -> None:
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        future.result(timeout=30)

    async def _start_server(self) -> None:
        try:
            from bleak import BleakServer
        except ImportError as exc:
            raise TransportError(
                "bleak is not installed. Run: pip install -r requirements-ble.txt"
            ) from exc

        self._server = BleakServer()
        try:
            await self._server.add_new_service(SERVICE_UUID)
            await self._server.add_new_characteristic(
                SERVICE_UUID,
                PACKET_CHAR_UUID,
                properties=["read", "notify"],
                value=bytearray(self._latest_packet_bytes),
            )
        except AttributeError:
            self._server = BleakServer(
                services=[
                    {
                        "uuid": SERVICE_UUID,
                        "characteristics": [
                            {
                                "uuid": PACKET_CHAR_UUID,
                                "properties": ["read", "notify"],
                                "value": bytearray(self._latest_packet_bytes),
                                "permissions": ["readable"],
                            }
                        ],
                    }
                ]
            )
        await self._server.start()
        logger.info("BLE GATT server started (service %s)", SERVICE_UUID)

    async def _update_characteristic(self) -> None:
        if not self._server:
            return
        for service in self._server.services:
            for char in service.characteristics:
                if char.uuid.lower() == PACKET_CHAR_UUID.lower():
                    char.value = bytearray(self._latest_packet_bytes)
                    if "notify" in char.properties:
                        await self._server.notify(char.uuid, char.value)

    async def _start_scanner(self) -> None:
        try:
            from bleak import BleakClient, BleakScanner
        except ImportError as exc:
            raise TransportError(
                "bleak is not installed. Run: pip install -r requirements-ble.txt"
            ) from exc

        async def _scan_loop() -> None:
            while self._receiving:
                devices = await BleakScanner.discover(
                    service_uuids=[SERVICE_UUID],
                    timeout=5.0,
                )
                for device in devices:
                    if not self._receiving:
                        break
                    await self._read_device(device.address, BleakClient)
                await asyncio.sleep(0.5)

        self._scan_task = asyncio.create_task(_scan_loop())

    async def _read_device(self, address: str, bleak_client_cls) -> None:
        try:
            async with bleak_client_cls(address, timeout=10.0) as client:
                data = await client.read_gatt_char(PACKET_CHAR_UUID)
                if not data:
                    return
                packet = SignedPacket.model_validate_json(data.decode("utf-8"))
                session = packet.payload.session_uuid_v4
                if session in self._seen_sessions:
                    return
                self._seen_sessions.add(session)
                if self._on_packet:
                    self._on_packet(packet)
        except Exception as exc:
            logger.debug("BLE read failed for %s: %s", address, exc)

    async def _shutdown(self) -> None:
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
            self._scan_task = None
        if self._server:
            await self._server.stop()
            self._server = None
