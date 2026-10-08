package com.checkoutbroadcast.ble

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import com.checkoutbroadcast.ShopNearbyRateLimiter
import kotlin.math.roundToInt

/** A till worth telling the customer about. [terminalHint] is the advert name when it starts with `CP-`. */
data class ShopNearbyHit(val deviceAddress: String, val terminalHint: String?, val rssi: Int)

data class ShopNearbyConfig(
    val reportMinDbm: Double = -80.0,
    val alpha: Double = 0.3,
    val reportDelayMs: Long = 5_000L,
    val limiter: ShopNearbyRateLimiter = ShopNearbyRateLimiter(),
)

/**
 * Low-power background listener for "a shop near you accepts this" alerts (spec/proximity-nudge.md).
 * No networking and no GATT: [onHit] gets a rate-limited till sighting; the bank app decides what to
 * do (e.g. ask its server to push, or show a local notification). Taps must open a till list —
 * never select or pay automatically.
 *
 * Uses SCAN_MODE_LOW_POWER, a hardware filter on the Checkout Broadcast service UUID and batched
 * results, so the OS can keep scanning with the screen off. Tills that only advertise a name are
 * found by the foreground [BleCheckoutReceiver] instead. To run with the app in the background,
 * start it from a foreground service of type `connectedDevice`.
 */
@SuppressLint("MissingPermission")
class ShopNearbyScanner(
    private val adapter: BluetoothAdapter,
    private val onHit: (ShopNearbyHit) -> Unit,
    private val config: ShopNearbyConfig = ShopNearbyConfig(),
    private val onError: ((Exception) -> Unit)? = null,
) {
    private val mainHandler = Handler(Looper.getMainLooper())
    private val smoothed = HashMap<String, Double>()

    @Volatile
    private var scanning = false

    private val callback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            mainHandler.post { handle(listOf(result)) }
        }

        override fun onBatchScanResults(results: MutableList<ScanResult>) {
            val copy = results.toList()
            mainHandler.post { handle(copy) }
        }

        override fun onScanFailed(errorCode: Int) {
            scanning = false
            onError?.invoke(Exception("BLE scan failed: $errorCode"))
        }
    }

    val isScanning: Boolean get() = scanning

    fun start() {
        if (scanning || !adapter.isEnabled) return
        val scanner = adapter.bluetoothLeScanner ?: run {
            onError?.invoke(Exception("Bluetooth LE scanner unavailable"))
            return
        }
        val filters = listOf(ScanFilter.Builder().setServiceUuid(ParcelUuid(BleConstants.SERVICE_UUID)).build())
        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_POWER)
            .apply { if (adapter.isOffloadedScanBatchingSupported) setReportDelay(config.reportDelayMs) }
            .build()
        scanner.startScan(filters, settings, callback)
        scanning = true
    }

    fun stop() {
        if (!scanning) return
        scanning = false
        try {
            adapter.bluetoothLeScanner?.stopScan(callback)
        } catch (_: Exception) {
        }
    }

    private fun handle(results: List<ScanResult>) {
        if (!scanning) return
        val now = System.currentTimeMillis()
        if (smoothed.size > 64) smoothed.clear()
        for (r in results) {
            val address = r.device?.address ?: continue
            if (r.rssi >= 0) continue
            val s = smoothed[address]?.let { config.alpha * r.rssi + (1 - config.alpha) * it } ?: r.rssi.toDouble()
            smoothed[address] = s
            if (s < config.reportMinDbm) continue
            val name = r.scanRecord?.deviceName?.trim().orEmpty()
            val hint = name.takeIf { it.uppercase().startsWith("CP-") }
            if (!config.limiter.tryAcquire(hint ?: address, now)) continue
            onHit(ShopNearbyHit(address, hint, s.roundToInt()))
        }
    }
}
