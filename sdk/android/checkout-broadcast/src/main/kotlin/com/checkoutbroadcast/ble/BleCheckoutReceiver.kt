package com.checkoutbroadcast.ble

import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap

/** BLE GATT UUIDs — must match spec/ble-transport.md */
object BleConstants {
    val SERVICE_UUID: UUID = UUID.fromString("cbbc0001-0000-4000-8000-000000000001")
    val PACKET_CHAR_UUID: UUID = UUID.fromString("cbbc0002-0000-4000-8000-000000000001")
    const val CONNECT_TIMEOUT_MS = 12_000L
}

/**
 * Scans for checkout broadcast peripherals, connects, reads signed packet JSON from GATT.
 */
class BleCheckoutReceiver(
    private val context: Context,
    private val adapter: BluetoothAdapter,
    private val onPacketBytes: (ByteArray) -> Unit,
    private val onError: ((Exception) -> Unit)? = null,
) {
    private val scanner = adapter.bluetoothLeScanner
    private val mainHandler = Handler(Looper.getMainLooper())
    private var scanning = false
    private val seenDevices = ConcurrentHashMap<String, Long>()
    private val activeGatts = mutableListOf<BluetoothGatt>()
    private var connectRunnable: Runnable? = null

    private val scanCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            val address = result.device.address ?: return
            val now = System.currentTimeMillis()
            val last = seenDevices[address] ?: 0L
            if (now - last < 3_000) return
            seenDevices[address] = now
            connectAndRead(result.device)
        }

        override fun onScanFailed(errorCode: Int) {
            onError?.invoke(Exception("BLE scan failed: $errorCode"))
        }
    }

    fun start() {
        if (scanning || !adapter.isEnabled) return
        val filter = ScanFilter.Builder()
            .setServiceUuid(ParcelUuid(BleConstants.SERVICE_UUID))
            .build()
        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build()
        scanner.startScan(listOf(filter), settings, scanCallback)
        scanning = true
    }

    fun stop() {
        if (!scanning) return
        scanner.stopScan(scanCallback)
        scanning = false
        connectRunnable?.let { mainHandler.removeCallbacks(it) }
        synchronized(activeGatts) {
            activeGatts.forEach { gatt ->
                try {
                    gatt.close()
                } catch (_: Exception) {
                }
            }
            activeGatts.clear()
        }
    }

    private fun connectAndRead(device: BluetoothDevice) {
        connectRunnable?.let { mainHandler.removeCallbacks(it) }
        val timeout = Runnable {
            onError?.invoke(Exception("GATT connect timeout"))
        }
        connectRunnable = timeout
        mainHandler.postDelayed(timeout, BleConstants.CONNECT_TIMEOUT_MS)

        val gatt = device.connectGatt(context, false, object : BluetoothGattCallback() {
            override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
                if (newState == BluetoothProfile.STATE_CONNECTED) {
                    gatt.discoverServices()
                } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                    synchronized(activeGatts) { activeGatts.remove(gatt) }
                    gatt.close()
                }
            }

            override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
                if (status != BluetoothGatt.GATT_SUCCESS) {
                    onError?.invoke(Exception("GATT service discovery failed: $status"))
                    gatt.disconnect()
                    return
                }
                val service = gatt.getService(BleConstants.SERVICE_UUID) ?: run {
                    gatt.disconnect()
                    return
                }
                val characteristic = service.getCharacteristic(BleConstants.PACKET_CHAR_UUID) ?: run {
                    gatt.disconnect()
                    return
                }
                gatt.readCharacteristic(characteristic)
            }

            override fun onCharacteristicRead(
                gatt: BluetoothGatt,
                characteristic: BluetoothGattCharacteristic,
                value: ByteArray,
                status: Int,
            ) {
                connectRunnable?.let { mainHandler.removeCallbacks(it) }
                if (status == BluetoothGatt.GATT_SUCCESS && value.isNotEmpty()) {
                    onPacketBytes(value)
                }
                gatt.disconnect()
            }

            @Deprecated("Deprecated in API 33")
            override fun onCharacteristicRead(
                gatt: BluetoothGatt,
                characteristic: BluetoothGattCharacteristic,
                status: Int,
            ) {
                @Suppress("DEPRECATION")
                val value = characteristic.value
                connectRunnable?.let { mainHandler.removeCallbacks(it) }
                if (status == BluetoothGatt.GATT_SUCCESS && value != null && value.isNotEmpty()) {
                    onPacketBytes(value)
                }
                gatt.disconnect()
            }
        })
        synchronized(activeGatts) { activeGatts.add(gatt) }
    }
}
