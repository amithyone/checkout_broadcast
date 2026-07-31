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
    val onPaymentReceived: ((VerifiedPayment) -> Unit)? = null,
    val onSendComplete: ((String) -> Unit)? = null,
    val onError: ((Exception) -> Unit)? = null,
)

data class CheckoutData(val amountNgn: Int, val itemCount: Int = 1)

data class VerifiedPayment(
    val merchantName: String,
    val amountNgn: Int,
    val maskedAccountSuffix: String,
    val sessionUuid: String,
    val terminalId: String,
    val recipientAccount: String? = null,
    val recipientBankCode: String? = null,
)

class RoleNotAllowedError(message: String) : Exception(message)

class CheckoutBroadcastAddon(
    private val config: CheckoutBroadcastConfig,
    private val bleReceiver: com.checkoutbroadcast.ble.BleCheckoutReceiver? = null,
) {
    private var started = false
    private val seenSessions = ConcurrentHashMap.newKeySet<String>()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

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
        )
        return internalBleReceiver
    }

    fun onBlePacketBytes(bytes: ByteArray) {
        scope.launch {
            try {
                val json = JSONObject(String(bytes, Charsets.UTF_8))
                val payment = verifyWithBank(json)
                config.onPaymentReceived?.invoke(payment)
            } catch (e: Exception) {
                config.onError?.invoke(e)
            }
        }
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

    private fun verifyWithBank(packetJson: JSONObject): VerifiedPayment {
        val payload = packetJson.getJSONObject("payload")
        val session = payload.getString("session_uuid_v4")
        if (!payload.has("timestamp_ms") || payload.isNull("timestamp_ms")) {
            throw Exception("Missing timestamp_ms in payload")
        }
        val timestampMs = payload.getLong("timestamp_ms")
        val now = System.currentTimeMillis()
        if (kotlin.math.abs(now - timestampMs) > 600_000) {
            throw Exception("Packet timestamp outside 10-minute window")
        }
        if (!seenSessions.add(session)) {
            throw Exception("Session UUID already consumed (replay)")
        }

        val url = URL("${config.bankApiUrl.trimEnd('/')}/verify-broadcast")
        val conn = url.openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.setRequestProperty("Content-Type", "application/json")
        conn.doOutput = true
        conn.connectTimeout = 10_000
        conn.readTimeout = 10_000
        OutputStreamWriter(conn.outputStream).use { it.write(packetJson.toString()) }

        val code = conn.responseCode
        val bodyStr = if (code in 200..299) {
            conn.inputStream.bufferedReader().readText()
        } else {
            conn.errorStream?.bufferedReader()?.readText() ?: "{}"
        }
        val body = JSONObject(bodyStr)
        if (code == 429) {
            throw Exception("Bank API rate limit exceeded")
        }
        if (!body.optBoolean("valid", false)) {
            throw Exception(body.optString("error", "Invalid broadcast packet"))
        }

        return VerifiedPayment(
            merchantName = body.getString("merchant_name"),
            amountNgn = body.getInt("amount_ngn"),
            maskedAccountSuffix = body.getString("masked_account_suffix"),
            sessionUuid = body.getString("session_uuid"),
            terminalId = body.getString("terminal_id"),
            recipientAccount = body.optString("recipient_account").ifBlank { null },
            recipientBankCode = body.optString("recipient_bank_code").ifBlank { null },
        )
    }
}
