import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk" / "python"))

from checkout_broadcast.errors import TransportError
from checkout_broadcast.protocol import CheckoutData
from checkout_broadcast.transport.ble_transport import BleTransport, _peripheral_supported


def test_peripheral_not_supported_on_darwin():
    with patch("checkout_broadcast.transport.ble_transport.platform.system", return_value="Darwin"):
        transport = BleTransport()
        with pytest.raises(TransportError, match="not supported on Darwin"):
            transport.start_send()


def test_ble_receive_requires_bleak():
    transport = BleTransport()
    with patch.dict(sys.modules, {"bleak": None}):
        with pytest.raises(TransportError, match="bleak is not installed"):
            transport.start_receive(lambda _p: None)


def test_create_transport_ble_kind():
    from checkout_broadcast.transport.simulated import create_transport

    t = create_transport("ble")
    assert isinstance(t, BleTransport)
