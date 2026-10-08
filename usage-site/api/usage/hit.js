import { corsHeaders, incrOkCount, rateLimitAllow } from "../../lib/kv.js";

const HOUR_LIMIT = 120;

function clientIp(req) {
  const fwd = req.headers["x-forwarded-for"];
  if (typeof fwd === "string" && fwd.length) {
    return fwd.split(",")[0].trim();
  }
  return req.socket?.remoteAddress || "unknown";
}

export default async function handler(req, res) {
  const headers = corsHeaders();
  if (req.method === "OPTIONS") {
    res.writeHead(204, headers);
    return res.end();
  }
  if (req.method !== "POST") {
    res.writeHead(405, { ...headers, "Content-Type": "application/json" });
    return res.end(JSON.stringify({ ok: false, error: "Method not allowed" }));
  }
  try {
    const ip = clientIp(req);
    const allowed = await rateLimitAllow(ip, HOUR_LIMIT);
    if (!allowed) {
      res.writeHead(429, { ...headers, "Content-Type": "application/json", "Retry-After": "3600" });
      return res.end(JSON.stringify({ ok: false, error: "Rate limit exceeded" }));
    }
    const ok_count = await incrOkCount();
    res.writeHead(200, { ...headers, "Content-Type": "application/json" });
    return res.end(JSON.stringify({ ok: true, ok_count }));
  } catch (err) {
    const status = err.status || 500;
    res.writeHead(status, { ...headers, "Content-Type": "application/json" });
    return res.end(JSON.stringify({ ok: false, error: err.message }));
  }
}
