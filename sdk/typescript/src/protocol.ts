import { randomUUID } from "crypto";
import type { CheckoutData, Payload, SignatureAlg, SignedPacket } from "./types.js";
import { hashBankName, signPacket } from "./signing.js";

export function buildPayload(params: {
  terminalId: string;
  amountNgn: number;
  itemCount: number;
  bankName: string;
  maskedAccountSuffix: string;
  sessionUuidV4?: string;
}): Payload {
  return {
    protocol_version: 2.0,
    timestamp_ms: Date.now(),
    session_uuid_v4: params.sessionUuidV4 ?? randomUUID(),
    terminal_id: params.terminalId,
    transaction_details: {
      currency_code: "NGN",
      total_amount_ngn: params.amountNgn,
      item_count: params.itemCount,
    },
    account_info_public_display: {
      bank_name_hash: hashBankName(params.bankName),
      masked_account_suffix: params.maskedAccountSuffix,
    },
  };
}

export function isTimestampValid(timestampMs: number, nowMs = Date.now()): boolean {
  return Math.abs(nowMs - timestampMs) <= 600_000;
}

export function parseTimestampMs(payload: Record<string, unknown>): number | null {
  if (!Object.prototype.hasOwnProperty.call(payload, "timestamp_ms")) {
    return null;
  }
  const raw = payload.timestamp_ms;
  if (raw === null || raw === undefined || raw === "") {
    return null;
  }
  const timestampMs = typeof raw === "number" ? raw : Number.parseInt(String(raw), 10);
  if (!Number.isFinite(timestampMs) || timestampMs <= 0) {
    return null;
  }
  return timestampMs;
}

export function createSignedPacket(
  checkout: CheckoutData,
  terminalId: string,
  signingKey: string,
  bankName: string,
  maskedAccountSuffix: string,
  signatureAlg: SignatureAlg = "HMAC-SHA256",
  sessionUuidV4?: string,
): SignedPacket {
  const payload = buildPayload({
    terminalId,
    amountNgn: checkout.amountNgn,
    itemCount: checkout.itemCount ?? 1,
    bankName,
    maskedAccountSuffix,
    sessionUuidV4,
  });
  const signed = signPacket(payload, signingKey, signatureAlg);
  return {
    payload,
    signature_alg: signed.signature_alg,
    signature: signed.signature,
  };
}
