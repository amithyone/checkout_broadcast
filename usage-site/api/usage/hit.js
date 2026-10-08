import {
  getTokenRecord,
  hashToken,
  incrOkCount,
  jsonHeaders,
  rateLimitAllow,
} from "../../lib/kv.js";

const HOUR_LIMIT = 600;

function bearer(req) {
  const h = req.headers.authorization || req.headers.Authorization || "";
  const m = /^Bearer\s+(.+)$/i.exec(String(h));
  return m ? m[1].trim() : "";
}

export default async function handler(req, res) {
  if (req.method === "OPTIONS") {
    res.writeHead(204, { Allow: "POST" });
    return res.end();
  }
  if (req.method !== "POST") {
    res.writeHead(405, jsonHeaders());
    return res.end(JSON.stringify({ ok: false, error: "Method not allowed" }));
  }
  try {
    const token = bearer(req);
    const reporter = await getTokenRecord(token);
    if (!reporter) {
      res.writeHead(401, jsonHeaders());
      return res.end(JSON.stringify({ ok: false, error: "Unknown or missing reporter token" }));
    }
    const allowed = await rateLimitAllow(hashToken(token), HOUR_LIMIT);
    if (!allowed) {
      res.writeHead(429, jsonHeaders({ "Retry-After": "3600" }));
      return res.end(JSON.stringify({ ok: false, error: "Rate limit exceeded" }));
    }
    const ok_count = await incrOkCount();
    res.writeHead(200, jsonHeaders());
    return res.end(JSON.stringify({ ok: true, ok_count, host: reporter.host }));
  } catch (err) {
    const status = err.status || 500;
    res.writeHead(status, jsonHeaders());
    return res.end(JSON.stringify({ ok: false, error: err.message }));
  }
}
