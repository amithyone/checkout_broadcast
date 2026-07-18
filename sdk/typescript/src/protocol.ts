import { randomUUID } from "crypto";
import type { CheckoutData, Payload, SignedPacket } from "./types.js";
import { hashBankName } from "./signing.js";

export function buildPayload(params: {
  terminalId: string;
  amountNgn: number;
  itemCount: number;
  bankName: string;
  maskedAccountSuffix: string;
}): Payload {
  return {
    protocol_version: 2.0,
    timestamp_ms: Date.now(),
    session_uuid_v4: randomUUID(),
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

export function createSignedPacket(
  checkout: CheckoutData,
  terminalId: string,
  signingKey: string,
  bankName: string,
  maskedAccountSuffix: string,
  signFn: (payload: Payload, key: string) => string,
): SignedPacket {
  const payload = buildPayload({
    terminalId,
    amountNgn: checkout.amountNgn,
    itemCount: checkout.itemCount ?? 1,
    bankName,
    maskedAccountSuffix,
  });
  return {
    payload,
    signature_alg: "HMAC-SHA256",
    signature: signFn(payload, signingKey),
  };
}
