package com.checkoutbroadcast

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ShopNearbyRateLimiterTest {
    private val minute = 60_000L

    @Test
    fun sameTillAtMostOncePerThreeMinutes() {
        val limiter = ShopNearbyRateLimiter()
        assertTrue(limiter.tryAcquire("CP-A", 0))
        assertFalse(limiter.tryAcquire("CP-A", 1 * minute))
        assertFalse(limiter.tryAcquire("CP-A", 3 * minute - 1))
        assertTrue(limiter.tryAcquire("CP-A", 3 * minute))
    }

    @Test
    fun differentTillsAreIndependent() {
        val limiter = ShopNearbyRateLimiter()
        assertTrue(limiter.tryAcquire("CP-A", 0))
        assertTrue(limiter.tryAcquire("CP-B", 0))
    }

    @Test
    fun capsAtTenPerHourThenRecovers() {
        val limiter = ShopNearbyRateLimiter()
        for (i in 0 until 10) assertTrue(limiter.tryAcquire("CP-$i", i * 1_000L))
        assertFalse(limiter.tryAcquire("CP-10", 10_000))
        assertFalse(limiter.tryAcquire("CP-10", 60 * minute - 1))
        assertTrue(limiter.tryAcquire("CP-10", 60 * minute))
        assertFalse(limiter.tryAcquire("CP-11", 60 * minute))
        assertTrue(limiter.tryAcquire("CP-11", 60 * minute + 1_000))
    }

    @Test
    fun rejectedHitsDoNotConsumeBudget() {
        val limiter = ShopNearbyRateLimiter(maxPerWindow = 2)
        assertTrue(limiter.tryAcquire("CP-A", 0))
        repeat(5) { assertFalse(limiter.tryAcquire("CP-A", 1_000L + it)) }
        assertTrue(limiter.tryAcquire("CP-B", 2_000))
    }
}
