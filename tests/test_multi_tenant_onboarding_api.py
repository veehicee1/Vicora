import hashlib
import os
import sqlite3
import unittest
from unittest.mock import patch

from flask import Flask
from multi_tenant import install_multi_tenant_routes, migrate_multi_tenant_schema


class MultiTenantOnboardingApiTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript("""
            CREATE TABLE schools(
              school_id TEXT PRIMARY KEY, school_code TEXT NOT NULL UNIQUE,
              name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'approved',
              is_legacy_default INTEGER NOT NULL DEFAULT 0,
              created_ts INTEGER NOT NULL DEFAULT 0, approved_ts INTEGER);
            INSERT INTO schools VALUES('legacy','VIC-LEGACY','Legacy School','approved',1,1,1);
            CREATE TABLE admins(
              id INTEGER PRIMARY KEY, username TEXT NOT NULL, password_hash TEXT NOT NULL,
              role TEXT NOT NULL DEFAULT 'super_admin', active INTEGER NOT NULL DEFAULT 1,
              school_id TEXT NOT NULL);
            CREATE UNIQUE INDEX ux_admins_school_username
              ON admins(school_id, username);
        """)
        migrate_multi_tenant_schema(self.conn)
        self.app = Flask(__name__)
        self.app.secret_key = "test-only-secret"
        self.app.testing = True
        install_multi_tenant_routes(self.app, lambda: self.conn,
                                    lambda message, code=400: (__import__("flask").jsonify(error=message), code))
        self.client = self.app.test_client()

    def tearDown(self):
        self.conn.close()

    def test_application_requires_valid_contact_and_is_pending(self):
        response = self.client.post("/api/public/school-applications", json={
            "school_name": "Second School", "contact_name": "Admin",
            "email": "bad-email", "phone": "08012345678"
        })
        self.assertEqual(response.status_code, 400)
        response = self.client.post("/api/public/school-applications", json={
            "school_name": "Second School", "contact_name": "Admin",
            "email": "admin@second.example", "phone": "08012345678"
        })
        self.assertEqual(response.status_code, 201)
        row = self.conn.execute("SELECT status FROM school_applications").fetchone()
        self.assertEqual(row["status"], "pending")

    def test_platform_review_approval_and_one_time_activation(self):
        application = self.client.post("/api/public/school-applications", json={
            "school_name": "Second School", "contact_name": "Admin",
            "email": "admin@second.example", "phone": "08012345678"
        }).get_json()
        self.assertEqual(self.client.get("/api/platform/applications").status_code, 401)
        with patch.dict(os.environ, {"VICORA_PLATFORM_ADMIN_TOKEN": "test-platform-secret"}):
            response = self.client.post(
                f"/api/platform/applications/{application['application_id']}/decision",
                headers={"X-VICORA-PLATFORM-TOKEN": "test-platform-secret"},
                json={"decision": "approve"}
            )
        self.assertEqual(response.status_code, 200)
        approved = response.get_json()
        self.assertRegex(approved["school_code"], r"^VIC-[A-F0-9]{8}$")
        self.assertEqual(self.client.get(
            "/api/public/schools/resolve?code=" + approved["school_code"]
        ).status_code, 200)
        activated = self.client.post("/api/public/school-activation", json={
            "school_code": approved["school_code"],
            "activation_token": approved["activation_token"],
            "username": "principal",
            "password": "A-strong-password-2026!"
        })
        self.assertEqual(activated.status_code, 200)
        admin = self.conn.execute(
            "SELECT username,school_id FROM admins WHERE username='principal'"
        ).fetchone()
        self.assertEqual(admin["school_id"], approved["school_id"])
        self.assertNotEqual(
            self.conn.execute("SELECT token_hash FROM school_admin_invites").fetchone()[0],
            approved["activation_token"]
        )
        replay = self.client.post("/api/public/school-activation", json={
            "school_code": approved["school_code"],
            "activation_token": approved["activation_token"],
            "username": "otheradmin",
            "password": "Another-strong-password-2026!"
        })
        self.assertEqual(replay.status_code, 401)

    def test_host_token_is_school_scoped_and_revocable(self):
        self.conn.execute(
            "INSERT INTO admins(username,password_hash,role,active,school_id) VALUES('owner','x','super_admin',1,'legacy')"
        )
        self.conn.commit()
        with self.client.session_transaction() as state:
            state["admin"] = "owner"
            state["school_id"] = "legacy"
        enrolled = self.client.post("/api/admin/hosts/enroll", json={
            "device_id": "android-device-0001", "platform": "android", "label": "School phone"
        })
        self.assertEqual(enrolled.status_code, 200)
        token = enrolled.get_json()["host_token"]
        stored = self.conn.execute("SELECT token_hash FROM school_hosts").fetchone()[0]
        self.assertEqual(stored, hashlib.sha256(token.encode()).hexdigest())
        beat = self.client.post("/api/host/heartbeat",
            headers={"X-VICORA-HOST-TOKEN": token})
        self.assertEqual(beat.status_code, 200)
        self.assertEqual(beat.get_json()["school_code"], "VIC-LEGACY")
        revoked = self.client.post("/api/admin/hosts/android-device-0001/revoke")
        self.assertEqual(revoked.status_code, 200)
        self.assertEqual(self.client.post("/api/host/heartbeat",
            headers={"X-VICORA-HOST-TOKEN": token}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
