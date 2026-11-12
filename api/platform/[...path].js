// Private VICORA Platform Admin bridge.
// Keeps the central Apps Script Admin Key out of the browser-to-Apps-Script payload
// until this server-side handler forwards it over HTTPS.
const DEFAULT_CENTRAL_ENDPOINT = "https://script.google.com/macros/s/AKfycby6wIxnHhFRyCdGDrt6EDJUoxVBEk1LZILu9O3hNoAI4VV0vkCAlcFHJzwGtCOJA6Kp/exec";

function sendJson(res, status, body) {
  res.status(status);
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store, max-age=0");
  res.setHeader("X-Content-Type-Options", "nosniff");
  return res.json(body);
}

function parseBody(body) {
  if (typeof body === "string") {
    try { return JSON.parse(body); } catch (_) { return null; }
  }
  return body && typeof body === "object" && !Array.isArray(body) ? body : null;
}

function timestamp(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  const parsed = Date.parse(String(value || ""));
  return Number.isFinite(parsed) ? Math.floor(parsed / 1000) : 0;
}

async function callCentral(endpoint, payload) {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Accept": "application/json" },
    body: JSON.stringify(payload),
    redirect: "follow",
    signal: AbortSignal.timeout(20000)
  });
  const raw = await response.text();
  let result;
  try { result = JSON.parse(raw); } catch (_) {
    throw new Error("The central VICORA service returned an invalid response.");
  }
  if (!response.ok || !result || result.ok !== true) {
    const message = result && result.error ? String(result.error).slice(0, 300) : "The central VICORA request failed.";
    const error = new Error(message);
    error.status = /key is invalid|administrator access is not configured/i.test(message) ? 401 : 502;
    throw error;
  }
  return result.data;
}

module.exports = async function handler(req, res) {
  const adminKey = String(req.headers["x-vicora-platform-token"] || "").trim();
  if (!adminKey) return sendJson(res, 401, { error: "Enter your VICORA Platform Admin Key." });

  const endpoint = String(process.env.VICORA_CENTRAL_APPS_SCRIPT_URL || DEFAULT_CENTRAL_ENDPOINT).trim();
  if (!/^https:\/\/script\.google\.com\/macros\/s\/[^/]+\/exec$/.test(endpoint)) {
    return sendJson(res, 503, { error: "VICORA Central Apps Script URL is not configured correctly." });
  }

  const route = Array.isArray(req.query && req.query.path)
    ? req.query.path.map(String)
    : String(req.url || "").split("?")[0].replace(/^\/api\/platform\/?/, "").split("/").filter(Boolean);

  try {
    if (route.length === 1 && route[0] === "applications" && req.method === "GET") {
      const data = await callCentral(endpoint, { action: "admin.listApplications", adminKey });
      if (!Array.isArray(data)) return sendJson(res, 502, { error: "Central service returned an unexpected applications list." });
      const requested = String((req.query && req.query.status) || "pending").toLowerCase();
      const allowed = ["pending", "approved", "rejected", "all"];
      if (!allowed.includes(requested)) return sendJson(res, 400, { error: "Invalid application status filter." });
      const applications = data.map((a) => ({
        id: String(a.application_id || ""),
        school_name: a.school_name || "",
        contact_name: a.contact_name || "",
        email: a.contact_email || "",
        phone: a.contact_phone || "",
        address: a.address || "",
        country: a.country || "",
        status: String(a.status || "").toLowerCase(),
        submitted_ts: timestamp(a.submitted_at),
        review_note: a.decision_note || ""
      })).filter((a) => a.id && (requested === "all" || a.status === requested));
      return sendJson(res, 200, { applications });
    }

    if (route.length === 3 && route[0] === "applications" && route[2] === "decision" && req.method === "POST") {
      const applicationId = String(route[1] || "").trim();
      if (!applicationId || applicationId.length > 80) return sendJson(res, 400, { error: "Invalid application ID." });
      const input = parseBody(req.body);
      if (!input || !["approve", "reject"].includes(String(input.decision || "").toLowerCase())) {
        return sendJson(res, 400, { error: "Choose approve or reject." });
      }
      const note = String(input.note || "").trim();
      if (note.length > 500) return sendJson(res, 400, { error: "Review note is too long." });
      const data = await callCentral(endpoint, {
        action: "admin.decideApplication",
        adminKey,
        applicationId,
        decision: String(input.decision).toLowerCase(),
        note
      });
      return sendJson(res, 200, {
        message: data.status === "rejected" ? "Application rejected." : "School approved. Activation details have also been emailed to the school contact.",
        school_code: data.schoolCode || "",
        activation_token: data.activationToken || "",
        email_sent: Boolean(data.emailSent)
      });
    }

    res.setHeader("Allow", "GET, POST");
    return sendJson(res, 405, { error: "Unsupported platform administration request." });
  } catch (error) {
    console.error("VICORA platform admin bridge failed:", error && error.message);
    return sendJson(res, error && error.status ? error.status : 502, {
      error: error && error.message ? error.message : "Unable to contact VICORA Central."
    });
  }
};

module.exports.config = { api: { bodyParser: { sizeLimit: "32kb" } } };
