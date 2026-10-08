import CoreBluetooth
import Foundation

public enum BleConstants {
    public static let serviceUUID = CBUUID(string: "CBBC0001-0000-4000-8000-000000000001")
    public static let packetCharUUID = CBUUID(string: "CBBC0002-0000-4000-8000-000000000001")
    public static let connectTimeout: TimeInterval = 12
    public static let readCooldown: TimeInterval = 4
}

/// Listens for Checkout Broadcast tills and hands each signed packet to `onPacket`.
///
/// - Scans without a service filter: many Windows POS adapters don't put the UUID in the advert.
///   Results are matched in `looksLikeCheckout`. iOS only allows unfiltered scans in the
///   foreground — run this while the pay-at-shop screen is open.
/// - Uses the packet embedded in advert service/manufacturer data when present (no connection).
/// - Otherwise connects to one till at a time and **reads** the packet characteristic. Never
///   subscribes to notifications and never pairs. Verification always happens server-side.
/// - Feeds every advert's RSSI into `proximity` and skips the connection for tills that are clearly
///   far away. While scanning, `onTillsChanged` fires about once a second so a picker can list only
///   in-range tills (`TillProximity.evaluate`). Never auto-select a till from this.
public final class CheckoutBleReceiver: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    private var central: CBCentralManager!
    private var onPacket: ((Data) -> Void)?
    private var onError: ((Error) -> Void)?
    private var scanning = false

    public let proximity = TillProximity()
    public var onTillsChanged: (() -> Void)?
    private var tillsTimer: Timer?
    private var tillsWereListed = false

    private var activePeripheral: CBPeripheral?
    private var timeoutWork: DispatchWorkItem?
    private var queue: [CBPeripheral] = []
    private var queuedIds = Set<UUID>()
    private var readIds = Set<UUID>()
    private var recentlyReadAt: [UUID: Date] = [:]

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
        scanning = true
        beginScanIfReady()
        tillsTimer?.invalidate()
        tillsTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            guard let self, self.scanning else { return }
            let hasTills = !self.proximity.isEmpty
            if hasTills || self.tillsWereListed { self.onTillsChanged?() }
            self.tillsWereListed = hasTills
        }
    }

    public func stopScanning() {
        scanning = false
        central.stopScan()
        tillsTimer?.invalidate()
        tillsTimer = nil
        tillsWereListed = false
        proximity.clear()
        queue.removeAll()
        queuedIds.removeAll()
        readIds.removeAll()
        finishActive()
    }

    /// Forget tills already read so they are picked up again (e.g. when a picker reopens).
    public func resetSeen() {
        readIds.removeAll()
        recentlyReadAt.removeAll()
    }

    private func beginScanIfReady() {
        guard scanning, central.state == .poweredOn else { return }
        central.scanForPeripherals(withServices: nil, options: [
            CBCentralManagerScanOptionAllowDuplicatesKey: true,
        ])
    }

    public func centralManagerDidUpdateState(_ central: CBCentralManager) {
        switch central.state {
        case .poweredOn:
            beginScanIfReady()
        case .unauthorized:
            onError?(NSError(domain: "CheckoutBroadcast", code: 10, userInfo: [
                NSLocalizedDescriptionKey: "Bluetooth permission denied",
            ]))
        case .poweredOff:
            if scanning {
                onError?(NSError(domain: "CheckoutBroadcast", code: 11, userInfo: [
                    NSLocalizedDescriptionKey: "Turn on Bluetooth to pay at shop",
                ]))
            }
        default:
            break
        }
    }

    private func looksLikeCheckout(_ peripheral: CBPeripheral, _ ad: [String: Any]) -> Bool {
        if let uuids = ad[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID], uuids.contains(BleConstants.serviceUUID) {
            return true
        }
        if let serviceData = ad[CBAdvertisementDataServiceDataKey] as? [CBUUID: Data],
           serviceData[BleConstants.serviceUUID] != nil {
            return true
        }
        let name = ((ad[CBAdvertisementDataLocalNameKey] as? String) ?? peripheral.name ?? "").uppercased()
        return name.contains("CHECKOUT") || name.contains("CHEKO") || name.hasPrefix("CP-") || name.hasPrefix("CN")
    }

    private func packetFromAdvert(_ ad: [String: Any]) -> Data? {
        if let serviceData = ad[CBAdvertisementDataServiceDataKey] as? [CBUUID: Data],
           let data = serviceData[BleConstants.serviceUUID],
           BroadcastWire.looksLikePacket(data) {
            return data
        }
        if let mfr = ad[CBAdvertisementDataManufacturerDataKey] as? Data, BroadcastWire.looksLikePacket(mfr) {
            return mfr
        }
        return nil
    }

    public func centralManager(
        _ central: CBCentralManager,
        didDiscover peripheral: CBPeripheral,
        advertisementData: [String: Any],
        rssi RSSI: NSNumber
    ) {
        guard scanning, looksLikeCheckout(peripheral, advertisementData) else { return }
        let id = peripheral.identifier
        let now = Date()
        proximity.updateSignal(deviceId: id.uuidString, rssi: RSSI.intValue, nowMs: TillProximity.nowMs())
        if let last = recentlyReadAt[id], now.timeIntervalSince(last) < BleConstants.readCooldown {
            return
        }

        if let data = packetFromAdvert(advertisementData) {
            recentlyReadAt[id] = now
            deliver(id, data)
            return
        }

        guard proximity.shouldPeek(deviceId: id.uuidString) else { return }
        guard !queuedIds.contains(id), !readIds.contains(id) else { return }
        queuedIds.insert(id)
        queue.append(peripheral)
        drainQueue()
    }

    private func drainQueue() {
        guard activePeripheral == nil, scanning, !queue.isEmpty else { return }
        let peripheral = queue.removeFirst()
        queuedIds.remove(peripheral.identifier)
        activePeripheral = peripheral
        peripheral.delegate = self

        let work = DispatchWorkItem { [weak self] in self?.finishAndContinue(peripheral) }
        timeoutWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + BleConstants.connectTimeout, execute: work)
        central.connect(peripheral, options: nil)
    }

    private func finishActive() {
        timeoutWork?.cancel()
        timeoutWork = nil
        guard let peripheral = activePeripheral else { return }
        activePeripheral = nil
        recentlyReadAt[peripheral.identifier] = Date()
        central.cancelPeripheralConnection(peripheral)
    }

    /// Ignores callbacks from a connection that has already been replaced.
    private func finishAndContinue(_ peripheral: CBPeripheral) {
        guard activePeripheral === peripheral else { return }
        finishActive()
        drainQueue()
    }

    public func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        peripheral.discoverServices([BleConstants.serviceUUID])
    }

    public func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        finishAndContinue(peripheral)
    }

    public func centralManager(
        _ central: CBCentralManager,
        didDisconnectPeripheral peripheral: CBPeripheral,
        error: Error?
    ) {
        finishAndContinue(peripheral)
    }

    public func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        guard error == nil,
              let service = peripheral.services?.first(where: { $0.uuid == BleConstants.serviceUUID })
        else {
            finishAndContinue(peripheral)
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
              let char = service.characteristics?.first(where: { $0.uuid == BleConstants.packetCharUUID }),
              char.properties.contains(.read)
        else {
            finishAndContinue(peripheral)
            return
        }
        peripheral.readValue(for: char)
    }

    public func peripheral(
        _ peripheral: CBPeripheral,
        didUpdateValueFor characteristic: CBCharacteristic,
        error: Error?
    ) {
        if error == nil,
           characteristic.uuid == BleConstants.packetCharUUID,
           let data = characteristic.value,
           BroadcastWire.looksLikePacket(data) {
            readIds.insert(peripheral.identifier)
            deliver(peripheral.identifier, data)
        }
        finishAndContinue(peripheral)
    }

    private func deliver(_ id: UUID, _ data: Data) {
        if let terminalId = BroadcastWire.parse(data)?.terminalId, !terminalId.isEmpty {
            proximity.setTerminal(deviceId: id.uuidString, terminalId: terminalId)
        }
        onPacket?(data)
    }
}
