"""Secure server-side bridge to the VICORA Central Apps Script API.

The Apps Script URL and platform admin key are server configuration only.
Never expose the admin key to browser, Android, or desktop renderer code.
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from flask import jsonify, request

PUBLIC_ACTIONS = frozenset({"applySchool", "activateSchool", "login"})
SCHOOL_ACTIONS = frozenset({
    "logout", "account.create", "class.save", "subject.save", "student.save",
    "school.profile", "host.enroll", "host.heartbeat", "host.revoke",
    "sync.push", "sync.pull",
})
ADMIN_ACTIONS = frozenset({
    "admin.listApplications", "admin.decideApplication", "admin.listSchools",
})
MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def _endpoint():
    value = os.environ.get("VICORA_CENTRAL_APPS_SCRIPT_URL", "").strip()
    if not value:
        raise RuntimeError("VICORA Central Apps Script URL is not configured on this server.")
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme != "https" or parsed.hostname != "script.google.com"
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or not re.fullmatch(r"/macros/s/[^/]+/exec", parsed.path)):
        raise RuntimeError("The configured VICORA Central Apps Script URL is invalid.")
    return value


def _decode_response(response):
    raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise RuntimeError("The central backend response exceeded the allowed size.")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise RuntimeError("The central backend returned an invalid JSON response.")
    if not isinstance(value, dict):
        raise RuntimeError("The central backend returned an unexpected response.")
    return value


def _call(payload=None, query=None):
    endpoint = _endpoint()
    if query:
        endpoint += "?" + urllib.parse.urlencode(query)
        req = urllib.request.Request(endpoint, headers={"Accept": "application/json"}, method="GET")
    else:
        body = json.dumps(payload or {}, separators=(",", ":")).encode("utf-8")
        if len(body) > MAX_REQUEST_BYTES:
            raise ValueError("The central backend request is too large.")
        req = urllib.request.Request(
            endpoint, data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return _decode_response(response), response.status
    except urllib.error.HTTPError as exc:
        try:
            return _decode_response(exc), exc.code
        except Exception:
            return {"ok": False, "error": "The central backend rejected the request."}, exc.code
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError("VICORA Central Apps Script is temporarily unreachable.")


def install_central_backend_routes(app, err):
    @app.get("/api/central/health")
    def vicora_central_health():
        try:
            result, status = _call(query={"action": "health"})
            healthy = status == 200 and result.get("ok") is True and result.get("service") == "VICORA Central Apps Script API"
            if not healthy:
                return jsonify(ok=False, connected=False, error="The central backend health check did not pass."), 503
            return jsonify(ok=True, connected=True, service=result.get("service"), version=result.get("version")), 200
        except (RuntimeError, ValueError) as exc:
            return jsonify(ok=False, connected=False, error=str(exc)), 503

    @app.post("/api/central/request")
    def vicora_central_request():
        if request.content_length and request.content_length > MAX_REQUEST_BYTES:
            return err("The central backend request is too large.", 413)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return err("Send a valid JSON request.")
        action = str(body.get("action") or "")
        if action not in PUBLIC_ACTIONS and action not in SCHOOL_ACTIONS:
            return err("This central backend action is not available through this endpoint.", 403)
        try:
            result, status = _call(payload=body)
            return jsonify(result), status
        except (RuntimeError, ValueError) as exc:
            return err(str(exc), 503)

    @app.post("/api/central/admin")
    def vicora_central_admin():
        if request.content_length and request.content_length > 64 * 1024:
            return err("The administrator request is too large.", 413)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return err("Send a valid JSON request.")
        action = str(body.get("action") or "")
        admin_key = os.environ.get("VICORA_CENTRAL_ADMIN_KEY", "")
        if action not in ADMIN_ACTIONS:
            return err("This central administrator action is not available.", 403)
        if not admin_key:
            return err("Central administrator access is not configured on this server.", 503)
        forwarded = dict(body)
        forwarded["adminKey"] = admin_key
        try:
            result, status = _call(payload=forwarded)
            return jsonify(result), status
        except (RuntimeError, ValueError) as exc:
            return err(str(exc), 503)
