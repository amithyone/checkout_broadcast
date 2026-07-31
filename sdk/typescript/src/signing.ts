import { createHash, createHmac, sign as cryptoSign, verify as cryptoVerify, KeyObject } from "crypto";
import type { Payload, SignatureAlg } from "./types.js";

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

export function normalizeSignatureAlg(alg: string): SignatureAlg {
  const upper = alg.trim().toUpperCase().replace(/_/g, "-");
  if (upper === "ED25519") return "ed25519";
  return "HMAC-SHA256";
}

function decodeKeyMaterial(value: string, expectedLength: number): Buffer | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const decoded = Buffer.from(trimmed, "base64");
  if (decoded.length === expectedLength) return decoded;
  if (/^[0-9a-fA-F]+$/.test(trimmed) && trimmed.length === expectedLength * 2) {
    return Buffer.from(trimmed, "hex");
  }
  return null;
}

function ed25519PrivateKey(signingKeyB64: string): KeyObject {
  const raw64 = decodeKeyMaterial(signingKeyB64, 64);
  const seed = raw64 ? raw64.subarray(0, 32) : decodeKeyMaterial(signingKeyB64, 32);
  if (!seed) {
    throw new Error("Invalid Ed25519 signing key: expected base64 32- or 64-byte key material");
  }
  return KeyObject.from({ key: Buffer.concat([Buffer.from("302e020100300506032b657004220420", "hex"), seed]), format: "der", type: "pkcs8" });
}

export function signPayloadEd25519(payload: Payload, signingKeyB64: string): string {
  const key = ed25519PrivateKey(signingKeyB64);
  const message = canonicalJson(payload as unknown as Record<string, unknown>);
  return cryptoSign(null, message, key).toString("base64");
}

export function verifyEd25519(payload: Payload, publicKeyB64: string, signature: string): boolean {
  const publicKeyBytes = decodeKeyMaterial(publicKeyB64, 32);
  const signatureBytes = decodeKeyMaterial(signature, 64);
  if (!publicKeyBytes || !signatureBytes) return false;
  const publicKey = KeyObject.from({
    key: Buffer.concat([Buffer.from("302a300506032b6570032100", "hex"), publicKeyBytes]),
    format: "der",
    type: "spki",
  });
  const message = canonicalJson(payload as unknown as Record<string, unknown>);
  return cryptoVerify(null, message, publicKey, signatureBytes);
}

export function signPacket(payload: Payload, signingKey: string, signatureAlg: SignatureAlg = "HMAC-SHA256"): SignedPacketFields {
  const alg = normalizeSignatureAlg(signatureAlg);
  if (alg === "ed25519") {
    return { signature_alg: "ed25519", signature: signPayloadEd25519(payload, signingKey) };
  }
  return { signature_alg: "HMAC-SHA256", signature: signPayload(payload, signingKey) };
}

interface SignedPacketFields {
  signature_alg: SignatureAlg;
  signature: string;
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
