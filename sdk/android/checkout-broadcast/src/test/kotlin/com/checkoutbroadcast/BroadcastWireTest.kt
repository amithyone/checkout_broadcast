package com.checkoutbroadcast

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test
import java.io.File

class BroadcastWireTest {
    private val vectors: JSONArray =
        JSONObject(File("../../../tests/fixtures/wire_vectors.json").readText()).getJSONArray("vectors")

    /** Sorted keys; integers and decimals kept distinct so `649` never passes as `649.0`. */
    private fun canonical(value: Any?): String = when (value) {
        is JSONObject -> value.keys().asSequence().sorted()
            .joinToString(",", "{", "}") { "\"$it\":${canonical(value.get(it))}" }
        is JSONArray -> (0 until value.length()).joinToString(",", "[", "]") { canonical(value.get(it)) }
        is Double, is Float, is java.math.BigDecimal -> "d:${(value as Number).toDouble()}"
        is Number -> "i:${value.toLong()}"
        is String -> JSONObject.quote(value)
        else -> value.toString()
    }

    @Test
    fun expandsSharedVectors() {
        for (i in 0 until vectors.length()) {
            val v = vectors.getJSONObject(i)
            val name = v.getString("name")
            val packet = assertNotNullAndGet(name, BroadcastWire.parse(v.getJSONObject("packet").toString()))
            assertEquals(name, canonical(v.getJSONObject("verify_body")), canonical(packet.verifyBody))
            assertEquals(name, v.getDouble("amount_ngn"), packet.amountNgn, 0.0001)
            assertEquals(name, v.getBoolean("is_presence"), packet.isPresence)
        }
    }

    @Test
    fun stripsNullPaddingFromGattRead() {
        val raw = vectors.getJSONObject(0).getJSONObject("packet").toString() + "\u0000\u0000"
        assertNotNull(BroadcastWire.parse(raw.toByteArray(Charsets.UTF_8)))
    }

    @Test
    fun rejectsNonPackets() {
        assertNull(BroadcastWire.parse("hello"))
        assertNull(BroadcastWire.parse("{\"p\":{\"sid\":\"\",\"tid\":\"x\"},\"sig\":\"s\"}"))
        assertNull(BroadcastWire.parse("{\"payload\":{\"terminal_id\":\"x\"}}"))
    }

    @Test
    fun terminalLabels() {
        assertEquals("01", BroadcastWire.terminalLabel("TERM-001"))
        assertEquals("07", BroadcastWire.terminalLabel("till 7"))
        assertEquals("RK8Z", BroadcastWire.terminalLabel("CP-1RK8Z"))
        assertEquals("AB", BroadcastWire.terminalLabel("ab"))
    }

    private fun <T> assertNotNullAndGet(message: String, value: T?): T {
        assertNotNull(message, value)
        return value!!
    }
}
