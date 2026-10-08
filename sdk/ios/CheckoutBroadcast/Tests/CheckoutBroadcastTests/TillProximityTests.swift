import XCTest
@testable import CheckoutBroadcast

final class TillProximityTests: XCTestCase {
    private func fixture() throws -> [String: Any] {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("../../../../../tests/fixtures/proximity_vectors.json")
            .standardizedFileURL
        return try XCTUnwrap(try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
    }

    func testDefaultsMatchFixtureConfig() throws {
        let c = try XCTUnwrap(try fixture()["config"] as? [String: Any])
        let d = ProximityConfig()
        XCTAssertEqual(d.alpha, c["alpha"] as? Double)
        XCTAssertEqual(d.inRangeDbm, (c["in_range_dbm"] as? NSNumber)?.doubleValue)
        XCTAssertEqual(d.windowDb, (c["window_db"] as? NSNumber)?.doubleValue)
        XCTAssertEqual(d.hysteresisDb, (c["hysteresis_db"] as? NSNumber)?.doubleValue)
        XCTAssertEqual(d.hysteresisMs, (c["hysteresis_ms"] as? NSNumber)?.int64Value)
        XCTAssertEqual(d.staleMs, (c["stale_ms"] as? NSNumber)?.int64Value)
        XCTAssertEqual(d.minPeekDbm, (c["min_peek_dbm"] as? NSNumber)?.doubleValue)
    }

    func testSharedVectors() throws {
        let vectors = try XCTUnwrap(try fixture()["vectors"] as? [[String: Any]])
        for v in vectors {
            let name = v["name"] as? String ?? "?"
            let filter = TillProximity()
            for step in try XCTUnwrap(v["steps"] as? [[String: Any]]) {
                let t = try XCTUnwrap(step["t"] as? NSNumber).int64Value
                if let s = step["signal"] as? [String: Any] {
                    filter.updateSignal(
                        deviceId: try XCTUnwrap(s["device"] as? String),
                        rssi: try XCTUnwrap(s["rssi"] as? NSNumber).intValue,
                        nowMs: t,
                        terminalId: s["terminal_id"] as? String
                    )
                }
                guard let check = step["check"] as? [String: Any] else { continue }
                let view = filter.evaluate(nowMs: t, preferred: check["preferred"] as? String)
                XCTAssertEqual(view.visible.map(\.deviceId), check["visible"] as? [String], "\(name) t=\(t) visible")
                XCTAssertEqual(view.hidden.map(\.deviceId), check["hidden"] as? [String], "\(name) t=\(t) hidden")
                let byId = Dictionary(uniqueKeysWithValues: (view.visible + view.hidden).map { ($0.deviceId, $0) })
                for (device, expected) in check["smoothed"] as? [String: NSNumber] ?? [:] {
                    XCTAssertEqual(byId[device]?.smoothedRssi ?? .nan, expected.doubleValue, accuracy: 0.01,
                                   "\(name) t=\(t) smoothed \(device)")
                }
                for (device, expected) in check["peek"] as? [String: Bool] ?? [:] {
                    XCTAssertEqual(filter.shouldPeek(deviceId: device), expected, "\(name) t=\(t) peek \(device)")
                }
            }
        }
    }

    func testDistanceIsForLogsOnly() {
        XCTAssertEqual(TillProximity.estimateDistanceMeters(rssi: -59), 1, accuracy: 0.0001)
    }
}
