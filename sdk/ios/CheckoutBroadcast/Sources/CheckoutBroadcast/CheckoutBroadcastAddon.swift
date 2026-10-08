import Foundation

public struct CheckoutBroadcastConfig {
    public let role: String
    public let bankApiUrl: String
    public let terminalId: String?
    public let signingKey: String?
    public let transport: String
    /// Extra headers on `POST /verify-broadcast`, e.g. the signed-in customer's session token.
    public var verifyHeaders: [String: String]
    public var onPaymentReceived: ((VerifiedPayment) -> Void)?
    public var onError: ((Error) -> Void)?

    public init(
        role: String,
        bankApiUrl: String,
        terminalId: String? = nil,
        signingKey: String? = nil,
        transport: String = "simulated",
        verifyHeaders: [String: String] = [:],
        onPaymentReceived: ((VerifiedPayment) -> Void)? = nil,
        onError: ((Error) -> Void)? = nil
    ) {
        self.role = role
        self.bankApiUrl = bankApiUrl
        self.terminalId = terminalId
        self.signingKey = signingKey
        self.transport = transport
        self.verifyHeaders = verifyHeaders
        self.onPaymentReceived = onPaymentReceived
        self.onError = onError
    }
}

public struct CheckoutData {
    public let amountNgn: Int
    public let itemCount: Int

    public init(amountNgn: Int, itemCount: Int = 1) {
        self.amountNgn = amountNgn
        self.itemCount = itemCount
    }
}

/// A verified till payment, ready to pre-fill a bank transfer.
///
/// `amountNgn` comes from the signed packet (compact wire kobo ÷ 100). When `isPresence` is true the
/// till is idle with no amount: ask the customer to enter one. Use `sessionUuid` as the transfer
/// idempotency key.
public struct VerifiedPayment {
    public let merchantName: String
    public let amountNgn: Double
    public let maskedAccountSuffix: String?
    public let sessionUuid: String
    public let terminalId: String
    public let recipientAccount: String?
    public let recipientBankCode: String?
    public let isPresence: Bool

    public init(
        merchantName: String,
        amountNgn: Double,
        maskedAccountSuffix: String?,
        sessionUuid: String,
        terminalId: String,
        recipientAccount: String? = nil,
        recipientBankCode: String? = nil,
        isPresence: Bool = false
    ) {
        self.merchantName = merchantName
        self.amountNgn = amountNgn
        self.maskedAccountSuffix = maskedAccountSuffix
        self.sessionUuid = sessionUuid
        self.terminalId = terminalId
        self.recipientAccount = recipientAccount
        self.recipientBankCode = recipientBankCode
        self.isPresence = isPresence
    }
}

public enum RoleNotAllowedError: Error {
    case sendNotAllowed
    case missingCredentials
}

public final class CheckoutBroadcastAddon {
    private let config: CheckoutBroadcastConfig
    private var started = false
    private var bleReceiver: CheckoutBleReceiver?
    private var seenSessions = Set<String>()

    public init(config: CheckoutBroadcastConfig) {
        self.config = config
    }

    public func start() throws {
        if started { return }
        if config.role == "receive" || config.role == "both" {
            if config.transport == "ble" {
                bleReceiver = CheckoutBleReceiver()
                bleReceiver?.startScanning(onPacket: { [weak self] data in
                    self?.handlePacketData(data)
                }, onError: { [weak self] error in
                    self?.config.onError?(error)
                })
            }
        }
        if config.role == "send" || config.role == "both" {
            if config.transport == "ble" {
                throw NSError(
                    domain: "CheckoutBroadcast",
                    code: 3,
                    userInfo: [NSLocalizedDescriptionKey: "iOS BLE send is phase 2. Use Windows/Linux POS for send."]
                )
            }
        }
        started = true
    }

    public func stop() {
        bleReceiver?.stopScanning()
        started = false
    }

    /// Forget sessions and tills already seen, e.g. each time the pay-at-shop picker opens.
    public func resetSeenSessions() {
        seenSessions.removeAll()
        bleReceiver?.resetSeen()
    }

    public func sendCheckout(data: CheckoutData) throws {
        if config.role == "receive" {
            throw RoleNotAllowedError.sendNotAllowed
        }
        if config.terminalId == nil || config.signingKey == nil {
            throw RoleNotAllowedError.missingCredentials
        }
        throw NSError(
            domain: "CheckoutBroadcast",
            code: 2,
            userInfo: [NSLocalizedDescriptionKey: "Use Windows/Linux POS SDK for checkout send."]
        )
    }

    /// Verify a packet pasted or scanned by other means (QR, manual JSON).
    public func verifyPacketJson(_ json: String) async throws -> VerifiedPayment {
        guard let packet = BroadcastWire.parse(json) else {
            throw NSError(domain: "CheckoutBroadcast", code: 4, userInfo: [
                NSLocalizedDescriptionKey: "Unrecognized checkout broadcast packet",
            ])
        }
        return try await verifyWithBank(packet)
    }

    private func handlePacketData(_ data: Data) {
        guard let packet = BroadcastWire.parse(data), seenSessions.insert(packet.sessionUuid).inserted else {
            return
        }
        Task {
            do {
                let payment = try await verifyWithBank(packet)
                await MainActor.run {
                    config.onPaymentReceived?(payment)
                }
            } catch {
                await MainActor.run {
                    config.onError?(error)
                }
            }
        }
    }

    /// Packet age is not checked here: a till session stays open until paid or cancelled, and the
    /// server decides (returns `valid:false` with `session_status` when closed).
    private func verifyWithBank(_ packet: BroadcastPacket) async throws -> VerifiedPayment {
        let base = config.bankApiUrl.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard let url = URL(string: base + "/verify-broadcast") else {
            throw NSError(domain: "CheckoutBroadcast", code: 7, userInfo: [
                NSLocalizedDescriptionKey: "Invalid bankApiUrl",
            ])
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        for (key, value) in config.verifyHeaders {
            request.setValue(value, forHTTPHeaderField: key)
        }
        request.httpBody = try packet.verifyBodyData()
        request.timeoutInterval = 45

        let (responseData, response) = try await URLSession.shared.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        let body = (try? JSONSerialization.jsonObject(with: responseData) as? [String: Any]) ?? [:]
        let data = body["data"] as? [String: Any] ?? body

        func serverMessage(_ o: [String: Any]) -> String? {
            for key in ["message", "error"] {
                if let s = (o[key] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines), !s.isEmpty {
                    return s
                }
            }
            return nil
        }

        guard (200...299).contains(status) else {
            let fallback = status == 429 ? "Bank API rate limit exceeded" : "Could not verify shop checkout"
            throw NSError(domain: "CheckoutBroadcast", code: status, userInfo: [
                NSLocalizedDescriptionKey: serverMessage(body) ?? fallback,
            ])
        }
        // Verify failures (unknown terminal, bad signature, session paid) arrive as HTTP 200.
        if (body["valid"] as? Bool) == false || (data["valid"] as? Bool) == false {
            throw NSError(domain: "CheckoutBroadcast", code: 9, userInfo: [
                NSLocalizedDescriptionKey: serverMessage(data) ?? serverMessage(body)
                    ?? "This shop checkout could not be verified",
            ])
        }

        func field(_ keys: String...) -> String? {
            for key in keys {
                if let s = (data[key] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines), !s.isEmpty {
                    return s
                }
            }
            return nil
        }

        let payload = packet.verifyBody["payload"] as? [String: Any]
        let display = payload?["account_info_public_display"] as? [String: Any]
        let payloadMsk = (display?["masked_account_suffix"] as? String).flatMap { $0.isEmpty ? nil : $0 }

        return VerifiedPayment(
            merchantName: field("merchant_name", "merchantName") ?? "Shop",
            amountNgn: packet.amountNgn,
            maskedAccountSuffix: field("masked_account_suffix") ?? payloadMsk,
            sessionUuid: field("session_uuid", "session_uuid_v4") ?? packet.sessionUuid,
            terminalId: field("terminal_id") ?? packet.terminalId,
            recipientAccount: field("recipient_account", "account_number"),
            recipientBankCode: field("recipient_bank_code", "bank_code"),
            isPresence: packet.isPresence
        )
    }
}
