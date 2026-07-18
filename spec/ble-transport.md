# BLE GATT Transport Profile

Checkout Broadcast uses a custom GATT service for signed packet delivery.

## UUIDs

| Name | UUID |
|------|------|
| Service | `cbbc0001-0000-4000-8000-000000000001` |
| Packet characteristic | `cbbc0002-0000-4000-8000-000000000001` |

## Flow

### Sender (POS — Windows/Linux)

1. Start GATT peripheral advertising `SERVICE_UUID`
2. On checkout complete, write signed packet JSON to `PACKET_CHAR_UUID`
3. Notify connected centrals (optional)

### Receiver (Mobile/Web)

1. Scan for `SERVICE_UUID`
2. Connect to peripheral
3. Read `PACKET_CHAR_UUID` → parse signed JSON envelope
4. Verify via bank API

## Platform support

| Platform | Send (peripheral) | Receive (central) |
|----------|-------------------|-------------------|
| Windows | Python bleak | Python bleak / Web BT |
| Linux | Python bleak | Python bleak |
| macOS | Not supported (Python) | Web BT / iOS SDK |
| Android | Android SDK | Android SDK |
| iOS | iOS SDK (phase 2) | iOS SDK |

Install Python BLE: `pip install -r requirements-ble.txt` (Windows/Linux).
