"""VICORA central school registry, approval, activation and host enrollment.

This module deliberately fails closed: the legacy examination API is not made
available to a newly approved tenant until its routes have been tenant-scoped.
"""
import hashlib
import hmac
import os
import re
import secrets
import time
import uuid

from flask import jsonify, request, session
from werkzeug.security import generate_password_hash


def migrate_multi_tenant_schema(connection):
    c = connection
    c.executescript("""
    CREATE TABLE IF NOT EXISTS school_applications (
      id INTEGER PRIMARY KEY, school_name TEXT NOT NULL, contact_name TEXT NOT NULL,
      email TEXT NOT NULL, phone TEXT NOT NULL, country TEXT NOT NULL DEFAULT 'Nigeria',
      address TEXT DEFAULT '', website TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'pending',
      submitted_ts INTEGER NOT NULL, reviewed_ts INTEGER DEFAULT 0,
      reviewed_by TEXT DEFAULT '', review_note TEXT DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_school_applications_status
      ON school_applications(status, submitted_ts);
    CREATE TABLE IF NOT EXISTS school_admin_invites (
      id INTEGER PRIMARY KEY, school_id TEXT NOT NULL REFERENCES schools(school_id),
      token_hash TEXT NOT NULL UNIQUE, expires_ts INTEGER NOT NULL,
      created_ts INTEGER NOT NULL, used_ts INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS school_hosts (
      device_id TEXT PRIMARY KEY, school_id TEXT NOT NULL REFERENCES schools(school_id),
      platform TEXT NOT NULL, label TEXT DEFAULT '', token_hash TEXT NOT NULL UNIQUE,
      created_ts INTEGER NOT NULL, last_seen INTEGER DEFAULT 0, revoked_ts INTEGER DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_school_hosts_school
      ON school_hosts(school_id, revoked_ts);
    CREATE TABLE IF NOT EXISTS platform_audit (
      id INTEGER PRIMARY KEY, ts INTEGER NOT NULL, actor TEXT NOT NULL,
      action TEXT NOT NULL, application_id INTEGER, school_id TEXT
    );
    """)
    school_cols = {r[1] for r in c.execute("PRAGMA table_info(schools)")}
    additions = {
      "contact_email": "TEXT DEFAULT ''", "contact_phone": "TEXT DEFAULT ''",
      "country": "TEXT DEFAULT 'Nigeria'", "address": "TEXT DEFAULT ''",
      "website": "TEXT DEFAULT ''", "reviewed_by": "TEXT DEFAULT ''",
      "review_note": "TEXT DEFAULT ''"
    }
    for name, definition in additions.items():
        if name not in school_cols:
            c.execute(f"ALTER TABLE schools ADD COLUMN {name} {definition}")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_schools_code_upper ON schools(upper(school_code))")
    c.commit()


def _platform_authorized():
    expected = os.environ.get("VICORA_PLATFORM_ADMIN_TOKEN", "")
    supplied = request.headers.get("X-VICORA-PLATFORM-TOKEN", "")
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def _school_by_code(connection, code):
    value = str(code or "").strip().upper()
    if not value:
        rows = connection.execute(
            "SELECT * FROM schools WHERE status='approved' ORDER BY created_ts LIMIT 2"
        ).fetchall()
        return rows[0] if len(rows) == 1 else None
    return connection.execute(
        "SELECT * FROM schools WHERE upper(school_code)=? AND status='approved'",
        (value,)
    ).fetchone()


def school_context(connection, code):
    return _school_by_code(connection, code)


def _platform_log(connection, action, application_id=None, school_id=None):
    connection.execute(
        "INSERT INTO platform_audit(ts,actor,action,application_id,school_id) VALUES(?,?,?,?,?)",
        (int(time.time()), "platform_super_admin", action, application_id, school_id)
    )
    connection.commit()


def install_multi_tenant_routes(app, db, err):
    @app.get("/api/public/schools/resolve")
    def vicora_resolve_school():
        code = request.args.get("code", "")
        row = _school_by_code(db(), code)
        if not row:
            return err("School Code not found or the school is not approved.", 404)
        return jsonify(ok=True, school={
            "school_id": row["school_id"], "school_code": row["school_code"],
            "name": row["name"], "status": row["status"]
        })

    @app.post("/api/public/school-applications")
    def vicora_apply_school():
        d = request.get_json(silent=True) or {}
        name = str(d.get("school_name") or "").strip()
        contact = str(d.get("contact_name") or "").strip()
        email = str(d.get("email") or "").strip().lower()
        phone = str(d.get("phone") or "").strip()
        country = str(d.get("country") or "Nigeria").strip()[:80]
        address = str(d.get("address") or "").strip()[:300]
        website = str(d.get("website") or "").strip()[:200]
        if len(name) < 3 or len(contact) < 2:
            return err("Enter the school name and contact person's name.")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            return err("Enter a valid contact email address.")
        if len(phone) < 7 or len(phone) > 40:
            return err("Enter a valid contact phone number.")
        if db().execute(
            "SELECT 1 FROM school_applications WHERE lower(email)=? AND status='pending'",
            (email,)
        ).fetchone():
            return err("A pending application already uses this email.", 409)
        cur = db().execute(
            """INSERT INTO school_applications
            (school_name,contact_name,email,phone,country,address,website,status,submitted_ts)
            VALUES(?,?,?,?,?,?,?,'pending',?)""",
            (name[:120], contact[:120], email, phone, country, address, website, int(time.time()))
        )
        db().commit()
        return jsonify(ok=True, application_id=cur.lastrowid,
                       message="Application received. VICORA will review it before issuing a School Code."), 201

    @app.get("/api/platform/applications")
    def vicora_platform_applications():
        if not _platform_authorized():
            return err("Platform Super Admin authorization required.", 401)
        status = request.args.get("status", "pending")
        if status not in ("pending", "approved", "rejected", "all"):
            return err("Invalid application status.")
        sql = "SELECT id,school_name,contact_name,email,phone,country,address,website,status,submitted_ts,reviewed_ts,reviewed_by,review_note FROM school_applications"
        args = ()
        if status != "all":
            sql += " WHERE status=?"
            args = (status,)
        sql += " ORDER BY submitted_ts DESC LIMIT 500"
        return jsonify(applications=[dict(r) for r in db().execute(sql, args).fetchall()])

    @app.post("/api/platform/applications/<int:application_id>/decision")
    def vicora_platform_decide_application(application_id):
        if not _platform_authorized():
            return err("Platform Super Admin authorization required.", 401)
        d = request.get_json(silent=True) or {}
        decision = str(d.get("decision") or "").lower()
        note = str(d.get("note") or "").strip()[:2000]
        if decision not in ("approve", "reject"):
            return err("Decision must be approve or reject.")
        c = db()
        app_row = c.execute(
            "SELECT * FROM school_applications WHERE id=?", (application_id,)
        ).fetchone()
        if not app_row:
            return err("Application not found.", 404)
        if app_row["status"] != "pending":
            return err("This application has already been reviewed.", 409)
        now = int(time.time())
        if decision == "reject":
            c.execute(
                "UPDATE school_applications SET status='rejected',reviewed_ts=?,reviewed_by='platform_super_admin',review_note=? WHERE id=?",
                (now, note, application_id)
            )
            c.commit()
            _platform_log(c, "Rejected school application", application_id)
            return jsonify(ok=True, status="rejected")
        school_id = str(uuid.uuid4())
        for _ in range(10):
            school_code = "VIC-" + secrets.token_hex(4).upper()
            if not c.execute("SELECT 1 FROM schools WHERE upper(school_code)=?", (school_code,)).fetchone():
                break
        else:
            return err("Could not allocate a unique School Code. Try again.", 503)
        c.execute(
            """INSERT INTO schools
            (school_id,school_code,name,status,is_legacy_default,created_ts,approved_ts,
             contact_email,contact_phone,country,address,website,reviewed_by,review_note)
            VALUES(?,?,?,'approved',0,?,?,?,?,?,?,?,'platform_super_admin',?)""",
            (school_id, school_code, app_row["school_name"], now, now,
             app_row["email"], app_row["phone"], app_row["country"],
             app_row["address"], app_row["website"], note)
        )
        invite = secrets.token_urlsafe(32)
        c.execute(
            "INSERT INTO school_admin_invites(school_id,token_hash,expires_ts,created_ts) VALUES(?,?,?,?)",
            (school_id, hashlib.sha256(invite.encode()).hexdigest(), now + 7 * 86400, now)
        )
        c.execute(
            "UPDATE school_applications SET status='approved',reviewed_ts=?,reviewed_by='platform_super_admin',review_note=? WHERE id=?",
            (now, note, application_id)
        )
        c.commit()
        _platform_log(c, "Approved school and issued School Code " + school_code,
                      application_id, school_id)
        return jsonify(ok=True, school_id=school_id, school_code=school_code,
                       activation_token=invite, activation_expires_ts=now + 7 * 86400,
                       message="Save the activation token securely; it is shown only once.")

    @app.post("/api/public/school-activation")
    def vicora_activate_school():
        d = request.get_json(silent=True) or {}
        code = str(d.get("school_code") or "").strip().upper()
        token = str(d.get("activation_token") or "")
        username = str(d.get("username") or "").strip()
        password = str(d.get("password") or "")
        if not re.fullmatch(r"[A-Za-z0-9_.@-]{3,80}", username):
            return err("Username must be 3-80 characters and use letters, numbers, dot, underscore, @ or hyphen.")
        if len(password) < 12:
            return err("Choose a password with at least 12 characters.")
        if len(token) < 32:
            return err("A valid activation token is required.", 401)
        c = db()
        school = _school_by_code(c, code)
        if not school:
            return err("School Code not found or not approved.", 404)
        digest = hashlib.sha256(token.encode()).hexdigest()
        invite = c.execute(
            """SELECT id FROM school_admin_invites
               WHERE school_id=? AND token_hash=? AND used_ts=0 AND expires_ts>?""",
            (school["school_id"], digest, int(time.time()))
        ).fetchone()
        if not invite:
            return err("Activation token is invalid, expired or already used.", 401)
        if c.execute(
            "SELECT 1 FROM admins WHERE school_id=? AND lower(username)=lower(?)",
            (school["school_id"], username)
        ).fetchone():
            return err("That username is already used in this school.", 409)
        c.execute(
            "INSERT INTO admins(username,password_hash,role,active,school_id) VALUES(?,?, 'super_admin',1,?)",
            (username, generate_password_hash(password), school["school_id"])
        )
        c.execute("UPDATE school_admin_invites SET used_ts=? WHERE id=?",
                  (int(time.time()), invite["id"]))
        c.commit()
        return jsonify(ok=True, message="School administrator activated. Sign in using your School Code.")

    @app.post("/api/admin/hosts/enroll")
    def vicora_enroll_host():
        school_id = session.get("school_id")
        username = session.get("admin")
        if not school_id or not username:
            return err("School administrator login required.", 401)
        staff = db().execute(
            "SELECT role,active FROM admins WHERE username=? AND school_id=?",
            (username, school_id)
        ).fetchone()
        if not staff or not staff["active"] or staff["role"] != "super_admin":
            return err("Only an active School Super Admin can enroll a host.", 403)
        d = request.get_json(silent=True) or {}
        device_id = str(d.get("device_id") or "").strip()
        platform = str(d.get("platform") or "").lower()
        label = str(d.get("label") or "").strip()[:120]
        if not re.fullmatch(r"[A-Za-z0-9._:-]{8,100}", device_id):
            return err("A stable device ID (8-100 safe characters) is required.")
        if platform not in ("android", "windows", "web"):
            return err("Host platform must be Android, Windows or Web.")
        token = secrets.token_urlsafe(40)
        db().execute(
            """INSERT INTO school_hosts(device_id,school_id,platform,label,token_hash,created_ts)
               VALUES(?,?,?,?,?,?) ON CONFLICT(device_id) DO UPDATE SET
               school_id=excluded.school_id,platform=excluded.platform,label=excluded.label,
               token_hash=excluded.token_hash,created_ts=excluded.created_ts,
               last_seen=0,revoked_ts=0""",
            (device_id, school_id, platform, label,
             hashlib.sha256(token.encode()).hexdigest(), int(time.time()))
        )
        db().commit()
        return jsonify(ok=True, device_id=device_id, host_token=token,
                       message="Store this host token securely. It will not be shown again.")

    @app.post("/api/host/heartbeat")
    def vicora_host_heartbeat():
        token = request.headers.get("X-VICORA-HOST-TOKEN", "")
        if len(token) < 32:
            return err("Host authorization required.", 401)
        digest = hashlib.sha256(token.encode()).hexdigest()
        row = db().execute(
            """SELECT h.device_id,h.school_id,h.platform,s.name,s.school_code
               FROM school_hosts h JOIN schools s ON s.school_id=h.school_id
               WHERE h.token_hash=? AND h.revoked_ts=0 AND s.status='approved'""",
            (digest,)
        ).fetchone()
        if not row:
            return err("Host token is invalid or revoked.", 401)
        db().execute("UPDATE school_hosts SET last_seen=? WHERE device_id=?",
                     (int(time.time()), row["device_id"]))
        db().commit()
        return jsonify(ok=True, device_id=row["device_id"], school_id=row["school_id"],
                       school_code=row["school_code"], school_name=row["name"],
                       platform=row["platform"])

    @app.get("/api/admin/hosts")
    def vicora_list_hosts():
        school_id = session.get("school_id")
        username = session.get("admin")
        if not school_id or not username:
            return err("School administrator login required.", 401)
        staff = db().execute(
            "SELECT role,active FROM admins WHERE username=? AND school_id=?",
            (username, school_id)
        ).fetchone()
        if not staff or not staff["active"] or staff["role"] != "super_admin":
            return err("Only an active School Super Admin can view enrolled hosts.", 403)
        rows = db().execute(
            """SELECT device_id,platform,label,created_ts,last_seen,revoked_ts
               FROM school_hosts WHERE school_id=? ORDER BY created_ts DESC""",
            (school_id,)
        ).fetchall()
        return jsonify(hosts=[dict(r) for r in rows])

    @app.post("/api/admin/hosts/<device_id>/revoke")
    def vicora_revoke_host(device_id):
        school_id = session.get("school_id")
        username = session.get("admin")
        if not school_id or not username:
            return err("School administrator login required.", 401)
        staff = db().execute(
            "SELECT role,active FROM admins WHERE username=? AND school_id=?",
            (username, school_id)
        ).fetchone()
        if not staff or not staff["active"] or staff["role"] != "super_admin":
            return err("Only an active School Super Admin can revoke a host.", 403)
        cur = db().execute(
            "UPDATE school_hosts SET revoked_ts=? WHERE device_id=? AND school_id=? AND revoked_ts=0",
            (int(time.time()), device_id, school_id)
        )
        db().commit()
        if not cur.rowcount:
            return err("Host not found or already revoked.", 404)
        return jsonify(ok=True)
