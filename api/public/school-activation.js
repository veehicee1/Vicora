// Public school activation is handled by the same Central Apps Script database
// that issued the School Code and one-time activation token.
const DEFAULT_CENTRAL_ENDPOINT = "https://script.google.com/macros/s/AKfycby6wIxnHhFRyCdGDrt6EDJUoxVBEk1LZILu9O3hNoAI4VV0vkCAlcFHJzwGtCOJA6Kp/exec";

function sendJson(res, status, body) {
  res.status(status);
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store, max-age=0");
  return res.json(body);
}

module.exports = async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return sendJson(res, 405, { ok: false, error: "Method not allowed." });
  }
  const input = typeof req.body === "string" ? (() => { try { return JSON.parse(req.body); } catch (_) { return null; } })() : req.body;
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    return sendJson(res, 400, { ok: false, error: "Invalid activation request." });
  }
  const schoolCode = String(input.school_code || "").trim().toUpperCase();
  const email = String(input.email || "").trim().toLowerCase();
  const activationToken = String(input.activation_token || "").trim();
  const password = String(input.password || "");
  if (!schoolCode || !email || !activationToken || password.length < 12) {
    return sendJson(res, 400, { ok: false, error: "Enter the School Code, registered contact email, activation token and a password of at least 12 characters." });
  }
  const endpoint = String(process.env.VICORA_CENTRAL_APPS_SCRIPT_URL || DEFAULT_CENTRAL_ENDPOINT).trim();
  if (!/^https:\/\/script\.google\.com\/macros\/s\/[^/]+\/exec$/.test(endpoint)) {
    return sendJson(res, 503, { ok: false, error: "VICORA Central Apps Script URL is not configured correctly." });
  }
  try {
    const upstream = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify({ action: "activateSchool", schoolCode, email, activationToken, password }),
      redirect: "follow",
      signal: AbortSignal.timeout(20000)
    });
    const raw = await upstream.text();
    let result;
    try { result = JSON.parse(raw); } catch (_) {
      return sendJson(res, 502, { ok: false, error: "VICORA Central returned an invalid activation response." });
    }
    if (!upstream.ok || !result || result.ok !== true) {
      return sendJson(res, 400, { ok: false, error: result && result.error ? String(result.error).slice(0, 300) : "School activation failed." });
    }
    return sendJson(res, 200, { ok: true, message: "School administrator account activated successfully.", schoolCode: result.data && result.data.schoolCode || schoolCode });
  } catch (error) {
    return sendJson(res, 502, { ok: false, error: error && error.message ? error.message : "Unable to contact VICORA Central." });
  }
};

module.exports.config = { api: { bodyParser: { sizeLimit: "16kb" } } };
