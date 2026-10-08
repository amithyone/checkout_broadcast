const KEY = "cb:ok_count";

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

export async function getOkCount() {
  const n = await command(["GET", KEY]);
  return n == null ? 0 : Number(n) || 0;
}

export async function incrOkCount() {
  const n = await command(["INCR", KEY]);
  return Number(n) || 0;
}

export async function rateLimitAllow(ip, limitPerHour) {
  const bucket = `cb:rl:${ip}:${new Date().toISOString().slice(0, 13)}`;
  const n = Number(await command(["INCR", bucket])) || 0;
  if (n === 1) {
    await command(["EXPIRE", bucket, "3600"]);
  }
  return n <= limitPerHour;
}

export function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Cache-Control": "no-store",
  };
}
