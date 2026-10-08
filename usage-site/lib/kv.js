import { createHash, randomBytes, timingSafeEqual } from "node:crypto";

const COUNT_KEY = "cb:ok_count";
const REPORTERS_KEY = "cb:reporters";

function restBase() {
  const url = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL || "";
  const token = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN || "";
  if (!url || !token) {
    return null;
  }
  return { url: url.replace(/\/$/, ""), token };
}

async function command(parts) {
  const kv = restBase();
  if (!kv) {
    const err = new Error("KV_REST_API_URL and KV_REST_API_TOKEN (or Upstash REDIS REST) are required");
    err.status = 503;
    throw err;
  }
  const res = await fetch(`${kv.url}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${kv.token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(parts),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(body.error || "kv request failed");
    err.status = 502;
    throw err;
  }
  return body.result;
}

export function hashToken(token) {
  return createHash("sha256").update(token, "utf8").digest("hex");
}

export function newReporterToken() {
  return randomBytes(32).toString("hex");
}

export function normalizeHost(raw) {
  let host = String(raw || "").trim().toLowerCase();
  host = host.replace(/^https?:\/\//, "").replace(/\/.*$/, "").replace(/:\d+$/, "");
  if (!/^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$/.test(host)) {
    return "";
  }
  if (host === "localhost" || host.endsWith(".local") || /^\d+\.\d+\.\d+\.\d+$/.test(host)) {
    return "";
  }
  return host;
}

export async function getOkCount() {
  const n = await command(["GET", COUNT_KEY]);
  return n == null ? 0 : Number(n) || 0;
}

export async function incrOkCount() {
  const n = await command(["INCR", COUNT_KEY]);
  return Number(n) || 0;
}

export async function listReporters() {
  const raw = await command(["GET", REPORTERS_KEY]);
  if (!raw) {
    return [];
  }
  try {
    const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

async function saveReporters(list) {
  await command(["SET", REPORTERS_KEY, JSON.stringify(list)]);
}

export async function getTokenRecord(token) {
  if (!token || token.length < 32) {
    return null;
  }
  const raw = await command(["GET", `cb:token:${hashToken(token)}`]);
  if (!raw) {
    return null;
  }
  try {
    return typeof raw === "string" ? JSON.parse(raw) : raw;
  } catch {
    return null;
  }
}

export async function enrollReporter({ host, name }) {
  const token = newReporterToken();
  const record = {
    host,
    name,
    enrolled_at: new Date().toISOString(),
  };
  await command(["SET", `cb:token:${hashToken(token)}`, JSON.stringify(record)]);
  const reporters = (await listReporters()).filter((r) => r.host !== host);
  reporters.push({ host, name });
  reporters.sort((a, b) => a.name.localeCompare(b.name));
  await saveReporters(reporters);
  return { token, ...record };
}

export async function revokeHost(host) {
  const reporters = (await listReporters()).filter((r) => r.host !== host);
  await saveReporters(reporters);
}

export async function rateLimitAllow(bucket, limitPerHour) {
  const key = `cb:rl:${bucket}:${new Date().toISOString().slice(0, 13)}`;
  const n = Number(await command(["INCR", key])) || 0;
  if (n === 1) {
    await command(["EXPIRE", key, "3600"]);
  }
  return n <= limitPerHour;
}

export function adminSecretOk(headerValue) {
  const expected = process.env.USAGE_ADMIN_SECRET || "";
  if (!expected || expected.length < 16) {
    return false;
  }
  const got = String(headerValue || "").replace(/^Bearer\s+/i, "");
  const a = Buffer.from(got);
  const b = Buffer.from(expected);
  if (a.length !== b.length) {
    return false;
  }
  return timingSafeEqual(a, b);
}

export async function readJson(req) {
  if (req.body && typeof req.body === "object" && !Buffer.isBuffer(req.body)) {
    return req.body;
  }
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(chunk);
  }
  const raw = Buffer.concat(chunks).toString("utf8").trim();
  if (!raw) {
    return {};
  }
  return JSON.parse(raw);
}

export async function proveVerifyHost(host) {
  const url = `https://${host}/.well-known/checkout-broadcast-usage.json`;
  const res = await fetch(url, { redirect: "error", signal: AbortSignal.timeout(8000) });
  if (!res.ok) {
    const err = new Error(`domain proof failed: HTTP ${res.status} from ${url}`);
    err.status = 400;
    throw err;
  }
  const body = await res.json().catch(() => ({}));
  const claimed = normalizeHost(body.host);
  if (claimed !== host) {
    const err = new Error("domain proof host mismatch");
    err.status = 400;
    throw err;
  }
}

export function corsPublic() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Cache-Control": "no-store",
  };
}

export function jsonHeaders(extra) {
  return { "Content-Type": "application/json", "Cache-Control": "no-store", ...extra };
}
