// Vercel server-side gateway for the GTMC Android student host.
// Never expose admin, pairing, sync, backup, or database endpoints here.
const { Readable } = require("node:stream");

const ALLOWED_EXACT = new Set(["/api/public/info", "/api/public/school-logo"]);
const ALLOWED_PREFIXES = ["/api/student/"];
const ALLOWED_METHODS = new Set(["GET", "POST", "PUT", "PATCH", "DELETE"]);

function sendJson(res, status, body) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.end(JSON.stringify(body));
}

module.exports = async function handler(req, res) {
  const incoming = new URL(req.url || "/", "https://vercel.invalid");
  const path = incoming.pathname;

  // Reject encoded separators/dot segments so URL decoding cannot escape the allowlist.
  if (/%2e|%2f|%5c/i.test(path) || path.includes(String.fromCharCode(92)) || path.split("/").some(part => part === "." || part === "..")) {
    return sendJson(res, 404, { error: "Not found" });
  }

  // This is an allowlist, not a general-purpose reverse proxy.
  if (!ALLOWED_EXACT.has(path) && !ALLOWED_PREFIXES.some(prefix => path.startsWith(prefix))) {
    return sendJson(res, 404, { error: "Not found" });
  }
  if (!ALLOWED_METHODS.has(req.method)) {
    res.setHeader("Allow", "GET, POST, PUT, PATCH, DELETE");
    return sendJson(res, 405, { error: "Method not allowed" });
  }

  const originValue = process.env.ANDROID_HOST_ORIGIN || "";
  const accessId = process.env.CF_ACCESS_CLIENT_ID || "";
  const accessSecret = process.env.CF_ACCESS_CLIENT_SECRET || "";
  if (!originValue || !accessId || !accessSecret) {
    return sendJson(res, 503, { error: "The secure examination gateway is not configured yet." });
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
  for (const key of ["accept", "content-type", "cookie", "user-agent", "accept-language"]) {
    const value = req.headers[key];
    if (typeof value === "string") headers.set(key, value);
  }
  headers.set("CF-Access-Client-Id", accessId);
  headers.set("CF-Access-Client-Secret", accessSecret);

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
