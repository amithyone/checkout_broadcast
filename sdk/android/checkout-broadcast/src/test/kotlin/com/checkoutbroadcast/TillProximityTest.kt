package com.checkoutbroadcast

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.File

class TillProximityTest {
    private val fixture = JSONObject(File("../../../tests/fixtures/proximity_vectors.json").readText())

    @Test
    fun defaultsMatchFixtureConfig() {
        val c = fixture.getJSONObject("config")
        assertEquals(
            ProximityConfig(
                alpha = c.getDouble("alpha"),
                inRangeDbm = c.getDouble("in_range_dbm"),
                windowDb = c.getDouble("window_db"),
                hysteresisDb = c.getDouble("hysteresis_db"),
                hysteresisMs = c.getLong("hysteresis_ms"),
                staleMs = c.getLong("stale_ms"),
                minPeekDbm = c.getDouble("min_peek_dbm"),
            ),
            ProximityConfig(),
        )
    }

    @Test
    fun replaysSharedVectors() {
        val vectors = fixture.getJSONArray("vectors")
        for (i in 0 until vectors.length()) {
            val v = vectors.getJSONObject(i)
            val name = v.getString("name")
            val filter = TillProximity()
            val steps = v.getJSONArray("steps")
            for (j in 0 until steps.length()) {
                val step = steps.getJSONObject(j)
                val t = step.getLong("t")
                step.optJSONObject("signal")?.let { s ->
                    filter.updateSignal(
                        s.getString("device"),
                        s.getInt("rssi"),
                        t,
                        s.optString("terminal_id").ifEmpty { null },
                    )
                }
                val check = step.optJSONObject("check") ?: continue
                val view = filter.evaluate(t, check.optString("preferred").ifEmpty { null })
                fun ids(key: String) = check.getJSONArray(key).let { a -> (0 until a.length()).map(a::getString) }
                assertEquals("$name t=$t visible", ids("visible"), view.visible.map { it.deviceId })
                assertEquals("$name t=$t hidden", ids("hidden"), view.hidden.map { it.deviceId })
                val byId = (view.visible + view.hidden).associateBy { it.deviceId }
                check.optJSONObject("smoothed")?.let { sm ->
                    for (device in sm.keys()) {
                        assertEquals("$name t=$t smoothed $device", sm.getDouble(device), byId.getValue(device).smoothedRssi, 0.01)
                    }
                }
                check.optJSONObject("peek")?.let { pk ->
                    for (device in pk.keys()) {
                        assertEquals("$name t=$t peek $device", pk.getBoolean(device), filter.shouldPeek(device))
                    }
                }
            }
        }
    }

    @Test
    fun distanceIsForLogsOnly() {
        assertEquals(1.0, TillProximity.estimateDistanceMeters(-59.0), 0.0001)
    }
}
