// VICORA School Admin bridge for Cloudflare Pages Functions.
// Uses the Central Apps Script tenancy/session API; CBT exam data remains on its existing host.
const DEFAULT_CENTRAL_ENDPOINT = "https://script.google.com/macros/s/AKfycby6wIxnHhFRyCdGDrt6EDJUoxVBEk1LZILu9O3hNoAI4VV0vkCAlcFHJzwGtCOJA6Kp/exec";
const SESSION_COOKIE = "vicora_school_session";
const EXAM_ACTIONS = Object.freeze({
  "questions/list": "question.list",
  "questions/save": "question.save",
  "questions/delete": "question.delete",
  "exams/list": "exam.list",
  "exams/save": "exam.save",
  "exams/delete": "exam.delete",
  "exams/questions": "exam.questions.set",
  "exams/assign": "exam.assign"
});

function json(body, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store, max-age=0",
      "X-Content-Type-Options": "nosniff",
      ...extraHeaders
    }
  });
}

function cookieValue(request, name) {
  const header = request.headers.get("Cookie") || "";
  const part = header.split(";").map(x => x.trim()).find(x => x.startsWith(name + "="));
  if (!part) return "";
  try { return decodeURIComponent(part.slice(name.length + 1)); }
  catch (_) { return ""; }
}

function sessionCookie(token, maxAge = 43200) {
  return SESSION_COOKIE + "=" + encodeURIComponent(token) +
    "; Path=/api/admin; Max-Age=" + maxAge + "; HttpOnly; Secure; SameSite=Lax";
}

async function readBody(request) {
  try {
    const value = await request.json();
    return value && typeof value === "object" && !Array.isArray(value) ? value : null;
  } catch (_) { return null; }
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
  catch (_) { throw new Error("VICORA Central returned an invalid response. Check the Apps Script Web App deployment."); }
  if (!response.ok || !result || result.ok !== true) {
    const message = result && result.error ? String(result.error).slice(0, 300) : "VICORA Central request failed.";
    const error = new Error(message);
    error.status = /session expired|invalid.*session|please sign in/i.test(message) ? 401 :
      /incorrect|invalid or inactive|trial has expired|trial period has not yet been assigned/i.test(message) ? 401 : 502;
    throw error;
  }
  return result.data;
}

function endpointFrom(env) {
  const endpoint = String(env.VICORA_CENTRAL_APPS_SCRIPT_URL || DEFAULT_CENTRAL_ENDPOINT).trim();
  if (!/^https:\/\/script\.google\.com\/macros\/s\/[^/]+\/exec$/.test(endpoint)) {
    throw new Error("VICORA Central Apps Script URL is not configured correctly.");
  }
  return endpoint;
}

export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const route = url.pathname.replace(/^\/api\/admin\/?/, "").split("/").filter(Boolean);
  const action = route.join("/");
  const token = cookieValue(request, SESSION_COOKIE);

  try {
    const endpoint = endpointFrom(env);

    if (action === "login" && request.method === "POST") {
      const input = await readBody(request);
      if (!input) return json({ error: "Enter your School Code, email and password." }, 400);
      const data = await callCentral(endpoint, {
        action: "login",
        schoolCode: String(input.school_code || "").trim().toUpperCase(),
        email: String(input.email || "").trim(),
        password: String(input.password || "")
      });
      if (!data || !data.sessionToken) return json({ error: "Central login did not return a valid session." }, 502);
      return json({ ok: true, user: data.user, school: data.school }, 200, {
        "Set-Cookie": sessionCookie(data.sessionToken)
      });
    }

    if (action === "me" && request.method === "GET") {
      if (!token) return json({ user: null }, 401);
      const identity = await callCentral(endpoint, { action: "auth.context", sessionToken: token });
      const profile = await callCentral(endpoint, { action: "school.profile", sessionToken: token });
      const roleNames = {
        school_admin: "School Admin",
        school_owner: "School Owner",
        teacher: "Teacher",
        exam_officer: "Exam Officer",
        viewer: "Viewer"
      };
      const role = String(identity.role || "");
      return json({
        user: {
          userId: String(identity.userId || ""),
          name: String(identity.name || "VICORA User"),
          role: role
        },
        role: role,
        role_name: roleNames[role] || "School User",
        school: profile.school && profile.school.name || "",
        central: true
      });
    }

    if (action === "profile" && request.method === "GET") {
      if (!token) return json({ error: "Please sign in." }, 401);
      const profile = await callCentral(endpoint, { action: "school.profile", sessionToken: token });
      return json(profile);
    }

    if (action === "logout" && request.method === "POST") {
      if (token) {
        await callCentral(endpoint, { action: "logout", sessionToken: token });
      }
      return json({ loggedOut: true }, 200, {
        "Set-Cookie": sessionCookie("", 0)
      });
    }

    if (Object.prototype.hasOwnProperty.call(EXAM_ACTIONS, action) && request.method === "POST") {
      if (!token) return json({ error: "Please sign in." }, 401);
      const input = await readBody(request);
      if (!input) return json({ error: "A valid JSON request body is required." }, 400);
      const data = await callCentral(endpoint, {
        ...input,
        action: EXAM_ACTIONS[action],
        sessionToken: token
      });
      return json({ ok: true, data });
    }

    if (request.method !== "GET" && request.method !== "POST") {
      return json({ error: "Method not allowed." }, 405, { Allow: "GET, POST" });
    }
    return json({ error: "Unsupported School Admin request." }, 404);
  } catch (error) {
    console.error("VICORA School Admin bridge failed:", error && error.message);
    return json(
      { error: error && error.message ? error.message : "Unable to contact VICORA Central." },
      error && error.status ? error.status : 502
    );
  }
}
