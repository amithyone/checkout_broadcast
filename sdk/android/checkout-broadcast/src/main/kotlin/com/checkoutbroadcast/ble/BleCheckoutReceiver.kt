package com.checkoutbroadcast.ble

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import com.checkoutbroadcast.BroadcastWire
import com.checkoutbroadcast.TillProximity
import java.util.UUID

/** BLE GATT UUIDs — must match spec/ble-transport.md */
object BleConstants {
    val SERVICE_UUID: UUID = UUID.fromString("cbbc0001-0000-4000-8000-000000000001")
    val PACKET_CHAR_UUID: UUID = UUID.fromString("cbbc0002-0000-4000-8000-000000000001")
    const val CONNECT_TIMEOUT_MS = 12_000L
    const val READ_COOLDOWN_MS = 4_000L
    const val REQUEST_MTU = 512
}

/**
 * Listens for Checkout Broadcast tills and hands each signed packet to [onPacketBytes].
 *
 * - Scans without an OS service-UUID filter: many Windows POS adapters don't put the UUID in the
 *   advert, so hardware filters miss them. Results are matched in [looksLikeCheckout].
 * - Uses the packet embedded in advert service/manufacturer data when present (no connection).
 * - Otherwise connects to one till at a time and **reads** the packet characteristic. Never
 *   enables notify/indicate and never bonds — writing the CCCD often forces an Android pairing
 *   dialog. Verification always happens server-side.
 * - Feeds every advert's RSSI into [proximity] and skips the connection for tills that are clearly
 *   far away. While scanning, [onTillsChanged] fires about once a second so a picker can list only
 *   in-range tills ([TillProximity.evaluate]). Never auto-select a till from this.
 *
 * Requires BLUETOOTH_SCAN + BLUETOOTH_CONNECT (API 31+) or Bluetooth + fine location (older).
 */
@SuppressLint("MissingPermission")
class BleCheckoutReceiver(
    private val context: Context,
    private val adapter: BluetoothAdapter,
    private val onPacketBytes: (ByteArray) -> Unit,
    private val onError: ((Exception) -> Unit)? = null,
    val proximity: TillProximity = TillProximity(),
    private val onTillsChanged: (() -> Unit)? = null,
) {
    private val serviceParcel = ParcelUuid(BleConstants.SERVICE_UUID)
    private val mainHandler = Handler(Looper.getMainLooper())

    @Volatile
    private var scanning = false
    private var activeGatt: BluetoothGatt? = null
    private var timeoutRunnable: Runnable? = null
    private var tillsWereListed = false

    private val tillsTicker = object : Runnable {
        override fun run() {
            if (!scanning) return
            val hasTills = !proximity.isEmpty()
            if (hasTills || tillsWereListed) onTillsChanged?.invoke()
            tillsWereListed = hasTills
            mainHandler.postDelayed(this, TILLS_TICK_MS)
        }
    }

    // Touched only on the main thread.
    private val deviceQueue = ArrayDeque<BluetoothDevice>()
    private val queuedAddresses = mutableSetOf<String>()
    private val readDevices = mutableSetOf<String>()
    private val recentlyReadAt = mutableMapOf<String, Long>()

    private val scanCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            mainHandler.post { handleScanResult(result) }
        }

        override fun onBatchScanResults(results: MutableList<ScanResult>) {
            mainHandler.post { results.forEach(::handleScanResult) }
        }

        override fun onScanFailed(errorCode: Int) {
            onError?.invoke(Exception("BLE scan failed: $errorCode"))
        }
    }

    fun start() {
        if (scanning || !adapter.isEnabled) return
        val scanner = adapter.bluetoothLeScanner ?: run {
            onError?.invoke(Exception("Bluetooth LE scanner unavailable"))
            return
        }
        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build()
        scanner.startScan(null, settings, scanCallback)
        scanning = true
        if (onTillsChanged != null) mainHandler.postDelayed(tillsTicker, TILLS_TICK_MS)
    }

    fun stop() {
        if (scanning) {
            try {
                adapter.bluetoothLeScanner?.stopScan(scanCallback)
            } catch (_: Exception) {
            }
        }
        scanning = false
        mainHandler.removeCallbacks(tillsTicker)
        mainHandler.post {
            deviceQueue.clear()
            queuedAddresses.clear()
            readDevices.clear()
            finishActiveGatt()
            proximity.clear()
            tillsWereListed = false
        }
    }

    /** Forget devices already read so the same tills are picked up again (e.g. when a picker reopens). */
    fun resetSeen() {
        mainHandler.post {
            readDevices.clear()
            recentlyReadAt.clear()
        }
    }

    private fun looksLikeCheckout(result: ScanResult): Boolean {
        val record = result.scanRecord ?: return false
        if (record.serviceUuids?.contains(serviceParcel) == true) return true
        if (record.serviceData?.containsKey(serviceParcel) == true) return true
        val name = (record.deviceName ?: "").uppercase()
        return name.contains("CHECKOUT") ||
            name.contains("CHEKO") ||
            name.startsWith("CP-") ||
            name.startsWith("CN")
    }

    private fun packetFromAdvert(result: ScanResult): ByteArray? {
        val record = result.scanRecord ?: return null
        record.getServiceData(serviceParcel)?.let { if (BroadcastWire.looksLikePacket(it)) return it }
        val mfr = record.manufacturerSpecificData ?: return null
        for (i in 0 until mfr.size()) {
            val bytes = mfr.valueAt(i)
            if (BroadcastWire.looksLikePacket(bytes)) return bytes
        }
        return null
    }

    private fun handleScanResult(result: ScanResult) {
        if (!scanning || !looksLikeCheckout(result)) return
        val address = result.device.address ?: return
        val now = System.currentTimeMillis()
        proximity.updateSignal(address, result.rssi, now)
        if (now - (recentlyReadAt[address] ?: 0L) < BleConstants.READ_COOLDOWN_MS) return

        val advertBytes = packetFromAdvert(result)
        if (advertBytes != null) {
            recentlyReadAt[address] = now
            deliverPacket(address, advertBytes)
            return
        }

        if (!proximity.shouldPeek(address)) return
        if (address in queuedAddresses || address in readDevices) return
        queuedAddresses.add(address)
        deviceQueue.addLast(result.device)
        drainQueue()
    }

    private fun drainQueue() {
        if (activeGatt != null || !scanning) return
        val device = deviceQueue.removeFirstOrNull() ?: return
        queuedAddresses.remove(device.address)
        peekPacket(device)
    }

    /** Closes the active connection; when [only] is set, ignores callbacks from an older connection. */
    private fun finishActiveGatt(only: BluetoothGatt? = null) {
        val gatt = activeGatt ?: return
        if (only != null && only !== gatt) return
        timeoutRunnable?.let { mainHandler.removeCallbacks(it) }
        timeoutRunnable = null
        activeGatt = null
        recentlyReadAt[gatt.device.address] = System.currentTimeMillis()
        try {
            gatt.disconnect()
        } catch (_: Exception) {
        }
        try {
            gatt.close()
        } catch (_: Exception) {
        }
    }

    private fun finishAndContinue(gatt: BluetoothGatt) {
        mainHandler.post {
            finishActiveGatt(only = gatt)
            drainQueue()
        }
    }

    private fun peekPacket(device: BluetoothDevice) {
        val gatt = device.connectGatt(context, false, object : BluetoothGattCallback() {
            override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
                when (newState) {
                    BluetoothProfile.STATE_CONNECTED ->
                        if (!gatt.requestMtu(BleConstants.REQUEST_MTU)) gatt.discoverServices()
                    BluetoothProfile.STATE_DISCONNECTED -> finishAndContinue(gatt)
                }
            }

            override fun onMtuChanged(gatt: BluetoothGatt, mtu: Int, status: Int) {
                gatt.discoverServices()
            }

            override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
                val characteristic = gatt.getService(BleConstants.SERVICE_UUID)
                    ?.getCharacteristic(BleConstants.PACKET_CHAR_UUID)
                val started = status == BluetoothGatt.GATT_SUCCESS &&
                    characteristic != null &&
                    (characteristic.properties and BluetoothGattCharacteristic.PROPERTY_READ) != 0 &&
                    gatt.readCharacteristic(characteristic)
                if (!started) finishAndContinue(gatt)
            }

            override fun onCharacteristicRead(
                gatt: BluetoothGatt,
                characteristic: BluetoothGattCharacteristic,
                value: ByteArray,
                status: Int,
            ) {
                deliver(gatt, status, value)
            }

            @Deprecated("Deprecated in API 33")
            override fun onCharacteristicRead(
                gatt: BluetoothGatt,
                characteristic: BluetoothGattCharacteristic,
                status: Int,
            ) {
                @Suppress("DEPRECATION")
                deliver(gatt, status, characteristic.value)
            }
        }, BluetoothDevice.TRANSPORT_LE)
        if (gatt == null) {
            recentlyReadAt[device.address] = System.currentTimeMillis()
            mainHandler.post { drainQueue() }
            return
        }
        activeGatt = gatt
        val timeout = Runnable {
            finishActiveGatt(only = gatt)
            drainQueue()
        }
        timeoutRunnable = timeout
        mainHandler.postDelayed(timeout, BleConstants.CONNECT_TIMEOUT_MS)
    }

    private fun deliver(gatt: BluetoothGatt, status: Int, value: ByteArray?) {
        val address = gatt.device.address
        if (status == BluetoothGatt.GATT_SUCCESS && value != null && BroadcastWire.looksLikePacket(value)) {
            mainHandler.post { readDevices.add(address) }
            deliverPacket(address, value)
        }
        finishAndContinue(gatt)
    }

    private fun deliverPacket(address: String, bytes: ByteArray) {
        BroadcastWire.parse(bytes)?.terminalId?.takeIf { it.isNotBlank() }?.let {
            proximity.setTerminal(address, it)
        }
        onPacketBytes(bytes)
    }

    private companion object {
        const val TILLS_TICK_MS = 1_000L
    }
}
