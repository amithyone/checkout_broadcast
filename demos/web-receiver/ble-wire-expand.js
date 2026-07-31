/**
 * Expand BLE GATT JSON into POST /verify-broadcast body.
 * Accepts full signed envelope or compact wire keys (v2.1 online minimal ~238 B).
 */

const PAYLOAD_ROOT_KEYS = new Set([
  "protocol_version",
  "connectivity",
  "timestamp_ms",
  "session_uuid_v4",
  "terminal_id",
  "transaction_details",
  "account_info_public_display",
  "offline_settlement",
  "broadcast_kind",
  "wallet_receive",
  "session_kind",
]);

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isCompactWirePayload(payload) {
  if (payload.session_uuid_v4 || payload.terminal_id) {
    return false;
  }
  return "v" in payload || "sid" in payload || "tid" in payload;
}

function expandCompactWirePayload(wire) {
  const amountKobo =
    wire.amt !== undefined && wire.amt !== null && wire.amt !== "" ? Number(wire.amt) : 0;
  /** @type {Record<string, unknown>} */
  const expanded = {
    protocol_version: wire.v ?? 2.1,
    timestamp_ms: Number(wire.ts ?? 0),
    session_uuid_v4: String(wire.sid ?? ""),
    terminal_id: String(wire.tid ?? ""),
    transaction_details: { total_amount_ngn: amountKobo },
  };
  if (wire.msk) {
    expanded.account_info_public_display = { masked_account_suffix: String(wire.msk) };
  }
  if (wire.k) {
    expanded.session_kind = String(wire.k);
  }
  return expanded;
}

/**
 * @param {unknown} gattJson Parsed UTF-8 JSON from GATT characteristic cbbc0002
 * @returns {{ payload: Record<string, unknown>, signature_alg: string, signature: string }}
 */
export function normalizeBleReadForVerify(gattJson) {
  if (!isPlainObject(gattJson)) {
    throw new Error("Invalid BLE packet");
  }

  if (isPlainObject(gattJson.payload) && typeof gattJson.signature === "string" && gattJson.signature !== "") {
    let payload = gattJson.payload;
    if (isCompactWirePayload(payload)) {
      payload = expandCompactWirePayload(payload);
    }
    return {
      payload,
      signature_alg: String(gattJson.signature_alg ?? gattJson.signatureAlg ?? "ed25519"),
      signature: gattJson.signature,
    };
  }

  if (isPlainObject(gattJson.p) && typeof gattJson.sig === "string" && gattJson.sig !== "") {
    let payload = gattJson.p;
    if (isCompactWirePayload(payload)) {
      payload = expandCompactWirePayload(payload);
    }
    return {
      payload,
      signature_alg: String(gattJson.alg ?? gattJson.signature_alg ?? "ed25519"),
      signature: gattJson.sig,
    };
  }

  if (
    typeof gattJson.signature === "string" &&
    gattJson.signature !== "" &&
    typeof gattJson.session_uuid_v4 === "string" &&
    typeof gattJson.terminal_id === "string"
  ) {
    /** @type {Record<string, unknown>} */
    const payload = {};
    for (const [key, value] of Object.entries(gattJson)) {
      if (key === "signature" || key === "signature_alg" || key === "signatureAlg") {
        continue;
      }
      if (PAYLOAD_ROOT_KEYS.has(key)) {
        payload[key] = value;
      }
    }
    return {
      payload,
      signature_alg: String(gattJson.signature_alg ?? gattJson.signatureAlg ?? "ed25519"),
      signature: gattJson.signature,
    };
  }

  throw new Error("Unrecognized BLE packet shape");
}
