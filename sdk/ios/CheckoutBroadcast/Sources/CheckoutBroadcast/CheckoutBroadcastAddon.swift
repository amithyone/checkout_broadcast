import Foundation

public struct CheckoutBroadcastConfig {
    public let role: String
    public let bankApiUrl: String
    public let terminalId: String?
    public let signingKey: String?
    public let transport: String
    public var onPaymentReceived: ((VerifiedPayment) -> Void)?
    public var onError: ((Error) -> Void)?

    public init(
        role: String,
        bankApiUrl: String,
        terminalId: String? = nil,
        signingKey: String? = nil,
        transport: String = "simulated",
        onPaymentReceived: ((VerifiedPayment) -> Void)? = nil,
        onError: ((Error) -> Void)? = nil
    ) {
        self.role = role
        self.bankApiUrl = bankApiUrl
        self.terminalId = terminalId
        self.signingKey = signingKey
        self.transport = transport
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

public struct VerifiedPayment {
    public let merchantName: String
    public let amountNgn: Int
    public let maskedAccountSuffix: String
    public let sessionUuid: String
    public let terminalId: String
    public let recipientAccount: String?
    public let recipientBankCode: String?

    public init(
        merchantName: String,
        amountNgn: Int,
        maskedAccountSuffix: String,
        sessionUuid: String,
        terminalId: String,
        recipientAccount: String? = nil,
        recipientBankCode: String? = nil
    ) {
        self.merchantName = merchantName
        self.amountNgn = amountNgn
        self.maskedAccountSuffix = maskedAccountSuffix
        self.sessionUuid = sessionUuid
        self.terminalId = terminalId
        self.recipientAccount = recipientAccount
        self.recipientBankCode = recipientBankCode
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

    private func handlePacketData(_ data: Data) {
        Task {
            do {
                let payment = try await verifyWithBank(packetData: data)
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

    private func verifyWithBank(packetData: Data) async throws -> VerifiedPayment {
        guard let json = try JSONSerialization.jsonObject(with: packetData) as? [String: Any],
              let payload = json["payload"] as? [String: Any],
              let session = payload["session_uuid_v4"] as? String,
              let timestampMs = payload["timestamp_ms"] as? Int64 ?? (payload["timestamp_ms"] as? Int).map(Int64.init)
        else {
            throw NSError(domain: "CheckoutBroadcast", code: 4, userInfo: [
                NSLocalizedDescriptionKey: "Invalid packet JSON",
            ])
        }

        let now = Int64(Date().timeIntervalSince1970 * 1000)
        if abs(now - timestampMs) > BleConstants.maxAgeMs {
            throw NSError(domain: "CheckoutBroadcast", code: 5, userInfo: [
                NSLocalizedDescriptionKey: "Timestamp outside 10-minute window",
            ])
        }
        if seenSessions.contains(session) {
            throw NSError(domain: "CheckoutBroadcast", code: 6, userInfo: [
                NSLocalizedDescriptionKey: "Session replay detected",
            ])
        }
        seenSessions.insert(session)

        let url = URL(string: config.bankApiUrl.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/verify-broadcast")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = packetData
        request.timeoutInterval = 10

        let (responseData, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw NSError(domain: "CheckoutBroadcast", code: 7, userInfo: [
                NSLocalizedDescriptionKey: "Invalid HTTP response",
            ])
        }
        guard let body = try JSONSerialization.jsonObject(with: responseData) as? [String: Any] else {
            throw NSError(domain: "CheckoutBroadcast", code: 8, userInfo: [
                NSLocalizedDescriptionKey: "Invalid verify response",
            ])
        }
        if http.statusCode == 429 {
            throw NSError(domain: "CheckoutBroadcast", code: 429, userInfo: [
                NSLocalizedDescriptionKey: "Rate limit exceeded",
            ])
        }
        guard (body["valid"] as? Bool) == true else {
            throw NSError(domain: "CheckoutBroadcast", code: 9, userInfo: [
                NSLocalizedDescriptionKey: body["error"] as? String ?? "Verification failed",
            ])
        }

        return VerifiedPayment(
            merchantName: body["merchant_name"] as? String ?? "",
            amountNgn: body["amount_ngn"] as? Int ?? 0,
            maskedAccountSuffix: body["masked_account_suffix"] as? String ?? "",
            sessionUuid: body["session_uuid"] as? String ?? session,
            terminalId: body["terminal_id"] as? String ?? "",
            recipientAccount: body["recipient_account"] as? String,
            recipientBankCode: body["recipient_bank_code"] as? String
        )
    }
}
