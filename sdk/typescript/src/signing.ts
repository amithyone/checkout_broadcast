import { createHash, createHmac } from "crypto";
import type { Payload } from "./types.js";

export function hashBankName(bankName: string): string {
  const normalized = bankName.trim().toLowerCase();
  const digest = createHash("sha256").update(normalized, "utf8").digest("hex");
  return `sha256:${digest}`;
}

export function canonicalJson(data: Record<string, unknown>): Buffer {
  return Buffer.from(JSON.stringify(sortKeys(data)), "utf8");
}

function sortKeys(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(sortKeys);
  }
  if (value !== null && typeof value === "object") {
    const obj = value as Record<string, unknown>;
    return Object.keys(obj)
      .sort()
      .reduce<Record<string, unknown>>((acc, key) => {
        acc[key] = sortKeys(obj[key]);
        return acc;
      }, {});
  }
  return value;
}

export function signPayload(payload: Payload, signingKey: string): string {
  const message = canonicalJson(payload as unknown as Record<string, unknown>);
  return createHmac("sha256", signingKey).update(message).digest("base64");
}

export function verifySignature(payload: Payload, signingKey: string, signature: string): boolean {
  const expected = signPayload(payload, signingKey);
  return timingSafeEqual(expected, signature);
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let result = 0;
  for (let i = 0; i < a.length; i += 1) {
    result |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return result === 0;
}
