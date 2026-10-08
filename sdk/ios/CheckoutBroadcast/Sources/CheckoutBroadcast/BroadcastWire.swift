import Foundation

/// A packet read from a till, already expanded to the body `POST /verify-broadcast` expects.
///
/// `amountNgn` is in naira for display and transfer. Compact wire `amt` is kobo; legacy
/// `total_amount_ngn` is naira.
public struct BroadcastPacket {
    public let verifyBody: [String: Any]
    public let sessionUuid: String
    public let terminalId: String
    public let amountNgn: Double
    public let isPresence: Bool
    public let isCompactWire: Bool

    public func verifyBodyData() throws -> Data {
        try JSONSerialization.data(withJSONObject: verifyBody, options: [.sortedKeys])
    }
}

/// Compact BLE wire `{p:{v,sid,tid,ts,amt,msk,k},alg,sig}` and legacy `{payload,signature_alg,signature}`.
///
/// The signature covers the expanded canonical payload, so keys must be added exactly as the till
/// signed them: `session_kind` only when `k` is sent, `account_info_public_display` only when `msk`
/// is non-empty. Matches sdk/typescript/src/bleWire.ts and bank_api/ble_wire.py.
public enum BroadcastWire {
    private static let presenceKinds: Set<String> = ["presence", "idle", "beacon"]
    private static let checkoutKinds: Set<String> = ["pos_checkout", "checkout"]
    private static let defaultProtocolVersion = 2.1

    public static func parse(_ data: Data) -> BroadcastPacket? {
        guard let text = String(data: data, encoding: .utf8) else { return nil }
        return parse(text)
    }

    public static func parse(_ text: String) -> BroadcastPacket? {
        let raw = text.replacingOccurrences(of: "\u{0000}", with: "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard raw.hasPrefix("{"),
              let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        if let p = obj["p"] as? [String: Any] {
            return fromCompactWire(obj, p)
        }
        return fromLegacy(obj)
    }

    /// True when bytes look like a JSON packet (used for advert-embedded payloads).
    public static func looksLikePacket(_ data: Data?) -> Bool {
        guard let data, !data.isEmpty else { return false }
        let head = String(decoding: data.prefix(8), as: UTF8.self)
        return head.trimmingCharacters(in: .whitespacesAndNewlines).hasPrefix("{")
    }

    /// Short till label for pickers: last 2 digits, else last 4 characters.
    public static func terminalLabel(_ terminalId: String) -> String {
        let trimmed = terminalId.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return "??" }
        let trailingDigits = String(trimmed.reversed().prefix(while: { $0.isASCII && $0.isNumber }).reversed())
        if !trailingDigits.isEmpty {
            return trailingDigits.count >= 2
                ? String(trailingDigits.suffix(2))
                : String(repeating: "0", count: 2 - trailingDigits.count) + trailingDigits
        }
        return trimmed.count <= 4 ? trimmed.uppercased() : String(trimmed.suffix(4))
    }

    private static func fromCompactWire(_ obj: [String: Any], _ p: [String: Any]) -> BroadcastPacket? {
        let sid = string(p["sid"])
        let tid = string(p["tid"])
        let sig = string(obj["sig"])
        guard !sid.isEmpty, !tid.isEmpty, !sig.isEmpty else { return nil }

        let amtKobo = number(p["amt"]) ?? 0
        let kind = string(p["k"]).lowercased()
        let amtMissing = p["amt"] == nil || p["amt"] is NSNull
        let presence = presenceKinds.contains(kind) || amtMissing || amtKobo == 0
        let koboRounded = Int64(amtKobo.rounded())

        var payload: [String: Any] = [
            "protocol_version": protocolVersion(p["v"]),
            "session_uuid_v4": sid,
            "terminal_id": tid,
            "timestamp_ms": number(p["ts"]).map { Int64($0) } ?? Int64(Date().timeIntervalSince1970 * 1000),
            "transaction_details": ["total_amount_ngn": presence ? Int64(0) : koboRounded],
        ]
        if presenceKinds.contains(kind) {
            payload["session_kind"] = "presence"
        } else if checkoutKinds.contains(kind) {
            payload["session_kind"] = "pos_checkout"
        }
        let msk = string(p["msk"])
        if !msk.isEmpty {
            payload["account_info_public_display"] = ["masked_account_suffix": msk]
        }

        let alg = string(obj["alg"])
        return BroadcastPacket(
            verifyBody: [
                "payload": payload,
                "signature_alg": alg.isEmpty ? "ed25519" : alg,
                "signature": sig,
            ],
            sessionUuid: sid,
            terminalId: tid,
            amountNgn: presence ? 0 : Double(koboRounded) / 100,
            isPresence: presence,
            isCompactWire: true
        )
    }

    private static func fromLegacy(_ obj: [String: Any]) -> BroadcastPacket? {
        guard let payload = obj["payload"] as? [String: Any] else { return nil }
        var sig = string(obj["signature"])
        if sig.isEmpty { sig = string(obj["sig"]) }
        var sid = string(payload["session_uuid_v4"])
        if sid.isEmpty { sid = string(payload["session_uuid"]) }
        let tid = string(payload["terminal_id"])
        guard !sig.isEmpty, !sid.isEmpty, !tid.isEmpty else { return nil }

        let tx = payload["transaction_details"] as? [String: Any]
        let amount = number(tx?["total_amount_ngn"]) ?? 0
        let presence = string(payload["session_kind"]).lowercased() == "presence" || amount <= 0
        let alg = string(obj["signature_alg"])
        return BroadcastPacket(
            verifyBody: [
                "payload": payload,
                "signature_alg": alg.isEmpty ? "HMAC-SHA256" : alg,
                "signature": sig,
            ],
            sessionUuid: sid,
            terminalId: tid,
            amountNgn: presence ? 0 : amount,
            isPresence: presence,
            isCompactWire: false
        )
    }

    private static func protocolVersion(_ raw: Any?) -> Any {
        if let n = raw as? NSNumber, !isBool(n) { return n }
        if let s = raw as? String, let d = Double(s.trimmingCharacters(in: .whitespaces)) { return d }
        return defaultProtocolVersion
    }

    private static func string(_ raw: Any?) -> String {
        guard let s = raw as? String else { return "" }
        return s.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func number(_ raw: Any?) -> Double? {
        if let n = raw as? NSNumber, !isBool(n) {
            let d = n.doubleValue
            return d.isFinite ? d : nil
        }
        if let s = raw as? String, let d = Double(s.trimmingCharacters(in: .whitespaces)), d.isFinite {
            return d
        }
        return nil
    }

    private static func isBool(_ n: NSNumber) -> Bool {
        CFGetTypeID(n) == CFBooleanGetTypeID()
    }
}
