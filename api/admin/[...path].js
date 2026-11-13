// VICORA School Admin bridge to the existing Central Apps Script API.
// Session tokens remain in an HttpOnly cookie and are never returned to browser JS.
const DEFAULT_ENDPOINT = "https://script.google.com/macros/s/AKfycby6wIxnHhFRyCdGDrt6EDJUoxVBEk1LZILu9O3hNoAI4VV0vkCAlcFHJzwGtCOJA6Kp/exec";
const COOKIE = "vicora_school_session";
const MAX_AGE = 60 * 60 * 12;

function send(res, status, data) {
  res.status(status);
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store, max-age=0");
  res.setHeader("X-Content-Type-Options", "nosniff");
  return res.json(data);
}
function parseBody(body) {
  if (typeof body === "string") { try { return JSON.parse(body); } catch (_) { return null; } }
  return body && typeof body === "object" && !Array.isArray(body) ? body : null;
}
function cookies(req) {
  return String(req.headers.cookie || "").split(";").reduce((out, part) => {
    const i = part.indexOf("=");
    if (i > 0) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
    return out;
  }, {});
}
function clearCookie(res) {
  res.setHeader("Set-Cookie", COOKIE + "=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0");
}
function setCookie(res, value) {
  res.setHeader("Set-Cookie", COOKIE + "=" + encodeURIComponent(value) + "; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=" + MAX_AGE);
}
function getIdentity(req) {
  const raw = cookies(req)[COOKIE];
  if (!raw) return null;
  try {
    const value = JSON.parse(Buffer.from(raw, "base64url").toString("utf8"));
    return value && value.token && value.user && value.school ? value : null;
  } catch (_) { return null; }
}
async function central(payload) {
  const endpoint = String(process.env.VICORA_CENTRAL_APPS_SCRIPT_URL || process.env.VICORA_APPS_SCRIPT_URL || DEFAULT_ENDPOINT).trim();
  if (!/^https:\/\/script\.google\.com\/macros\/s\/[^/]+\/exec$/.test(endpoint)) {
    const e = new Error("VICORA Central Apps Script URL is not configured correctly."); e.status = 503; throw e;
  }
  const response = await fetch(endpoint, {
    method: "POST", headers: { "Content-Type": "application/json", "Accept": "application/json" },
    body: JSON.stringify(payload), redirect: "follow", signal: AbortSignal.timeout(20000)
  });
  const raw = await response.text();
  let result;
  try { result = JSON.parse(raw); } catch (_) { const e = new Error("VICORA Central returned an unreadable response."); e.status = 502; throw e; }
  if (!response.ok || !result || result.ok !== true) {
    const e = new Error(result && result.error ? String(result.error).slice(0, 300) : "VICORA Central request failed.");
    e.status = response.ok ? 401 : 502; throw e;
  }
  return result.data;
}
module.exports = async function handler(req, res) {
  const path = "/" + (Array.isArray(req.query && req.query.path) ? req.query.path.map(String).join("/") : String(req.url || "").split("?")[0].replace(/^\/api\/admin\/?/, ""));
  if (req.method === "POST" && path === "/login") {
    const input = parseBody(req.body);
    const schoolCode = String(input && input.school_code || "").trim().toUpperCase();
    const email = String(input && (input.email || input.username) || "").trim().toLowerCase();
    const password = String(input && input.password || "");
    if (!schoolCode || !email || !password) return send(res, 400, { error: "Enter your School Code, Admin Email and Password." });
    try {
      const data = await central({ action: "login", schoolCode, email, password });
      if (!data || !data.sessionToken || !data.user || !data.school) return send(res, 502, { error: "VICORA Central returned an incomplete sign-in response." });
      const identity = { token: data.sessionToken, user: data.user, school: data.school, expiresAt: data.expiresAt };
      setCookie(res, Buffer.from(JSON.stringify(identity)).toString("base64url"));
      return send(res, 200, { ok: true, signedIn: true });
    } catch (e) { return send(res, e.status || 502, { error: e.message || "Unable to sign in to VICORA Central." }); }
  }
  if (req.method === "GET" && path === "/me") {
    const identity = getIdentity(req);
    if (!identity) return send(res, 200, { user: null });
    return send(res, 200, {
      user: { username: identity.user.email, name: identity.user.name, email: identity.user.email },
      role: identity.user.role === "school_admin" || identity.user.role === "school_owner" ? "super_admin" : identity.user.role,
      role_name: "School Admin",
      school: identity.school.name || identity.school.schoolCode,
      school_code: identity.school.schoolCode
    });
  }
  if (req.method === "POST" && path === "/logout") {
    const identity = getIdentity(req);
    if (identity) { try { await central({ action: "logout", sessionToken: identity.token }); } catch (_) {} }
    clearCookie(res);
    return send(res, 200, { ok: true, loggedOut: true });
  }
  if (req.method === "GET" && path === "/profile") {
    const identity = getIdentity(req);
    if (!identity) return send(res, 401, { error: "Please sign in." });
    try { return send(res, 200, await central({ action: "school.profile", sessionToken: identity.token })); }
    catch (e) { clearCookie(res); return send(res, e.status || 401, { error: e.message }); }
  }
  return send(res, 501, { error: "This School Admin feature is not yet connected to VICORA Central. Your sign-in session is preserved." });
};
