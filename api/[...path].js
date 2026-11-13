// Vercel server-side gateway for VICORA public onboarding, platform review and student APIs.
// Never expose general school admin, pairing, sync, backup, or database endpoints here.
const { Readable } = require("node:stream");

const ALLOWED_EXACT = new Set(["/api/public/info", "/api/public/school-logo", "/api/public/schools/resolve", "/api/public/school-applications", "/api/public/school-activation"]);
const ALLOWED_PREFIXES = ["/api/student/", "/api/platform/", "/api/android-host/"];
const ALLOWED_METHODS = new Set(["GET", "POST", "PUT", "PATCH", "DELETE"]);

function sendJson(res, status, body) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.end(JSON.stringify(body));
}


async function handlePlatformAdmin(req, res, incoming) {
  const path = incoming.pathname;

  // Route platform administration to the existing Google Apps Script backend.
  if (path.startsWith("/api/platform/")) {
    if (!["GET", "POST"].includes(req.method)) {
      res.setHeader("Allow", "GET, POST");
      return sendJson(res, 405, { error: "Method not allowed" });
    }
    return handlePlatformAdmin(req, res, incoming);
  }
  const token = String(req.headers["x-vicora-platform-token"] || "").trim();
  if (!token) return sendJson(res, 401, { error: "Enter the Platform Super Admin Key." });
  let scriptUrl;
  try { scriptUrl = new URL(process.env.VICORA_APPS_SCRIPT_URL || ""); } catch (_) {
    return sendJson(res, 503, { error: "The Google Apps Script URL is not configured in Vercel." });
  }
  if (scriptUrl.protocol !== "https:" || scriptUrl.hostname !== "script.google.com" ||
      !/^\/macros\/s\/[^/]+\/exec$/.test(scriptUrl.pathname) || scriptUrl.search || scriptUrl.hash) {
    return sendJson(res, 503, { error: "The configured Google Apps Script URL is invalid." });
  }
  let action, payload = { adminKey: token };
  if (req.method === "GET" && path === "/api/platform/applications") {
    action = "admin.listApplications";
  } else {
    const match = path.match(/^\/api\/platform\/applications\/([^/]+)\/decision$/);
    if (req.method !== "POST" || !match) {
      res.setHeader("Allow", "GET, POST");
      return sendJson(res, 404, { error: "Platform admin endpoint not found." });
    }
    let body = "";
    try {
      for await (const chunk of req) {
        body += chunk;
        if (body.length > 20000) return sendJson(res, 413, { error: "Request is too large." });
      }
      const input = body ? JSON.parse(body) : {};
      action = "admin.decideApplication";
      payload.applicationId = decodeURIComponent(match[1]);
      payload.decision = input.decision;
      payload.note = input.note || "";
    } catch (_) { return sendJson(res, 400, { error: "Invalid request body." }); }
  }
  try {
    const upstream = await fetch(scriptUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify({ action, ...payload }),
      redirect: "follow",
      signal: AbortSignal.timeout(15000)
    });
    const raw = await upstream.text();
    let result;
    try { result = JSON.parse(raw); } catch (_) {
      return sendJson(res, 502, { error: "Google Apps Script returned an unreadable response." });
    }
    if (!upstream.ok || !result || result.ok !== true) {
      return sendJson(res, upstream.ok ? 401 : 502, { error: (result && result.error) || "Google Apps Script request failed." });
    }
    if (action === "admin.listApplications") {
      const status = String(incoming.searchParams.get("status") || "pending").toLowerCase();
      const rows = Array.isArray(result.data) ? result.data : [];
      const filtered = status === "all" ? rows : rows.filter(row => String(row.status || "").toLowerCase() === status);
      const applications = filtered.map(row => ({
        id: row.application_id, school_name: row.school_name || "",
        contact_name: row.contact_name || "", email: row.contact_email || "",
        phone: row.contact_phone || "", address: row.address || "",
        country: row.country || "", status: row.status || "",
        submitted_ts: row.submitted_at ? Math.floor(new Date(row.submitted_at).getTime() / 1000) : null,
        review_note: row.decision_note || ""
      }));
      return sendJson(res, 200, { applications });
    }
    const data = result.data || {};
    return sendJson(res, 200, {
      message: data.status === "rejected" ? "Application rejected." : "Application approved.",
      school_code: data.schoolCode || "", activation_token: data.activationToken || "",
      email_sent: Boolean(data.emailSent), contact_email: data.contactEmail || ""
    });
  } catch (_) {
    return sendJson(res, 502, { error: "Could not reach the Google Apps Script backend. Please try again." });
  }
}

module.exports = async function handler(req, res) {
  const incoming = new URL(req.url || "/", "https://vercel.invalid");
  const path = incoming.pathname;

  // Reject encoded separators/dot segments so URL decoding cannot escape the allowlist.
  if (/%2e|%2f|%5c/i.test(path) || path.includes(String.fromCharCode(92)) || path.split("/").some(part => part === "." || part === "..")) {
    return sendJson(res, 404, { error: "Not found" });
  }

  // This is an allowlist, not a general-purpose reverse proxy.
  const adminGatewayEnabled = process.env.VICORA_ENABLE_ADMIN_GATEWAY === "1";
  const allowedAdminPath = adminGatewayEnabled && path.startsWith("/api/admin/");
  if (!ALLOWED_EXACT.has(path) && !ALLOWED_PREFIXES.some(prefix => path.startsWith(prefix)) && !allowedAdminPath) {
    return sendJson(res, 404, { error: "Not found" });
  }
  if (!ALLOWED_METHODS.has(req.method)) {
    res.setHeader("Allow", "GET, POST, PUT, PATCH, DELETE");
    return sendJson(res, 405, { error: "Method not allowed" });
  }

  const originValue = process.env.VICORA_API_ORIGIN || process.env.ANDROID_HOST_ORIGIN || "";
  const accessId = process.env.CF_ACCESS_CLIENT_ID || "";
  const accessSecret = process.env.CF_ACCESS_CLIENT_SECRET || "";
  if (!originValue || Boolean(accessId) !== Boolean(accessSecret)) {
    return sendJson(res, 503, { error: "The VICORA API gateway is not configured correctly." });
  }

  let origin;
  try {
    origin = new URL(originValue);
  } catch (_) {
    return sendJson(res, 503, { error: "The secure examination gateway address is invalid." });
  }
  if (origin.protocol !== "https:" || origin.username || origin.password ||
      origin.pathname !== "/" || origin.search || origin.hash) {
    return sendJson(res, 503, { error: "The Android host must use a trusted HTTPS tunnel origin." });
  }

  const target = new URL(path + incoming.search, origin);
  const headers = new Headers();
  for (const key of ["accept", "content-type", "cookie", "user-agent", "accept-language", "x-vicora-platform-token", "x-vicora-host-token", "authorization"]) {
    const value = req.headers[key];
    if (typeof value === "string") headers.set(key, value);
  }
  // Public persistent hosts such as Render can be reached directly over HTTPS.
  // A private Android/Windows LAN host can continue using Cloudflare Access.
  if (accessId && accessSecret) {
    headers.set("CF-Access-Client-Id", accessId);
    headers.set("CF-Access-Client-Secret", accessSecret);
  }

  const hasBody = !["GET", "HEAD"].includes(req.method);
  try {
    const upstream = await fetch(target, {
      method: req.method,
      headers,
      body: hasBody ? req : undefined,
      ...(hasBody ? { duplex: "half" } : {}),
      redirect: "manual",
      signal: AbortSignal.timeout(9000)
    });

    // Do not forward redirects that could disclose or navigate to the private host.
    if (upstream.status >= 300 && upstream.status < 400) {
      return sendJson(res, 502, { error: "The examination host returned an unexpected redirect." });
    }

    res.statusCode = upstream.status;
    for (const key of ["content-type", "cache-control", "retry-after"]) {
      const value = upstream.headers.get(key);
      if (value) res.setHeader(key, value);
    }
    res.setHeader("Cache-Control", "no-store");
    res.setHeader("X-Content-Type-Options", "nosniff");
    const cookies = typeof upstream.headers.getSetCookie === "function"
      ? upstream.headers.getSetCookie()
      : (upstream.headers.get("set-cookie") ? [upstream.headers.get("set-cookie")] : []);
    if (cookies.length) res.setHeader("Set-Cookie", cookies);

    if (!upstream.body) return res.end();
    Readable.fromWeb(upstream.body).pipe(res);
  } catch (_) {
    if (!res.headersSent) return sendJson(res, 502, { error: "The Android examination host is temporarily unreachable." });
    res.destroy();
  }
};

module.exports.config = { api: { bodyParser: false } };
