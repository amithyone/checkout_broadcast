package com.checkoutbroadcast

import kotlin.math.pow

/** Defaults from spec/ble-transport.md "Proximity filtering". */
data class ProximityConfig(
    val alpha: Double = 0.3,
    val inRangeDbm: Double = -75.0,
    val windowDb: Double = 12.0,
    val hysteresisDb: Double = 5.0,
    val hysteresisMs: Long = 3_000L,
    val staleMs: Long = 10_000L,
    val minPeekDbm: Double = -90.0,
)

/** Snapshot of one till's smoothed signal. [inRange] is false for tills only listed because a push named them. */
data class TillSignal(
    val deviceId: String,
    val terminalId: String?,
    val smoothedRssi: Double,
    val lastHeardMs: Long,
    val inRange: Boolean,
)

data class TillProximityView(val visible: List<TillSignal>, val hidden: List<TillSignal>)

/**
 * Splits tills into in-range ([TillProximityView.visible]) and farther ([TillProximityView.hidden])
 * from smoothed RSSI. It never picks a till: the customer always taps one and confirms with PIN.
 *
 * Thread-safe. Feed every advert with [updateSignal]; call [evaluate] to refresh the lists.
 */
class TillProximity(val config: ProximityConfig = ProximityConfig()) {
    private class Entry(
        val deviceId: String,
        var terminalId: String?,
        var smoothed: Double,
        var lastHeardMs: Long,
        var shown: Boolean = false,
        var belowSinceMs: Long? = null,
    )

    private val tills = LinkedHashMap<String, Entry>()

    /** Records one advert and returns the smoothed RSSI, or null when [rssi] is unknown (>= 0, e.g. 127). */
    @Synchronized
    fun updateSignal(deviceId: String, rssi: Int, nowMs: Long, terminalId: String? = null): Double? {
        val till = tills[deviceId]
        if (terminalId != null && till != null) till.terminalId = terminalId
        if (rssi >= 0) return till?.smoothed
        if (till == null) {
            tills[deviceId] = Entry(deviceId, terminalId, rssi.toDouble(), nowMs)
            return rssi.toDouble()
        }
        till.smoothed = config.alpha * rssi + (1.0 - config.alpha) * till.smoothed
        till.lastHeardMs = nowMs
        return till.smoothed
    }

    @Synchronized
    fun setTerminal(deviceId: String, terminalId: String) {
        tills[deviceId]?.terminalId = terminalId
    }

    /** False when the till is clearly too far to be worth a GATT connection. */
    @Synchronized
    fun shouldPeek(deviceId: String): Boolean {
        val till = tills[deviceId] ?: return true
        return till.smoothed >= config.minPeekDbm
    }

    @Synchronized
    fun isEmpty(): Boolean = tills.isEmpty()

    @Synchronized
    fun clear() = tills.clear()

    /** [preferred] is a terminal ID (or device address) named in a push: always visible and first. */
    @Synchronized
    fun evaluate(nowMs: Long, preferred: String? = null): TillProximityView {
        tills.values.removeAll { nowMs - it.lastHeardMs > config.staleMs }
        if (tills.isEmpty()) return TillProximityView(emptyList(), emptyList())

        val strongest = tills.values.maxOf { it.smoothed }
        for (till in tills.values) {
            val s = till.smoothed
            if (s >= config.inRangeDbm && s >= strongest - config.windowDb) {
                till.shown = true
                till.belowSinceMs = null
            } else if (till.shown) {
                val wellBelow = s < config.inRangeDbm - config.hysteresisDb ||
                    s < strongest - config.windowDb - config.hysteresisDb
                val since = till.belowSinceMs
                when {
                    !wellBelow -> till.belowSinceMs = null
                    since == null -> till.belowSinceMs = nowMs
                    nowMs - since >= config.hysteresisMs -> {
                        till.shown = false
                        till.belowSinceMs = null
                    }
                }
            }
        }

        val pref = preferred?.trim()?.uppercase().orEmpty()
        fun isPreferred(t: Entry) =
            pref.isNotEmpty() && (pref == t.terminalId?.uppercase() || pref == t.deviceId.uppercase())

        val order = compareBy<Entry>({ if (isPreferred(it)) 0 else 1 }, { -it.smoothed }, { it.terminalId ?: it.deviceId })
        val (visible, hidden) = tills.values.sortedWith(order).partition { it.shown || isPreferred(it) }
        fun snap(t: Entry) = TillSignal(t.deviceId, t.terminalId, t.smoothed, t.lastHeardMs, t.shown)
        return TillProximityView(visible.map(::snap), hidden.map(::snap))
    }

    companion object {
        /** Log-distance path loss. For logs only — too noisy on phones to decide anything. */
        fun estimateDistanceMeters(rssi: Double, txPowerDbm: Double = -59.0, pathLossN: Double = 2.5): Double =
            10.0.pow((txPowerDbm - rssi) / (10.0 * pathLossN))
    }
}
