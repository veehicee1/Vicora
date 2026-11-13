// VICORA School Admin bridge for Cloudflare Pages Functions.
// Keeps the school session token in an HttpOnly cookie.
const DEFAULT_ENDPOINT = "https://script.google.com/macros/s/AKfycby6wIxnHhFRyCdGDrt6EDJUoxVBEk1LZILu9O3hNoAI4VV0vkCAlcFHJzwGtCOJA6Kp/exec";
const COOKIE = "vicora_school_session";
const MAX_AGE = 60 * 60 * 12;

function json(data, status = 200, headers = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store, max-age=0",
      "X-Content-Type-Options": "nosniff",
      ...headers
    }
  });
}
function parseBody(value) {
  if (typeof value === "string") { try { value = JSON.parse(value); } catch (_) { return null; } }
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}
function cookieMap(request) {
  return String(request.headers.get("Cookie") || "").split(";").reduce((out, part) => {
    const i = part.indexOf("=");
    if (i > 0) {
      try { out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim()); } catch (_) {}
    }
    return out;
  }, {});
}
function encodeIdentity(value) {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/=/g, "").replace(/\\+/g, "-").replace(/\\//g, "_");
}
function decodeIdentity(value) {
  try {
    const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
    const binary = atob(base64 + "=".repeat((4 - base64.length % 4) % 4));
    const bytes = Uint8Array.from(binary, c => c.charCodeAt(0));
    const parsed = JSON.parse(new TextDecoder().decode(bytes));
    return parsed && parsed.token && parsed.user && parsed.school ? parsed : null;
  } catch (_) { return null; }
}
function getIdentity(request) {
  const raw = cookieMap(request)[COOKIE];
  return raw ? decodeIdentity(raw) : null;
}
function sessionCookie(value, maxAge = MAX_AGE) {
  return COOKIE + "=" + encodeURIComponent(value) + "; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=" + maxAge;
}
async function central(endpoint, payload) {
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
  catch (_) { const error = new Error("VICORA Central returned an unreadable response."); error.status = 502; throw error; }
  if (!response.ok || !result || result.ok !== true) {
    const error = new Error(result && result.error ? String(result.error).slice(0, 300) : "VICORA Central request failed.");
    error.status = response.ok ? 401 : 502;
    throw error;
  }
  return result.data;
}

export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const path = "/" + url.pathname.replace(/^\\/api\\/admin\\/?/, "").split("/").filter(Boolean).map(decodeURIComponent).join("/");
  const endpoint = String(env.VICORA_CENTRAL_APPS_SCRIPT_URL || env.VICORA_APPS_SCRIPT_URL || DEFAULT_ENDPOINT).trim();

  if (!/^https:\\/\\/script\\.google\\.com\\/macros\\/s\\/[^/]+\\/exec$/.test(endpoint)) {
    return json({ error: "VICORA Central Apps Script URL is not configured correctly." }, 503);
  }

  if (request.method === "POST" && path === "/login") {
    const input = parseBody(await request.json().catch(() => null));
    const schoolCode = String(input && input.school_code || "").trim().toUpperCase();
    const email = String(input && (input.email || input.username) || "").trim().toLowerCase();
    const password = String(input && input.password || "");
    if (!schoolCode || !email || !password) return json({ error: "Enter your School Code, Admin Email and Password." }, 400);
    try {
      const data = await central(endpoint, { action: "login", schoolCode, email, password });
      if (!data || !data.sessionToken || !data.user || !data.school) {
        return json({ error: "VICORA Central returned an incomplete sign-in response." }, 502);
      }
      const identity = { token: data.sessionToken, user: data.user, school: data.school, expiresAt: data.expiresAt };
      return json({ ok: true, signedIn: true }, 200, { "Set-Cookie": sessionCookie(encodeIdentity(identity)) });
    } catch (error) {
      return json({ error: error.message || "Unable to sign in to VICORA Central." }, error.status || 502);
    }
  }

  if (request.method === "GET" && path === "/me") {
    const identity = getIdentity(request);
    if (!identity) return json({ user: null });
    return json({
      user: { username: identity.user.email, name: identity.user.name, email: identity.user.email },
      role: identity.user.role === "school_admin" || identity.user.role === "school_owner" ? "super_admin" : identity.user.role,
      role_name: "School Admin",
      school: identity.school.name || identity.school.schoolCode,
      school_code: identity.school.schoolCode
    });
  }

  if (request.method === "POST" && path === "/logout") {
    const identity = getIdentity(request);
    if (identity) {
      try { await central(endpoint, { action: "logout", sessionToken: identity.token }); } catch (_) {}
    }
    return json({ ok: true, loggedOut: true }, 200, { "Set-Cookie": sessionCookie("", 0) });
  }

  if (request.method === "GET" && path === "/profile") {
    const identity = getIdentity(request);
    if (!identity) return json({ error: "Please sign in." }, 401);
    try {
      return json(await central(endpoint, { action: "school.profile", sessionToken: identity.token }));
    } catch (error) {
      return json({ error: error.message || "Unable to load school profile." }, error.status || 401,
        { "Set-Cookie": sessionCookie("", 0) });
    }
  }

  return json({ error: "This School Admin feature is not yet connected to VICORA Central. Your sign-in session is preserved." }, 501);
}
