// VICORA Platform Admin bridge for Cloudflare Pages Functions.
// Keeps the Central Apps Script Admin Key out of public source code.
const DEFAULT_CENTRAL_ENDPOINT = "https://script.google.com/macros/s/AKfycby6wIxnHhFRyCdGDrt6EDJUoxVBEk1LZILu9O3hNoAI4VV0vkCAlcFHJzwGtCOJA6Kp/exec";

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store, max-age=0",
      "X-Content-Type-Options": "nosniff"
    }
  });
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
  try { result = JSON.parse(raw); }
  catch (_) { throw new Error("The central VICORA service returned an invalid response."); }
  if (!response.ok || !result || result.ok !== true) {
    const message = result && result.error ? String(result.error).slice(0, 300) : "The central VICORA request failed.";
    const error = new Error(message);
    error.status = /key is invalid|administrator access is not configured/i.test(message) ? 401 : 502;
    throw error;
  }
  return result.data;
}

function timestamp(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  const parsed = Date.parse(String(value || ""));
  return Number.isFinite(parsed) ? Math.floor(parsed / 1000) : 0;
}

async function readBody(request) {
  try {
    const body = await request.json();
    return body && typeof body === "object" && !Array.isArray(body) ? body : null;
  } catch (_) { return null; }
}

export async function onRequest(context) {
  const { request, env } = context;
  const adminKey = String(request.headers.get("x-vicora-platform-token") || "").trim();
  if (!adminKey) return json({ error: "Enter your VICORA Platform Admin Key." }, 401);

  const endpoint = String(env.VICORA_CENTRAL_APPS_SCRIPT_URL || DEFAULT_CENTRAL_ENDPOINT).trim();
  if (!/^https:\/\/script\.google\.com\/macros\/s\/[^/]+\/exec$/.test(endpoint)) {
    return json({ error: "VICORA Central Apps Script URL is not configured correctly." }, 503);
  }

  const url = new URL(request.url);
  const route = url.pathname.replace(/^\/api\/platform\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);

  try {
    if (route.length === 1 && route[0] === "applications" && request.method === "GET") {
      const data = await callCentral(endpoint, { action: "admin.listApplications", adminKey });
      if (!Array.isArray(data)) return json({ error: "Central service returned an unexpected applications list." }, 502);
      const requested = String(url.searchParams.get("status") || "pending").toLowerCase();
      const allowed = ["pending", "approved", "rejected", "all"];
      if (!allowed.includes(requested)) return json({ error: "Invalid application status filter." }, 400);
      const applications = data.map(a => ({
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
      })).filter(a => a.id && (requested === "all" || a.status === requested));
      return json({ applications });
    }

    if (route.length === 3 && route[0] === "applications" && route[2] === "decision" && request.method === "POST") {
      const applicationId = String(route[1] || "").trim();
      if (!applicationId || applicationId.length > 80) return json({ error: "Invalid application ID." }, 400);
      const input = await readBody(request);
      if (!input || !["approve", "reject"].includes(String(input.decision || "").toLowerCase())) {
        return json({ error: "Choose approve or reject." }, 400);
      }
      const note = String(input.note || "").trim();
      if (note.length > 500) return json({ error: "Review note is too long." }, 400);
      const trialDays = Number(input.trialDays);
      if (String(input.decision).toLowerCase() === "approve" && (!Number.isInteger(trialDays) || trialDays < 1 || trialDays > 365)) {
        return json({ error: "Choose a trial period between 1 and 365 days." }, 400);
      }
      const data = await callCentral(endpoint, {
        action: "admin.decideApplication", adminKey, applicationId,
        decision: String(input.decision).toLowerCase(), note, trialDays
      });
      return json({
        message: data.status === "rejected" ? "Application rejected." : "School approved. Activation details have also been emailed to the school contact.",
        school_code: data.schoolCode || "",
        activation_token: data.activationToken || "",
        email_sent: Boolean(data.emailSent),
        trial_days: Number(data.trialDays || 0),
        trial_expires_at: data.trialExpiresAt || ""
      });
    }

    if (route.length === 1 && route[0] === "schools" && request.method === "GET") {
      const data = await callCentral(endpoint, { action: "admin.listSchools", adminKey });
      if (!Array.isArray(data)) return json({ error: "Central service returned an unexpected schools list." }, 502);
      return json({ schools: data });
    }

    if (route.length === 2 && route[0] === "schools" && route[1] === "trial" && request.method === "POST") {
      const input = await readBody(request);
      const schoolId = String(input && input.schoolId || "").trim();
      const trialDays = Number(input && input.trialDays);
      if (!schoolId || schoolId.length > 100) return json({ error: "Invalid school ID." }, 400);
      if (!Number.isInteger(trialDays) || trialDays < 1 || trialDays > 365) return json({ error: "Choose a trial period between 1 and 365 days." }, 400);
      const data = await callCentral(endpoint, { action: "admin.assignTrial", adminKey, schoolId, trialDays });
      return json({
        schoolId: data.schoolId,
        trial_days: data.trialDays,
        trial_expires_at: data.expiresAt,
        subscription_status: data.subscriptionStatus
      });
    }

    return json({ error: "Unsupported platform administration request." }, 405);
  } catch (error) {
    console.error("VICORA platform admin bridge failed:", error && error.message);
    return json({ error: error && error.message ? error.message : "Unable to contact VICORA Central." },
      error && error.status ? error.status : 502);
  }
}
