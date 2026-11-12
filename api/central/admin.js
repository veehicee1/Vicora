// Private server-side bridge from the VICORA Platform Admin page to Apps Script.
// The browser supplies the operator token; the Apps Script admin key never leaves Vercel.
const { timingSafeEqual } = require("node:crypto");

const MAX_BODY_BYTES = 16 * 1024;
const ALLOWED_ACTIONS = new Set([
  "admin.listApplications",
  "admin.decideApplication",
  "admin.listSchools"
]);

function sendJson(res, status, body) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store, max-age=0");
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.end(JSON.stringify(body));
}

function constantTimeMatch(expected, supplied) {
  if (!expected || !supplied) return false;
  const a = Buffer.from(expected, "utf8");
  const b = Buffer.from(supplied, "utf8");
  return a.length === b.length && timingSafeEqual(a, b);
}

module.exports = async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store, max-age=0");
  res.setHeader("Vary", "X-VICORA-PLATFORM-TOKEN");

  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return sendJson(res, 405, { ok: false, error: "Method not allowed." });
  }

  const operatorToken = process.env.VICORA_PLATFORM_ADMIN_TOKEN || "";
  const suppliedToken = req.headers["x-vicora-platform-token"] || "";
  if (!constantTimeMatch(operatorToken, suppliedToken)) {
    return sendJson(res, 401, { ok: false, error: "Platform administrator authorization failed." });
  }

  const endpoint = process.env.VICORA_CENTRAL_APPS_SCRIPT_URL || "";
  const adminKey = process.env.VICORA_PLATFORM_ADMIN_KEY || "";
  if (!endpoint || !adminKey) {
    return sendJson(res, 503, { ok: false, error: "The central platform service is not configured." });
  }

  let target;
  try {
    target = new URL(endpoint);
  } catch (_) {
    return sendJson(res, 503, { ok: false, error: "The central Apps Script URL is invalid." });
  }
  if (target.protocol !== "https:" || target.hostname !== "script.google.com" ||
      !/^\/macros\/s\/[A-Za-z0-9_-]+\/exec$/.test(target.pathname) ||
      target.username || target.password || target.search || target.hash) {
    return sendJson(res, 503, { ok: false, error: "The central Apps Script URL is not an approved endpoint." });
  }

  let raw = "";
  try {
    for await (const chunk of req) {
      raw += chunk.toString("utf8");
      if (Buffer.byteLength(raw, "utf8") > MAX_BODY_BYTES) {
        return sendJson(res, 413, { ok: false, error: "Request is too large." });
      }
    }
  } catch (_) {
    return sendJson(res, 400, { ok: false, error: "Could not read request." });
  }

  let body;
  try {
    body = JSON.parse(raw || "{}");
  } catch (_) {
    return sendJson(res, 400, { ok: false, error: "Send valid JSON." });
  }
  if (!body || typeof body !== "object" || Array.isArray(body) ||
      !ALLOWED_ACTIONS.has(String(body.action || ""))) {
    return sendJson(res, 400, { ok: false, error: "This platform action is not allowed." });
  }

  const payload = { action: body.action, adminKey };
  if (body.action === "admin.decideApplication") {
    payload.applicationId = String(body.applicationId || "").slice(0, 80);
    payload.decision = String(body.decision || "").toLowerCase();
    payload.note = String(body.note || "").slice(0, 500);
    if (!payload.applicationId || !["approve", "reject"].includes(payload.decision)) {
      return sendJson(res, 400, { ok: false, error: "A valid application ID and decision are required." });
    }
  }

  try {
    const upstream = await fetch(target.toString(), {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(payload),
      redirect: "follow",
      signal: AbortSignal.timeout(15000)
    });
    const text = await upstream.text();
    let result;
    try {
      result = JSON.parse(text);
    } catch (_) {
      return sendJson(res, 502, { ok: false, error: "The central service returned an unreadable response." });
    }
    if (!upstream.ok || !result || result.ok !== true) {
      return sendJson(res, upstream.ok ? 400 : 502, {
        ok: false,
        error: String(result && result.error || "The central service rejected the request.").slice(0, 400)
      });
    }
    return sendJson(res, 200, result);
  } catch (_) {
    return sendJson(res, 502, { ok: false, error: "VICORA Central is temporarily unreachable." });
  }
};

module.exports.config = { api: { bodyParser: false } };
