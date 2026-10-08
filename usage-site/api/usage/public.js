import { corsHeaders, getOkCount } from "../../lib/kv.js";

export default async function handler(req, res) {
  const headers = corsHeaders();
  if (req.method === "OPTIONS") {
    res.writeHead(204, headers);
    return res.end();
  }
  if (req.method !== "GET") {
    res.writeHead(405, headers);
    return res.end(JSON.stringify({ ok: false, error: "Method not allowed" }));
  }
  try {
    const ok_count = await getOkCount();
    res.writeHead(200, { ...headers, "Content-Type": "application/json" });
    return res.end(JSON.stringify({ ok: true, ok_count }));
  } catch (err) {
    const status = err.status || 500;
    res.writeHead(status, { ...headers, "Content-Type": "application/json" });
    return res.end(JSON.stringify({ ok: false, error: err.message, ok_count: 0 }));
  }
}
