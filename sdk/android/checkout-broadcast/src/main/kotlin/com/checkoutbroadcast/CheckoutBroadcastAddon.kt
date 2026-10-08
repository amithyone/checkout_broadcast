package com.checkoutbroadcast

import android.bluetooth.BluetoothManager
import android.content.Context
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.ConcurrentHashMap

typealias BroadcastRole = String

data class CheckoutBroadcastConfig(
    val role: BroadcastRole,
    val bankApiUrl: String,
    val terminalId: String? = null,
    val signingKey: String? = null,
    val merchantName: String = "ABC Enterprises",
    val bankName: String = "kuda",
    val maskedAccountSuffix: String = "***9876",
    val transport: String = "simulated",
    /** Required for BLE receive when bleReceiver is not injected (Android). */
    val androidContext: Context? = null,
    /** Extra headers on `POST /verify-broadcast`, e.g. the signed-in customer's session token. */
    val verifyHeaders: Map<String, String> = emptyMap(),
    val onPaymentReceived: ((VerifiedPayment) -> Unit)? = null,
    /**
     * About once a second while BLE receive runs (main thread): tills split into in-range and farther.
     * Join with [VerifiedPayment.terminalId] via [TillSignal.terminalId]. List the visible ones; never
     * auto-select. Uses [CheckoutBroadcastAddon.preferredTerminalId].
     */
    val onTillsUpdated: ((TillProximityView) -> Unit)? = null,
    val onSendComplete: ((String) -> Unit)? = null,
    val onError: ((Exception) -> Unit)? = null,
)

data class CheckoutData(val amountNgn: Int, val itemCount: Int = 1)

/**
 * A verified till payment, ready to pre-fill a bank transfer.
 *
 * [amountNgn] comes from the signed packet (compact wire kobo ÷ 100). When [isPresence] is true the
 * till is idle with no amount: ask the customer to enter one. Use [sessionUuid] as the transfer
 * idempotency key.
 */
data class VerifiedPayment(
    val merchantName: String,
    val amountNgn: Double,
    val maskedAccountSuffix: String?,
    val sessionUuid: String,
    val terminalId: String,
    val recipientAccount: String? = null,
    val recipientBankCode: String? = null,
    val isPresence: Boolean = false,
)

class RoleNotAllowedError(message: String) : Exception(message)

class CheckoutBroadcastAddon(
    private val config: CheckoutBroadcastConfig,
    private val bleReceiver: com.checkoutbroadcast.ble.BleCheckoutReceiver? = null,
) {
    private var started = false
    private val seenSessions = ConcurrentHashMap.newKeySet<String>()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    /** Terminal named in a push notification: always listed first by [tills], never auto-selected. */
    @Volatile
    var preferredTerminalId: String? = null

    /** Current in-range / farther split. Empty until BLE receive has heard a till. */
    fun tills(nowMs: Long = System.currentTimeMillis()): TillProximityView {
        val receiver = bleReceiver ?: internalBleReceiver ?: return TillProximityView(emptyList(), emptyList())
        return receiver.proximity.evaluate(nowMs, preferredTerminalId)
    }

    fun start() {
        if (started) return
        if (config.role == "receive" || config.role == "both") {
            if (config.transport == "ble") {
                val receiver = bleReceiver ?: createBleReceiver()
                    ?: throw IllegalStateException(
                        "BLE receive requires androidContext in CheckoutBroadcastConfig or an injected BleCheckoutReceiver"
                    )
                receiver.start()
            }
        }
        if (config.role == "send" || config.role == "both") {
            if (config.transport == "ble") {
                throw UnsupportedOperationException(
                    "Android BLE send (GATT peripheral) is phase 2. Use Windows/Linux POS for send."
                )
            }
        }
        started = true
    }

    fun stop() {
        bleReceiver?.stop()
        internalBleReceiver?.stop()
        started = false
    }

    private var internalBleReceiver: com.checkoutbroadcast.ble.BleCheckoutReceiver? = null

    private fun createBleReceiver(): com.checkoutbroadcast.ble.BleCheckoutReceiver? {
        if (internalBleReceiver != null) {
            return internalBleReceiver
        }
        val ctx = config.androidContext ?: return null
        val manager = ctx.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
        val adapter = manager?.adapter ?: return null
        internalBleReceiver = com.checkoutbroadcast.ble.BleCheckoutReceiver(
            context = ctx,
            adapter = adapter,
            onPacketBytes = { onBlePacketBytes(it) },
            onError = config.onError,
            onTillsChanged = config.onTillsUpdated?.let { cb -> { cb(tills()) } },
        )
        return internalBleReceiver
    }

    fun onBlePacketBytes(bytes: ByteArray) {
        val packet = BroadcastWire.parse(bytes) ?: return
        if (!seenSessions.add(packet.sessionUuid)) return
        scope.launch {
            try {
                val payment = verifyWithBank(packet)
                config.onPaymentReceived?.invoke(payment)
            } catch (e: Exception) {
                config.onError?.invoke(e)
            }
        }
    }

    /** Verify a packet pasted or scanned by other means (QR, manual JSON). Blocking — call off the main thread. */
    fun verifyPacketJson(json: String): VerifiedPayment {
        val packet = BroadcastWire.parse(json)
            ?: throw IllegalArgumentException("Unrecognized checkout broadcast packet")
        return verifyWithBank(packet)
    }

    /** Forget sessions and tills already seen, e.g. each time the pay-at-shop picker opens. */
    fun resetSeenSessions() {
        seenSessions.clear()
        bleReceiver?.resetSeen()
        internalBleReceiver?.resetSeen()
    }

    fun sendCheckout(data: CheckoutData) {
        if (config.role == "receive") {
            throw RoleNotAllowedError("sendCheckout is not allowed when role is 'receive'")
        }
        if (config.terminalId == null || config.signingKey == null) {
            throw RoleNotAllowedError("terminalId and signingKey are required for send/both roles")
        }
        throw UnsupportedOperationException(
            "Use Windows/Linux POS SDK with transport='ble' for checkout send."
        )
    }

    /**
     * Packet age is not checked here: a till session stays open until paid or cancelled, and the
     * server decides (returns `valid:false` with `session_status` when closed).
     */
    private fun verifyWithBank(packet: BroadcastPacket): VerifiedPayment {
        val url = URL("${config.bankApiUrl.trimEnd('/')}/verify-broadcast")
        val conn = url.openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.setRequestProperty("Content-Type", "application/json")
        conn.setRequestProperty("Accept", "application/json")
        config.verifyHeaders.forEach { (k, v) -> conn.setRequestProperty(k, v) }
        conn.doOutput = true
        conn.connectTimeout = 15_000
        conn.readTimeout = 45_000
        OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { it.write(packet.verifyBody.toString()) }

        val code = conn.responseCode
        val bodyStr = try {
            (if (code in 200..299) conn.inputStream else conn.errorStream)
                ?.bufferedReader()?.readText().orEmpty()
        } finally {
            conn.disconnect()
        }
        val body = try {
            JSONObject(bodyStr)
        } catch (_: Exception) {
            JSONObject()
        }
        val data = body.optJSONObject("data") ?: body

        fun serverMessage(o: JSONObject): String? =
            listOf("message", "error").map { o.optString(it).trim() }.firstOrNull { it.isNotEmpty() }

        if (code !in 200..299) {
            throw Exception(
                serverMessage(body) ?: if (code == 429) "Bank API rate limit exceeded" else "Could not verify shop checkout"
            )
        }
        // Verify failures (unknown terminal, bad signature, session paid) arrive as HTTP 200.
        if (body.opt("valid") == false || data.opt("valid") == false) {
            throw Exception(serverMessage(data) ?: serverMessage(body) ?: "This shop checkout could not be verified")
        }

        fun field(vararg keys: String): String? =
            keys.map { data.optString(it).trim() }.firstOrNull { it.isNotEmpty() }

        val payloadMsk = packet.verifyBody.optJSONObject("payload")
            ?.optJSONObject("account_info_public_display")
            ?.optString("masked_account_suffix")?.trim()?.ifEmpty { null }

        return VerifiedPayment(
            merchantName = field("merchant_name", "merchantName") ?: "Shop",
            amountNgn = packet.amountNgn,
            maskedAccountSuffix = field("masked_account_suffix") ?: payloadMsk,
            sessionUuid = field("session_uuid", "session_uuid_v4") ?: packet.sessionUuid,
            terminalId = field("terminal_id") ?: packet.terminalId,
            recipientAccount = field("recipient_account", "account_number"),
            recipientBankCode = field("recipient_bank_code", "bank_code"),
            isPresence = packet.isPresence,
        )
    }
}
