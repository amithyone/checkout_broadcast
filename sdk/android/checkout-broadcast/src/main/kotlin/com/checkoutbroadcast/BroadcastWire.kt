package com.checkoutbroadcast

import org.json.JSONObject
import kotlin.math.roundToLong

/**
 * A packet read from a till, already expanded to the body `POST /verify-broadcast` expects.
 *
 * [amountNgn] is in naira for display and transfer. Compact wire `amt` is kobo; legacy
 * `total_amount_ngn` is naira.
 */
data class BroadcastPacket(
    val verifyBody: JSONObject,
    val sessionUuid: String,
    val terminalId: String,
    val amountNgn: Double,
    val isPresence: Boolean,
    val isCompactWire: Boolean,
)

/**
 * Compact BLE wire `{p:{v,sid,tid,ts,amt,msk,k},alg,sig}` and legacy `{payload,signature_alg,signature}`.
 *
 * The signature covers the expanded canonical payload, so keys must be added exactly as the till
 * signed them: `session_kind` only when `k` is sent, `account_info_public_display` only when `msk`
 * is non-empty. Matches sdk/typescript/src/bleWire.ts and bank_api/ble_wire.py.
 */
object BroadcastWire {
    private val PRESENCE_KINDS = setOf("presence", "idle", "beacon")
    private val CHECKOUT_KINDS = setOf("pos_checkout", "checkout")
    private const val DEFAULT_PROTOCOL_VERSION = 2.1

    fun parse(bytes: ByteArray): BroadcastPacket? = parse(String(bytes, Charsets.UTF_8))

    fun parse(text: String): BroadcastPacket? {
        val raw = text.replace("\u0000", "").trim()
        if (!raw.startsWith("{")) return null
        val obj = try {
            JSONObject(raw)
        } catch (_: Exception) {
            return null
        }
        val p = obj.optJSONObject("p")
        return if (p != null) fromCompactWire(obj, p) else fromLegacy(obj)
    }

    /** True when bytes look like a JSON packet (used for advert-embedded payloads). */
    fun looksLikePacket(bytes: ByteArray?): Boolean {
        if (bytes == null || bytes.isEmpty()) return false
        val head = String(bytes.copyOf(minOf(8, bytes.size)), Charsets.UTF_8).trimStart()
        return head.startsWith("{")
    }

    private fun fromCompactWire(obj: JSONObject, p: JSONObject): BroadcastPacket? {
        val sid = p.optString("sid").trim()
        val tid = p.optString("tid").trim()
        val sig = obj.optString("sig").trim()
        if (sid.isEmpty() || tid.isEmpty() || sig.isEmpty()) return null

        val amtKobo = asDouble(p.opt("amt")) ?: 0.0
        val kind = p.optString("k").trim().lowercase()
        val presence = kind in PRESENCE_KINDS || !p.has("amt") || p.isNull("amt") || amtKobo == 0.0

        val payload = JSONObject()
        payload.put("protocol_version", protocolVersion(p.opt("v")))
        payload.put("session_uuid_v4", sid)
        payload.put("terminal_id", tid)
        payload.put("timestamp_ms", asDouble(p.opt("ts"))?.toLong() ?: System.currentTimeMillis())
        payload.put(
            "transaction_details",
            JSONObject().put("total_amount_ngn", if (presence) 0L else amtKobo.roundToLong()),
        )
        when (kind) {
            in PRESENCE_KINDS -> payload.put("session_kind", "presence")
            in CHECKOUT_KINDS -> payload.put("session_kind", "pos_checkout")
        }
        val msk = p.optString("msk").trim()
        if (msk.isNotEmpty()) {
            payload.put("account_info_public_display", JSONObject().put("masked_account_suffix", msk))
        }

        val alg = obj.optString("alg").trim().ifEmpty { "ed25519" }
        return BroadcastPacket(
            verifyBody = JSONObject()
                .put("payload", payload)
                .put("signature_alg", alg)
                .put("signature", sig),
            sessionUuid = sid,
            terminalId = tid,
            amountNgn = if (presence) 0.0 else amtKobo.roundToLong() / 100.0,
            isPresence = presence,
            isCompactWire = true,
        )
    }

    private fun fromLegacy(obj: JSONObject): BroadcastPacket? {
        val payload = obj.optJSONObject("payload") ?: return null
        val sig = obj.optString("signature").trim().ifEmpty { obj.optString("sig").trim() }
        if (sig.isEmpty()) return null
        val sid = payload.optString("session_uuid_v4").trim()
            .ifEmpty { payload.optString("session_uuid").trim() }
        val tid = payload.optString("terminal_id").trim()
        if (sid.isEmpty() || tid.isEmpty()) return null

        val amount = asDouble(payload.optJSONObject("transaction_details")?.opt("total_amount_ngn")) ?: 0.0
        val kind = payload.optString("session_kind").trim().lowercase()
        val presence = kind == "presence" || amount <= 0.0
        val alg = obj.optString("signature_alg").trim().ifEmpty { "HMAC-SHA256" }
        return BroadcastPacket(
            verifyBody = JSONObject()
                .put("payload", payload)
                .put("signature_alg", alg)
                .put("signature", sig),
            sessionUuid = sid,
            terminalId = tid,
            amountNgn = if (presence) 0.0 else amount,
            isPresence = presence,
            isCompactWire = false,
        )
    }

    private fun protocolVersion(raw: Any?): Any = when (raw) {
        is Number -> raw
        is String -> raw.trim().toDoubleOrNull() ?: DEFAULT_PROTOCOL_VERSION
        else -> DEFAULT_PROTOCOL_VERSION
    }

    private fun asDouble(raw: Any?): Double? = when (raw) {
        is Number -> raw.toDouble().takeIf { it.isFinite() }
        is String -> raw.trim().toDoubleOrNull()?.takeIf { it.isFinite() }
        else -> null
    }

    /** Short till label for pickers: last 2 digits, else last 4 characters. */
    fun terminalLabel(terminalId: String): String {
        val trimmed = terminalId.trim()
        if (trimmed.isEmpty()) return "??"
        val digits = Regex("(\\d+)\\s*$").find(trimmed)?.groupValues?.get(1)
        if (!digits.isNullOrEmpty()) {
            return if (digits.length >= 2) digits.takeLast(2) else digits.padStart(2, '0')
        }
        return if (trimmed.length <= 4) trimmed.uppercase() else trimmed.takeLast(4)
    }
}
