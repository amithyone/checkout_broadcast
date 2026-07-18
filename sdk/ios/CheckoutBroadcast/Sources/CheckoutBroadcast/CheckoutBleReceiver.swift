import CoreBluetooth
import Foundation

public enum BleConstants {
    public static let serviceUUID = CBUUID(string: "CBBC0001-0000-4000-8000-000000000001")
    public static let packetCharUUID = CBUUID(string: "CBBC0002-0000-4000-8000-000000000001")
    public static let maxAgeMs: Int64 = 600_000
}

/// CBCentralManager scanner — connect, read GATT packet characteristic, disconnect.
public final class CheckoutBleReceiver: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    private var central: CBCentralManager!
    private var onPacket: ((Data) -> Void)?
    private var onError: ((Error) -> Void)?
    private var connectingPeripheral: CBPeripheral?
    private var seenAddresses = Set<String>()
    private var lastSeenAt: [String: Date] = [:]

    public override init() {
        super.init()
        central = CBCentralManager(delegate: self, queue: nil)
    }

    public func startScanning(
        onPacket: @escaping (Data) -> Void,
        onError: ((Error) -> Void)? = nil
    ) {
        self.onPacket = onPacket
        self.onError = onError
        if central.state == .poweredOn {
            central.scanForPeripherals(withServices: [BleConstants.serviceUUID], options: [
                CBCentralManagerScanOptionAllowDuplicatesKey: false,
            ])
        }
    }

    public func stopScanning() {
        central.stopScan()
        if let peripheral = connectingPeripheral {
            central.cancelPeripheralConnection(peripheral)
            connectingPeripheral = nil
        }
    }

    public func centralManagerDidUpdateState(_ central: CBCentralManager) {
        if central.state == .poweredOn, onPacket != nil {
            central.scanForPeripherals(withServices: [BleConstants.serviceUUID], options: nil)
        }
    }

    public func centralManager(
        _ central: CBCentralManager,
        didDiscover peripheral: CBPeripheral,
        advertisementData: [String: Any],
        rssi RSSI: NSNumber
    ) {
        let id = peripheral.identifier.uuidString
        let now = Date()
        if let last = lastSeenAt[id], now.timeIntervalSince(last) < 3 {
            return
        }
        lastSeenAt[id] = now
        if connectingPeripheral != nil {
            return
        }
        connectingPeripheral = peripheral
        central.stopScan()
        central.connect(peripheral, options: nil)
    }

    public func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        peripheral.delegate = self
        peripheral.discoverServices([BleConstants.serviceUUID])
    }

    public func centralManager(
        _ central: CBCentralManager,
        didFailToConnect peripheral: CBPeripheral,
        error: Error?
    ) {
        connectingPeripheral = nil
        onError?(error ?? NSError(domain: "CheckoutBroadcast", code: 1, userInfo: [
            NSLocalizedDescriptionKey: "Failed to connect to POS terminal",
        ]))
        if onPacket != nil {
            central.scanForPeripherals(withServices: [BleConstants.serviceUUID], options: nil)
        }
    }

    public func centralManager(
        _ central: CBCentralManager,
        didDisconnectPeripheral peripheral: CBPeripheral,
        error: Error?
    ) {
        connectingPeripheral = nil
        if onPacket != nil {
            central.scanForPeripherals(withServices: [BleConstants.serviceUUID], options: nil)
        }
    }

    public func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        guard error == nil,
              let service = peripheral.services?.first(where: { $0.uuid == BleConstants.serviceUUID })
        else {
            central.cancelPeripheralConnection(peripheral)
            return
        }
        peripheral.discoverCharacteristics([BleConstants.packetCharUUID], for: service)
    }

    public func peripheral(
        _ peripheral: CBPeripheral,
        didDiscoverCharacteristicsFor service: CBService,
        error: Error?
    ) {
        guard error == nil,
              let char = service.characteristics?.first(where: { $0.uuid == BleConstants.packetCharUUID })
        else {
            central.cancelPeripheralConnection(peripheral)
            return
        }
        peripheral.readValue(for: char)
    }

    public func peripheral(
        _ peripheral: CBPeripheral,
        didUpdateValueFor characteristic: CBCharacteristic,
        error: Error?
    ) {
        guard characteristic.uuid == BleConstants.packetCharUUID,
              let data = characteristic.value,
              !data.isEmpty
        else {
            central.cancelPeripheralConnection(peripheral)
            return
        }
        onPacket?(data)
        central.cancelPeripheralConnection(peripheral)
    }
}
