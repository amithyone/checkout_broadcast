import Foundation

/// Defaults from spec/ble-transport.md "Proximity filtering".
public struct ProximityConfig: Equatable {
    public var alpha = 0.3
    public var inRangeDbm = -75.0
    public var windowDb = 12.0
    public var hysteresisDb = 5.0
    public var hysteresisMs: Int64 = 3_000
    public var staleMs: Int64 = 10_000
    public var minPeekDbm = -90.0

    public init() {}
}

/// Snapshot of one till's smoothed signal. `inRange` is false for tills only listed because a push named them.
public struct TillSignal: Equatable {
    public let deviceId: String
    public let terminalId: String?
    public let smoothedRssi: Double
    public let lastHeardMs: Int64
    public let inRange: Bool
}

public struct TillProximityView: Equatable {
    public let visible: [TillSignal]
    public let hidden: [TillSignal]
}

/// Splits tills into in-range (`visible`) and farther (`hidden`) from smoothed RSSI. It never picks a
/// till: the customer always taps one and confirms with PIN.
///
/// Thread-safe. Feed every advert with `updateSignal`; call `evaluate` to refresh the lists.
public final class TillProximity {
    private struct Entry {
        let deviceId: String
        var terminalId: String?
        var smoothed: Double
        var lastHeardMs: Int64
        var shown = false
        var belowSinceMs: Int64?
    }

    public let config: ProximityConfig
    private var tills: [String: Entry] = [:]
    private let lock = NSLock()

    public init(config: ProximityConfig = ProximityConfig()) {
        self.config = config
    }

    public static func nowMs() -> Int64 {
        Int64(Date().timeIntervalSince1970 * 1000)
    }

    /// Records one advert and returns the smoothed RSSI, or nil when `rssi` is unknown (>= 0, e.g. 127).
    @discardableResult
    public func updateSignal(deviceId: String, rssi: Int, nowMs: Int64, terminalId: String? = nil) -> Double? {
        lock.lock()
        defer { lock.unlock() }
        if let terminalId, tills[deviceId] != nil { tills[deviceId]?.terminalId = terminalId }
        if rssi >= 0 { return tills[deviceId]?.smoothed }
        guard var till = tills[deviceId] else {
            tills[deviceId] = Entry(deviceId: deviceId, terminalId: terminalId, smoothed: Double(rssi), lastHeardMs: nowMs)
            return Double(rssi)
        }
        till.smoothed = config.alpha * Double(rssi) + (1 - config.alpha) * till.smoothed
        till.lastHeardMs = nowMs
        tills[deviceId] = till
        return till.smoothed
    }

    public func setTerminal(deviceId: String, terminalId: String) {
        lock.lock()
        defer { lock.unlock() }
        tills[deviceId]?.terminalId = terminalId
    }

    /// False when the till is clearly too far to be worth a GATT connection.
    public func shouldPeek(deviceId: String) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        guard let till = tills[deviceId] else { return true }
        return till.smoothed >= config.minPeekDbm
    }

    public var isEmpty: Bool {
        lock.lock()
        defer { lock.unlock() }
        return tills.isEmpty
    }

    public func clear() {
        lock.lock()
        defer { lock.unlock() }
        tills.removeAll()
    }

    /// `preferred` is a terminal ID (or device id) named in a push: always visible and first.
    public func evaluate(nowMs: Int64, preferred: String? = nil) -> TillProximityView {
        lock.lock()
        defer { lock.unlock() }
        tills = tills.filter { nowMs - $0.value.lastHeardMs <= config.staleMs }
        guard let strongest = tills.values.map(\.smoothed).max() else {
            return TillProximityView(visible: [], hidden: [])
        }

        for key in Array(tills.keys) {
            guard var till = tills[key] else { continue }
            let s = till.smoothed
            if s >= config.inRangeDbm && s >= strongest - config.windowDb {
                till.shown = true
                till.belowSinceMs = nil
            } else if till.shown {
                let wellBelow = s < config.inRangeDbm - config.hysteresisDb ||
                    s < strongest - config.windowDb - config.hysteresisDb
                if !wellBelow {
                    till.belowSinceMs = nil
                } else if let since = till.belowSinceMs {
                    if nowMs - since >= config.hysteresisMs {
                        till.shown = false
                        till.belowSinceMs = nil
                    }
                } else {
                    till.belowSinceMs = nowMs
                }
            }
            tills[key] = till
        }

        let pref = (preferred ?? "").trimmingCharacters(in: .whitespaces).uppercased()
        func isPreferred(_ t: Entry) -> Bool {
            !pref.isEmpty && (pref == t.terminalId?.uppercased() || pref == t.deviceId.uppercased())
        }
        let sorted = tills.values.sorted { a, b in
            let pa = isPreferred(a), pb = isPreferred(b)
            if pa != pb { return pa }
            if a.smoothed != b.smoothed { return a.smoothed > b.smoothed }
            return (a.terminalId ?? a.deviceId) < (b.terminalId ?? b.deviceId)
        }
        func snap(_ t: Entry) -> TillSignal {
            TillSignal(deviceId: t.deviceId, terminalId: t.terminalId, smoothedRssi: t.smoothed,
                       lastHeardMs: t.lastHeardMs, inRange: t.shown)
        }
        let visible = sorted.filter { $0.shown || isPreferred($0) }.map(snap)
        let hidden = sorted.filter { !($0.shown || isPreferred($0)) }.map(snap)
        return TillProximityView(visible: visible, hidden: hidden)
    }

    /// Log-distance path loss. For logs only — too noisy on phones to decide anything.
    public static func estimateDistanceMeters(rssi: Double, txPowerDbm: Double = -59, pathLossN: Double = 2.5) -> Double {
        pow(10, (txPowerDbm - rssi) / (10 * pathLossN))
    }
}
