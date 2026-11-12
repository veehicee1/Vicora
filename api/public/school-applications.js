// Public school-application endpoint.
// Forwards only the public applySchool action to the VICORA Central Apps Script.
function sendJson(res, status, body) {
  res.status(status).setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  return res.json(body);
}

module.exports = async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return sendJson(res, 405, { ok: false, error: "Method not allowed." });
  }

  const defaultEndpoint = "https://script.google.com/macros/s/AKfycby6wIxnHhFRyCdGDrt6EDJUoxVBEk1LZILu9O3hNoAI4VV0vkCAlcFHJzwGtCOJA6Kp/exec";
  const endpoint = String(process.env.VICORA_CENTRAL_APPS_SCRIPT_URL || defaultEndpoint).trim();
  if (!/^https:\/\/script\.google\.com\/macros\/s\/[^/]+\/exec$/.test(endpoint)) {
    return sendJson(res, 503, { ok: false, error: "School registration service is not configured. Please contact VICORA support." });
  }

  let input = req.body;
  if (typeof input === "string") {
    try { input = JSON.parse(input); } catch (_) { input = null; }
  }
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    return sendJson(res, 400, { ok: false, error: "Invalid application data." });
  }

  // Never accept an arbitrary Apps Script action or forward client-supplied admin credentials.
  const body = {
    action: "applySchool",
    schoolName: input.schoolName,
    contactName: input.contactName,
    contactEmail: input.contactEmail,
    contactPhone: input.contactPhone,
    country: input.country,
    state: input.state,
    address: input.address,
    schoolType: input.schoolType
  };

  for (const [key, max] of Object.entries({
    schoolName: 160, contactName: 120, contactEmail: 180, contactPhone: 40,
    country: 80, state: 80, address: 240, schoolType: 60
  })) {
    if (typeof body[key] !== "string" || body[key].trim().length > max) {
      return sendJson(res, 400, { ok: false, error: "Please check the application fields and try again." });
    }
    body[key] = body[key].trim();
  }

  try {
    const upstream = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(body),
      redirect: "follow",
      signal: AbortSignal.timeout(15000)
    });
    const raw = await upstream.text();
    let result;
    try { result = JSON.parse(raw); } catch (_) {
      console.error("VICORA Central returned a non-JSON response for applySchool.");
      return sendJson(res, 502, { ok: false, error: "The central registration service returned an invalid response. Please try again later." });
    }

    if (!upstream.ok || !result || result.ok !== true) {
      const message = result && result.error ? String(result.error).slice(0, 300) : "Application could not be submitted.";
      return sendJson(res, upstream.ok ? 400 : 502, { ok: false, error: message });
    }
    return sendJson(res, 200, { ok: true, data: result.data });
  } catch (error) {
    console.error("VICORA school application forwarding failed:", error && error.message);
    return sendJson(res, 502, { ok: false, error: "Unable to reach VICORA Central right now. Please try again later." });
  }
};

module.exports.config = { api: { bodyParser: { sizeLimit: "32kb" } } };
