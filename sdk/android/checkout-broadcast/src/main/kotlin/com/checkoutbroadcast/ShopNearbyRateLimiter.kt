package com.checkoutbroadcast

/**
 * Report the same till at most once per [perTillMs], and at most [maxPerWindow] tills per
 * [windowMs] overall (spec/proximity-nudge.md). Thread-safe.
 */
class ShopNearbyRateLimiter(
    private val perTillMs: Long = 3 * 60_000L,
    private val maxPerWindow: Int = 10,
    private val windowMs: Long = 60 * 60_000L,
) {
    private val lastByTill = HashMap<String, Long>()
    private val recent = ArrayDeque<Long>()

    @Synchronized
    fun tryAcquire(tillKey: String, nowMs: Long): Boolean {
        while (recent.isNotEmpty() && nowMs - recent.first() >= windowMs) recent.removeFirst()
        val last = lastByTill[tillKey]
        if (last != null && nowMs - last < perTillMs) return false
        if (recent.size >= maxPerWindow) return false
        lastByTill[tillKey] = nowMs
        recent.addLast(nowMs)
        if (lastByTill.size > 256) lastByTill.entries.removeAll { nowMs - it.value >= perTillMs }
        return true
    }
}
