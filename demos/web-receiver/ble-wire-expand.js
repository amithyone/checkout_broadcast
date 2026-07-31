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
]);

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

/**
 * @param {unknown} gattJson Parsed UTF-8 JSON from GATT characteristic cbbc0002
 * @returns {{ payload: Record<string, unknown>, signature_alg: string, signature: string }}
 */
export function normalizeBleReadForVerify(gattJson) {
  if (!isPlainObject(gattJson)) {
    throw new Error("Invalid BLE packet");
  }

  // Full signed envelope (512 B class payloads)
  if (isPlainObject(gattJson.payload) && typeof gattJson.signature === "string" && gattJson.signature !== "") {
    return {
      payload: gattJson.payload,
      signature_alg: String(gattJson.signature_alg ?? gattJson.signatureAlg ?? "ed25519"),
      signature: gattJson.signature,
    };
  }

  // Compact wire keys (some POS transports shorten field names)
  if (isPlainObject(gattJson.p) && typeof gattJson.sig === "string" && gattJson.sig !== "") {
    return {
      payload: gattJson.p,
      signature_alg: String(gattJson.alg ?? gattJson.signature_alg ?? "ed25519"),
      signature: gattJson.sig,
    };
  }

  // Payload fields flattened at root — preserve signature bytes; do not rebuild payload
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
