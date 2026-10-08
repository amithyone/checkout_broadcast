import XCTest
@testable import CheckoutBroadcast

final class BroadcastWireTests: XCTestCase {
    private func vectors() throws -> [[String: Any]] {
        let fixture = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("../../../../../tests/fixtures/wire_vectors.json")
            .standardizedFileURL
        let root = try JSONSerialization.jsonObject(with: Data(contentsOf: fixture)) as? [String: Any]
        return try XCTUnwrap(root?["vectors"] as? [[String: Any]])
    }

    /// Sorted keys; integers and decimals kept distinct so `649` never passes as `649.0`.
    private func canonical(_ value: Any) -> String {
        switch value {
        case let dict as [String: Any]:
            return "{" + dict.keys.sorted().map { "\"\($0)\":\(canonical(dict[$0]!))" }.joined(separator: ",") + "}"
        case let array as [Any]:
            return "[" + array.map(canonical).joined(separator: ",") + "]"
        case let s as String:
            return "\"\(s)\""
        case let n as NSNumber:
            if CFGetTypeID(n) == CFBooleanGetTypeID() { return n.boolValue ? "true" : "false" }
            return CFNumberIsFloatType(n) ? "d:\(n.doubleValue)" : "i:\(n.int64Value)"
        default:
            return "\(value)"
        }
    }

    func testExpandsSharedVectors() throws {
        for v in try vectors() {
            let name = v["name"] as? String ?? "?"
            let packetData = try JSONSerialization.data(withJSONObject: try XCTUnwrap(v["packet"]))
            let packet = try XCTUnwrap(BroadcastWire.parse(packetData), name)
            XCTAssertEqual(canonical(v["verify_body"]!), canonical(packet.verifyBody), name)
            XCTAssertEqual((v["amount_ngn"] as? NSNumber)?.doubleValue ?? -1, packet.amountNgn, accuracy: 0.0001, name)
            XCTAssertEqual(v["is_presence"] as? Bool, packet.isPresence, name)

            let roundTrip = try JSONSerialization.jsonObject(with: packet.verifyBodyData())
            XCTAssertEqual(canonical(v["verify_body"]!), canonical(roundTrip), "\(name) (serialized)")
        }
    }

    func testStripsNullPaddingFromGattRead() throws {
        let first = try XCTUnwrap(try vectors().first?["packet"])
        var data = try JSONSerialization.data(withJSONObject: first)
        data.append(contentsOf: [0, 0])
        XCTAssertNotNil(BroadcastWire.parse(data))
    }

    func testRejectsNonPackets() {
        XCTAssertNil(BroadcastWire.parse("hello"))
        XCTAssertNil(BroadcastWire.parse("{\"p\":{\"sid\":\"\",\"tid\":\"x\"},\"sig\":\"s\"}"))
        XCTAssertNil(BroadcastWire.parse("{\"payload\":{\"terminal_id\":\"x\"}}"))
    }

    func testTerminalLabels() {
        XCTAssertEqual(BroadcastWire.terminalLabel("TERM-001"), "01")
        XCTAssertEqual(BroadcastWire.terminalLabel("till 7"), "07")
        XCTAssertEqual(BroadcastWire.terminalLabel("CP-1RK8Z"), "RK8Z")
        XCTAssertEqual(BroadcastWire.terminalLabel("ab"), "AB")
    }
}
