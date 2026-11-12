// Private server-side bridge from the VICORA Platform Admin page to Apps Script.
// The browser supplies the operator token; the Apps Script admin key never leaves Vercel.
const { timingSafeEqual } = require("node:crypto");

const MAX_BODY_BYTES = 16 * 1024;
const ALLOWED_ACTIONS = new Set([
  "admin.listApplications",
  "admin.decideApplication",
  "admin.listSchools",
  "admin.setSchoolStatus",
  "admin.listSubscriptionData",
  "admin.saveSubscriptionPlan",
  "admin.assignSubscription",
  "admin.setSubscriptionStatus",
  "admin.recordSubscriptionPayment"
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
  if (body.action === "admin.setSchoolStatus") {
    payload.schoolId = String(body.schoolId || "").slice(0, 100);
    payload.status = String(body.status || "").toLowerCase();
    if (!payload.schoolId || !["approved", "suspended"].includes(payload.status)) {
      return sendJson(res, 400, { ok: false, error: "A valid school ID and status are required." });
    }
  }

  if (body.action === "admin.saveSubscriptionPlan") {
    payload.planId = String(body.planId || "").slice(0, 100);
    payload.planName = String(body.planName || "").slice(0, 100);
    payload.billingCycle = String(body.billingCycle || "").toLowerCase();
    payload.durationDays = Number(body.durationDays);
    payload.amount = Number(body.amount);
    payload.currency = String(body.currency || "NGN").slice(0, 8);
    payload.graceDays = Number(body.graceDays || 0);
    payload.maxStudents = Number(body.maxStudents || 0);
    payload.maxStaff = Number(body.maxStaff || 0);
    payload.features = Array.isArray(body.features) ? body.features.slice(0, 30).map(x => String(x).slice(0, 100)) : [];
    payload.active = body.active !== false;
    if (!payload.planName || !["monthly", "termly", "yearly", "custom"].includes(payload.billingCycle) ||
        !Number.isInteger(payload.durationDays) || payload.durationDays < 1 || payload.durationDays > 3660 ||
        !Number.isFinite(payload.amount) || payload.amount < 0 ||
        !Number.isInteger(payload.graceDays) || payload.graceDays < 0 || payload.graceDays > 90) {
      return sendJson(res, 400, { ok: false, error: "Enter valid plan details, duration, price and grace period." });
    }
  }
  if (body.action === "admin.assignSubscription") {
    payload.schoolId = String(body.schoolId || "").slice(0, 100);
    payload.planId = String(body.planId || "").slice(0, 100);
    payload.startAt = String(body.startAt || "").slice(0, 40);
    payload.notes = String(body.notes || "").slice(0, 500);
    if (!payload.schoolId || !payload.planId) return sendJson(res, 400, { ok: false, error: "Choose a school and subscription plan." });
  }
  if (body.action === "admin.setSubscriptionStatus") {
    payload.subscriptionId = String(body.subscriptionId || "").slice(0, 100);
    payload.status = String(body.status || "").toLowerCase();
    if (!payload.subscriptionId || !["active", "suspended", "cancelled"].includes(payload.status)) {
      return sendJson(res, 400, { ok: false, error: "A valid subscription and status are required." });
    }
  }
  if (body.action === "admin.recordSubscriptionPayment") {
    payload.subscriptionId = String(body.subscriptionId || "").slice(0, 100);
    payload.amount = Number(body.amount);
    payload.currency = String(body.currency || "NGN").slice(0, 8);
    payload.paymentMethod = String(body.paymentMethod || "manual").slice(0, 60);
    payload.reference = String(body.reference || "").slice(0, 120);
    payload.status = String(body.status || "pending").toLowerCase();
    payload.notes = String(body.notes || "").slice(0, 500);
    if (!payload.subscriptionId || !Number.isFinite(payload.amount) || payload.amount <= 0 ||
        !["pending", "verified", "rejected"].includes(payload.status)) {
      return sendJson(res, 400, { ok: false, error: "Enter a valid subscription, amount and payment status." });
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
