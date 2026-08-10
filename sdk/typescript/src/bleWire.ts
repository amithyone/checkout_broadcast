/**
 * Compact BLE wire expand — matches CheckoutNow / Cheko production path.
 * Signature covers expanded canonical keys, not short wire keys.
 */

export type WireBroadcastPacket = {
  p: {
    v?: number | string;
    sid: string;
    tid: string;
    ts: number | string;
    /** Amount in kobo (₦1.00 → 100). Omit / 0 = presence. */
    amt?: number;
    msk?: string;
    k?: string;
  };
  alg?: string;
  sig: string;
};

export type VerifyEnvelope = {
  payload: Record<string, unknown>;
  signature_alg: string;
  signature: string;
  /** Present when expanded from compact wire — treat amounts as kobo. */
  wireSource?: "wire" | "legacy";
};

function asFiniteNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) {
    return Number(value);
  }
  return fallback;
}

export function isWireBroadcastPacket(raw: unknown): raw is WireBroadcastPacket {
  if (!raw || typeof raw !== "object") {
    return false;
  }
  const obj = raw as Record<string, unknown>;
  const p = obj.p;
  if (p == null || typeof p !== "object") {
    return false;
  }
  const pp = p as Record<string, unknown>;
  return (
    typeof pp.sid === "string" &&
    pp.sid.trim().length > 0 &&
    typeof pp.tid === "string" &&
    pp.tid.trim().length > 0 &&
    typeof obj.sig === "string" &&
    obj.sig.trim().length > 0 &&
    (typeof pp.ts === "number" || (typeof pp.ts === "string" && Number.isFinite(Number(pp.ts))))
  );
}

export function isLegacyBroadcastPacket(raw: unknown): boolean {
  if (!raw || typeof raw !== "object") {
    return false;
  }
  const obj = raw as Record<string, unknown>;
  return obj.payload != null && typeof obj.payload === "object";
}

export function isPresenceWirePacket(wire: WireBroadcastPacket): boolean {
  const k = String(wire.p.k ?? "").trim().toLowerCase();
  if (k === "presence" || k === "idle" || k === "beacon") {
    return true;
  }
  if (wire.p.amt === undefined || wire.p.amt === null) {
    return true;
  }
  return asFiniteNumber(wire.p.amt, -1) === 0;
}

/** Compact wire amt / signed total_amount_ngn is kobo → major NGN for display & transfer. */
export function wireKoboToNaira(kobo: number): number {
  if (!Number.isFinite(kobo) || kobo <= 0) {
    return 0;
  }
  return Math.round(kobo) / 100;
}

export function expandWireToVerifyPacket(wire: WireBroadcastPacket): VerifyEnvelope {
  const p = wire.p;
  let protocolVersion = 2.1;
  if (typeof p.v === "number" && Number.isFinite(p.v)) {
    protocolVersion = p.v;
  } else if (typeof p.v === "string" && p.v.trim() && Number.isFinite(Number(p.v))) {
    protocolVersion = Number(p.v);
  }

  const presence = isPresenceWirePacket(wire);
  const payload: Record<string, unknown> = {
    protocol_version: protocolVersion,
    timestamp_ms: asFiniteNumber(p.ts),
    session_uuid_v4: String(p.sid).trim(),
    terminal_id: String(p.tid).trim(),
    transaction_details: {
      total_amount_ngn: presence ? 0 : asFiniteNumber(p.amt),
    },
  };

  const kind = String(p.k ?? "").trim().toLowerCase();
  if (kind === "presence" || kind === "idle" || kind === "beacon") {
    payload.session_kind = "presence";
  } else if (kind === "pos_checkout" || kind === "checkout") {
    payload.session_kind = "pos_checkout";
  }

  const msk = typeof p.msk === "string" ? p.msk.trim() : "";
  if (msk) {
    payload.account_info_public_display = { masked_account_suffix: msk };
  }

  return {
    payload,
    signature_alg: (typeof wire.alg === "string" && wire.alg.trim()) || "ed25519",
    signature: String(wire.sig).trim(),
    wireSource: "wire",
  };
}

/** Normalize GATT JSON (compact wire or legacy full envelope) for POST /verify-broadcast. */
export function normalizeBleReadForVerify(raw: unknown): VerifyEnvelope | null {
  if (isWireBroadcastPacket(raw)) {
    return expandWireToVerifyPacket(raw);
  }
  if (!isLegacyBroadcastPacket(raw)) {
    return null;
  }
  const obj = raw as {
    payload: Record<string, unknown>;
    signature?: string;
    signature_alg?: string;
    sig?: string;
  };
  const signature = (obj.signature ?? obj.sig ?? "").trim();
  const payload = obj.payload;
  if (!signature || !payload?.session_uuid_v4 || !payload?.terminal_id) {
    return null;
  }
  return {
    payload,
    signature,
    signature_alg: obj.signature_alg?.trim() || "HMAC-SHA256",
    wireSource: "legacy",
  };
}

/** JSON body for POST /verify-broadcast (strip wireSource). */
export function verifyRequestBody(packet: VerifyEnvelope): {
  payload: Record<string, unknown>;
  signature_alg: string;
  signature: string;
} {
  return {
    payload: packet.payload,
    signature_alg: packet.signature_alg,
    signature: packet.signature,
  };
}
