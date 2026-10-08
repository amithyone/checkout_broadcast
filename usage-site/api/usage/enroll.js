import {
  adminSecretOk,
  enrollReporter,
  jsonHeaders,
  normalizeHost,
  proveVerifyHost,
  readJson,
} from "../../lib/kv.js";

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.writeHead(405, jsonHeaders());
    return res.end(JSON.stringify({ ok: false, error: "Method not allowed" }));
  }
  if (!adminSecretOk(req.headers.authorization || req.headers["x-admin-secret"])) {
    res.writeHead(401, jsonHeaders());
    return res.end(JSON.stringify({ ok: false, error: "Unauthorized" }));
  }
  try {
    const body = await readJson(req);
    const host = normalizeHost(body.host);
    const name = String(body.name || "").trim().slice(0, 80);
    if (!host || name.length < 2) {
      res.writeHead(400, jsonHeaders());
      return res.end(JSON.stringify({ ok: false, error: "host and name required" }));
    }
    await proveVerifyHost(host);
    const enrolled = await enrollReporter({ host, name });
    res.writeHead(200, jsonHeaders());
    return res.end(
      JSON.stringify({
        ok: true,
        host: enrolled.host,
        name: enrolled.name,
        token: enrolled.token,
        hint: "Store token as CHECKOUT_USAGE_STATS_TOKEN on the verify server. It is shown once.",
      })
    );
  } catch (err) {
    const status = err.status || 500;
    res.writeHead(status, jsonHeaders());
    return res.end(JSON.stringify({ ok: false, error: err.message }));
  }
}
