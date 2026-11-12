"""Secure server-side bridge to the VICORA Central Apps Script API.

Apps Script owns school identity and central credentials. Local SQLite remains
the CBT engine. Central school IDs are mirrored locally without touching legacy
students, exams, attempts, answers, scores or reports.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from flask import jsonify, request, session
from werkzeug.security import generate_password_hash

PUBLIC_ACTIONS = frozenset({"applySchool", "activateSchool", "login"})
SCHOOL_ACTIONS = frozenset({
    "logout", "account.create", "class.save", "subject.save", "student.save",
    "school.profile", "host.enroll", "host.heartbeat", "host.revoke",
    "sync.push", "sync.pull",
})
ADMIN_ACTIONS = frozenset({
    "admin.listApplications", "admin.decideApplication", "admin.listSchools",
})
ROLE_MAP = {
    "school_admin": "super_admin",
    "school_owner": "super_admin",
    "teacher": "exam_administrator",
    "exam_officer": "exam_administrator",
    "viewer": "auditor",
}
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


def _post_action(action, **fields):
    result, status = _call(payload={"action": action, **fields})
    if status != 200 or result.get("ok") is not True:
        message = result.get("error") or "VICORA Central rejected the request."
        raise ValueError(message)
    data = result.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("VICORA Central returned an incomplete response.")
    return data


def _school_from_central(code):
    result, status = _call(query={"action": "resolveSchool", "code": code})
    if status != 200 or result.get("ok") is not True or not isinstance(result.get("school"), dict):
        raise ValueError(result.get("error") or "The approved school could not be resolved centrally.")
    return result["school"]


def _ensure_local_school(connection, school):
    school_id = str(school.get("schoolId") or "").strip()
    code = str(school.get("schoolCode") or "").strip().upper()
    name = str(school.get("name") or "").strip()
    if not school_id or not code or not name or school.get("status") != "approved":
        raise RuntimeError("VICORA Central returned an invalid or inactive school identity.")
    by_id = connection.execute("SELECT school_code,name FROM main.schools WHERE school_id=?", (school_id,)).fetchone()
    by_code = connection.execute("SELECT school_id FROM main.schools WHERE upper(school_code)=?", (code,)).fetchone()
    if by_id and (by_id["school_code"].upper() != code):
        raise RuntimeError("The central School Code conflicts with the local school identity.")
    if by_code and by_code["school_id"] != school_id:
        raise RuntimeError("This School Code is already assigned to a different local school.")
    if not by_id:
        now = int(time.time())
        connection.execute(
            """INSERT INTO main.schools
            (school_id,school_code,name,status,is_legacy_default,created_ts,approved_ts,
             contact_email,contact_phone,country,address,website)
            VALUES(?,?,?,'approved',0,?,?,?,?,?,?,?)""",
            (school_id, code, name[:120], now, now, "", "", str(school.get("country") or "Nigeria")[:80],
             "", "")
        )
        connection.commit()
    return school_id


def _ensure_local_admin(connection, school_id, user):
    user_id = str(user.get("userId") or "").strip()
    email = str(user.get("email") or "").strip().lower()
    name = str(user.get("name") or email).strip()
    central_role = str(user.get("role") or "")
    local_role = ROLE_MAP.get(central_role)
    if not user_id or not email or not local_role:
        raise ValueError("This central account role is not enabled for the CBT portal.")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS central_user_map (
            central_user_id TEXT PRIMARY KEY, school_id TEXT NOT NULL,
            email TEXT NOT NULL, local_username TEXT NOT NULL UNIQUE,
            central_role TEXT NOT NULL, created_ts INTEGER NOT NULL,
            UNIQUE(school_id,email)
        )
    """)
    mapped = connection.execute(
        "SELECT local_username,central_role FROM main.central_user_map WHERE central_user_id=? AND school_id=?",
        (user_id, school_id)
    ).fetchone()
    if mapped:
        username = mapped["local_username"]
        connection.execute(
            "UPDATE main.admins SET role=?,active=1 WHERE username=? AND school_id=?",
            (local_role, username, school_id)
        )
        connection.execute(
            "UPDATE main.central_user_map SET email=?,central_role=? WHERE central_user_id=? AND school_id=?",
            (email, central_role, user_id, school_id)
        )
        connection.commit()
        return username
    # Stable synthetic local username avoids collisions where two schools share
    # an administrator email; central email remains the login identifier.
    digest = hashlib.sha256((school_id + "|" + user_id).encode("utf-8")).hexdigest()[:28]
    username = "vc_" + digest
    existing = connection.execute(
        "SELECT id FROM main.admins WHERE username=?", (username,)
    ).fetchone()
    if existing:
        raise RuntimeError("A local administrator identity collision needs administrator review.")
    unusable_local_password = generate_password_hash(secrets.token_urlsafe(48))
    cursor = connection.execute(
        "INSERT INTO main.admins(username,password_hash,role,active,school_id) VALUES(?,?,?,?,?)",
        (username, unusable_local_password, local_role, 1, school_id)
    )
    connection.execute(
        """INSERT INTO main.central_user_map
        (central_user_id,school_id,email,local_username,central_role,created_ts)
        VALUES(?,?,?,?,?,?)""",
        (user_id, school_id, email, username, central_role, int(time.time()))
    )
    connection.commit()
    return username


def central_logout(session_key, connection):
    if not session_key or connection is None:
        return
    digest = hashlib.sha256(str(session_key).encode("utf-8")).hexdigest()
    connection.execute("""
        CREATE TABLE IF NOT EXISTS central_sessions (
            session_key_hash TEXT PRIMARY KEY, session_token TEXT NOT NULL,
            expires_ts REAL NOT NULL, school_id TEXT NOT NULL,
            local_username TEXT NOT NULL, created_ts INTEGER NOT NULL
        )
    """)
    row = connection.execute(
        "SELECT session_token FROM main.central_sessions WHERE session_key_hash=?",
        (digest,)
    ).fetchone()
    if row:
        try:
            _post_action("logout", sessionToken=row["session_token"])
        except (RuntimeError, ValueError):
            # Local logout must still complete if the central service is unavailable.
            pass
        connection.execute("DELETE FROM main.central_sessions WHERE session_key_hash=?", (digest,))
        connection.commit()


def install_central_backend_routes(app, db, err):
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
            if status == 200 and result.get("ok") is False:
                status = 400
            return jsonify(result), status
        except (RuntimeError, ValueError) as exc:
            return err(str(exc), 503)

    @app.post("/api/central/activate")
    def vicora_central_activate():
        body = request.get_json(silent=True) or {}
        code = str(body.get("school_code") or "").strip().upper()
        email = str(body.get("email") or "").strip().lower()
        token = str(body.get("activation_token") or "")
        password = str(body.get("password") or "")
        if not code or not email or len(token) < 24 or len(password) < 12:
            return err("Enter the School Code, activation token, valid email and a password of at least 12 characters.")
        try:
            activated = _post_action(
                "activateSchool", activationToken=token, email=email, password=password
            )
            school = _school_from_central(code)
            connection = db()
            school_id = _ensure_local_school(connection, school)
            return jsonify(ok=True, activated=bool(activated.get("activated")),
                           school_code=school.get("schoolCode"),
                           message="School administrator activated. Sign in with the School Code, email and password.")
        except (RuntimeError, ValueError) as exc:
            return err(str(exc), 400)

    @app.post("/api/central/login")
    def vicora_central_login():
        body = request.get_json(silent=True) or {}
        code = str(body.get("school_code") or "").strip().upper()
        email = str(body.get("email") or "").strip().lower()
        password = str(body.get("password") or "")
        if not code or not email or not password:
            return err("Enter the School Code, email and password.")
        try:
            auth = _post_action("login", schoolCode=code, email=email, password=password)
            school = auth.get("school") or {}
            user = auth.get("user") or {}
            if str(school.get("schoolCode") or "").upper() != code:
                raise RuntimeError("The central login returned a different School Code.")
            connection = db()
            school_id = _ensure_local_school(connection, school)
            username = _ensure_local_admin(connection, school_id, user)
            expires_text = str(auth.get("expiresAt") or "")
            from datetime import datetime
            expires_ts = datetime.fromisoformat(expires_text.replace("Z", "+00:00")).timestamp()
            if expires_ts <= time.time():
                raise ValueError("The central login session has expired. Sign in again.")
            if not auth.get("sessionToken"):
                raise RuntimeError("VICORA Central did not return a secure session token.")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS central_sessions (
                    session_key_hash TEXT PRIMARY KEY, session_token TEXT NOT NULL,
                    expires_ts REAL NOT NULL, school_id TEXT NOT NULL,
                    local_username TEXT NOT NULL, created_ts INTEGER NOT NULL
                )
            """)
            session_key = secrets.token_urlsafe(40)
            connection.execute(
                """INSERT INTO main.central_sessions
                (session_key_hash,session_token,expires_ts,school_id,local_username,created_ts)
                VALUES(?,?,?,?,?,?)""",
                (hashlib.sha256(session_key.encode("utf-8")).hexdigest(),
                 auth["sessionToken"], expires_ts, school_id, username, int(time.time()))
            )
            connection.commit()
            session.clear()
            session.permanent = True
            session["admin"] = username
            session["school_id"] = school_id
            session["admin_role"] = ROLE_MAP[user.get("role")]
            session["central_session_key"] = session_key
            session["central_expires_ts"] = expires_ts
            return jsonify(ok=True, user=user.get("name") or email,
                           role=session["admin_role"], role_name="School Administrator" if session["admin_role"] == "super_admin" else session["admin_role"].replace("_", " ").title(),
                           school=school.get("name"), school_code=code,
                           expires_at=expires_text, central=True)
        except (RuntimeError, ValueError, TypeError, KeyError) as exc:
            return err(str(exc), 401)

    @app.post("/api/central/admin")
    def vicora_central_admin():
        if request.content_length and request.content_length > 64 * 1024:
            return err("The administrator request is too large.", 413)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return err("Send a valid JSON request.")
        action = str(body.get("action") or "")
        expected_platform_token = os.environ.get("VICORA_PLATFORM_ADMIN_TOKEN", "")
        supplied_platform_token = request.headers.get("X-VICORA-PLATFORM-TOKEN", "")
        if not (expected_platform_token and supplied_platform_token
                and hmac.compare_digest(expected_platform_token, supplied_platform_token)):
            return err("Platform Super Admin authorization required.", 401)
        admin_key = os.environ.get("VICORA_CENTRAL_ADMIN_KEY", "")
        if action not in ADMIN_ACTIONS:
            return err("This central administrator action is not available.", 403)
        if not admin_key:
            return err("Central administrator access is not configured on this server.", 503)
        forwarded = dict(body)
        forwarded["adminKey"] = admin_key
        try:
            result, status = _call(payload=forwarded)
            if status == 200 and result.get("ok") is False:
                status = 400
            return jsonify(result), status
        except (RuntimeError, ValueError) as exc:
            return err(str(exc), 503)
