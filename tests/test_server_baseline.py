"""Small regression tests for the GTMC central-server safety baseline."""
import os
import tempfile
import unittest
import subprocess
import sys

# Keep test data out of the checkout and out of any real school database.
os.environ["CBT_DATA"] = tempfile.mkdtemp(prefix="gtmc-cbt-tests-")

from app import app  # noqa: E402
from desktop_connection import _config_path, validate_server_url  # noqa: E402


class ServerBaselineTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = app.test_client()



    def test_remote_student_only_mode_hides_admin_surface(self):
        from unittest.mock import patch
        with patch("app.REMOTE_STUDENT_ONLY", True):
            blocked = self.client.get(
                "/admin",
                environ_overrides={"REMOTE_ADDR": "198.51.100.25"},
            )
            allowed = self.client.get(
                "/home/",
                environ_overrides={"REMOTE_ADDR": "198.51.100.25"},
            )
        self.assertEqual(blocked.status_code, 404)
        self.assertEqual(allowed.status_code, 200)

    def test_remote_student_only_mode_does_not_block_loopback_admin_page(self):
        from unittest.mock import patch
        with patch("app.REMOTE_STUDENT_ONLY", True):
            response = self.client.get(
                "/admin",
                environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
            )
        self.assertEqual(response.status_code, 200)

    def test_android_host_student_surface_keeps_student_entry_and_blocks_admin(self):
        from unittest.mock import patch
        with patch.dict(os.environ, {"CBT_REMOTE_STUDENT_ONLY": "1"}):
            student = self.client.get(
                "/",
                environ_overrides={"REMOTE_ADDR": "192.0.2.40"},
            )
            admin_page = self.client.get(
                "/admin",
                environ_overrides={"REMOTE_ADDR": "192.0.2.40"},
            )
            admin_api = self.client.get(
                "/api/admin/dashboard",
                environ_overrides={"REMOTE_ADDR": "192.0.2.40"},
            )
        self.assertEqual(student.status_code, 200)
        self.assertEqual(admin_page.status_code, 404)
        self.assertEqual(admin_api.status_code, 404)

    def test_android_student_only_host_can_initialize_without_trusted_proxy(self):
        env = os.environ.copy()
        env.update({
            "CBT_REMOTE_STUDENT_ONLY": "1",
            "CBT_TRUST_PROXY": "0",
            "CBT_HOST": "0.0.0.0",
            "CBT_DATA": tempfile.mkdtemp(prefix="gtmc-android-host-init-"),
        })
        result = subprocess.run(
            [sys.executable, "-c", "import app; assert app.SERVER_HOST == '0.0.0.0'"],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_home_exam_page_is_an_additional_entry_point(self):
        home = self.client.get("/home/")
        root = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertEqual(root.status_code, 200)
        self.assertIn(b"Registration number", home.data)
        self.assertIn(b"Registration number", root.data)

    def test_home_pwa_manifest_is_valid_json(self):
        response = self.client.get("/home/manifest.webmanifest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/manifest+json")
        manifest = response.get_json()
        self.assertEqual(manifest["start_url"], "/home/")
        self.assertEqual(manifest["scope"], "/home/")

    def test_home_service_worker_is_scoped_and_not_cacheable(self):
        response = self.client.get("/home/sw.js")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Service-Worker-Allowed"), "/home/")
        self.assertEqual(response.headers.get("Cache-Control"), "no-cache")
        self.assertIn(b"startsWith('/api/')", response.data)
        self.assertIn(b"network-only", response.data)

    def test_admin_and_exam_preferences_are_separate(self):
        self.assertNotEqual(_config_path("admin"), _config_path("exam"))

    def test_private_lan_http_address_is_allowed(self):
        self.assertEqual(
            validate_server_url("http://192.168.1.25:8000"),
            "http://192.168.1.25:8000/",
        )

    def test_public_remote_http_address_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "must use HTTPS"):
            validate_server_url("http://cbt.example.com")

    def test_public_remote_https_address_is_allowed(self):
        self.assertEqual(
            validate_server_url("https://cbt.example.com"),
            "https://cbt.example.com/",
        )

    def test_health_endpoint_is_ready_and_minimal(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["database"], "ready")
        self.assertNotIn("students", payload)
        self.assertNotIn("database_path", payload)

    def test_admin_api_requires_login(self):
        response = self.client.get("/api/admin/dashboard")
        self.assertEqual(response.status_code, 401)

    def test_remote_admin_is_blocked_by_default(self):
        with self.client.session_transaction() as sess:
            sess["admin"] = "admin"
        response = self.client.get(
            "/api/admin/dashboard",
            environ_overrides={"REMOTE_ADDR": "192.0.2.25"},
        )
        self.assertEqual(response.status_code, 403)

    def test_remote_admin_cannot_be_enabled_without_https_proxy(self):
        with self.client.session_transaction() as sess:
            sess["admin"] = "admin"
        response = self.client.post(
            "/api/admin/settings",
            json={"school_name": "GTMC", "allow_remote_admin": True},
            environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("HTTPS reverse-proxy", response.get_json()["error"])

    def test_loopback_admin_can_reach_dashboard_after_login(self):
        with self.client.session_transaction() as sess:
            sess["admin"] = "admin"
        response = self.client.get(
            "/api/admin/dashboard",
            environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
        )
        self.assertEqual(response.status_code, 200)


    def _proctor_fixture(self, policy="required"):
        import app as cbt
        c = cbt.raw()
        suffix = str(__import__("time").time_ns())
        c.execute("INSERT INTO classes(name) VALUES(?)", ("Proctor Test Class " + suffix,))
        class_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.execute("INSERT INTO subjects(name) VALUES(?)", ("Proctor Test Subject " + suffix,))
        subject_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.execute("INSERT INTO students(reg_no,name,class_id,access_code) VALUES(?,?,?,?)",
                  ("PT" + suffix, "Proctor Test Student", class_id, "ABC123"))
        student_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.execute("""INSERT INTO questions(subject_id,text,a,b,c,d,answer,marks)
                     VALUES(?,?,?,?,?,?,?,?)""",
                  (subject_id, "Test question " + suffix, "A", "B", "C", "D", "A", 1))
        c.execute("""INSERT INTO exams(title,subject_id,duration_min,num_questions,status,
                     created_ts,objective_count,theory_count,camera_policy)
                     VALUES(?,?,?,?,?,?,?,?,?)""",
                  ("Proctor Test Exam " + suffix, subject_id, 20, 1, "live",
                   int(__import__("time").time()), 1, 0, policy))
        exam_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.execute("INSERT INTO exam_classes(exam_id,class_id) VALUES(?,?)", (exam_id, class_id))
        c.commit()
        c.close()
        return {"exam_id": exam_id, "student_id": student_id, "reg_no": "PT" + suffix}

    def test_required_proctor_policy_is_enforced_by_begin_api(self):
        fixture = self._proctor_fixture("required")
        credentials = {"reg_no": fixture["reg_no"], "code": "ABC123",
                       "exam_id": fixture["exam_id"], "device": "test-browser"}
        blocked = self.client.post("/api/student/begin", json=credentials)
        self.assertEqual(blocked.status_code, 403)
        self.assertIn("requires camera permission", blocked.get_json()["error"])
        allowed = self.client.post("/api/student/begin",
                                   json={**credentials, "camera_preflight": True})
        self.assertEqual(allowed.status_code, 200)
        self.assertTrue(allowed.get_json().get("token"))

    def test_proctor_events_are_idempotent_and_admin_reviewable(self):
        fixture = self._proctor_fixture("optional")
        begun = self.client.post("/api/student/begin", json={
            "reg_no": fixture["reg_no"], "code": "ABC123",
            "exam_id": fixture["exam_id"], "device": "test-browser"})
        token = begun.get_json()["token"]
        event = {"request_id": "same-event-id", "event_type": "camera_started",
                 "client_ts": 1000, "details": {"camera_ready": True}}
        headers = {"X-Token": token}
        first = self.client.post("/api/student/proctor-event", json=event, headers=headers)
        second = self.client.post("/api/student/proctor-event", json=event, headers=headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        import app as cbt
        c = cbt.raw()
        count = c.execute("SELECT COUNT(*) FROM proctor_events WHERE session_id=("
                          "SELECT id FROM sessions WHERE token=?)", (token,)).fetchone()[0]
        c.close()
        self.assertEqual(count, 1)
        with self.client.session_transaction() as sess:
            sess["admin"] = "proctor-reviewer"
        listing = self.client.get(f"/api/admin/proctor/{fixture['exam_id']}")
        self.assertEqual(listing.status_code, 200)
        event_id = listing.get_json()["rows"][0]["id"]
        reviewed = self.client.post(f"/api/admin/proctor/events/{event_id}/review",
                                    json={"review_state": "Needs follow-up",
                                          "review_note": "Check the interruption."})
        self.assertEqual(reviewed.status_code, 200)
        updated = self.client.get(f"/api/admin/proctor/{fixture['exam_id']}")
        self.assertEqual(updated.get_json()["rows"][0]["review_state"], "Needs follow-up")

    def test_proctor_events_are_rejected_when_policy_is_off(self):
        fixture = self._proctor_fixture("off")
        begun = self.client.post("/api/student/begin", json={
            "reg_no": fixture["reg_no"], "code": "ABC123",
            "exam_id": fixture["exam_id"], "device": "test-browser"})
        token = begun.get_json()["token"]
        response = self.client.post("/api/student/proctor-event",
                                    json={"request_id": "off-event", "event_type": "camera_started"},
                                    headers={"X-Token": token})
        self.assertEqual(response.status_code, 409)


    def test_android_host_package_export_and_import_are_repeatable(self):
        fixture = self._proctor_fixture("optional")
        with self.client.session_transaction() as sess:
            sess["admin"] = "admin"
        exported = self.client.get(f"/api/admin/remote-host/package/{fixture['exam_id']}")
        self.assertEqual(exported.status_code, 200)
        self.assertIn("attachment", exported.headers.get("Content-Disposition", ""))
        package = exported.get_json()
        self.assertEqual(package["schema_version"], 1)
        self.assertTrue(package["exam"]["sync_uuid"])
        self.assertTrue(package["students"][0]["sync_uuid"])
        self.assertTrue(package["questions"][0]["sync_uuid"])
        self.assertEqual(package["exam"]["camera_policy"], "optional")
        imported = self.client.post("/api/admin/remote-host/package/import", json=package)
        self.assertEqual(imported.status_code, 200, imported.get_json())
        self.assertEqual(imported.get_json()["status"], "draft")
        repeated = self.client.post("/api/admin/remote-host/package/import", json=package)
        self.assertEqual(repeated.status_code, 200, repeated.get_json())
        import app as cbt
        c = cbt.raw()
        exam = c.execute("SELECT status,camera_policy FROM exams WHERE id=?",
                         (fixture["exam_id"],)).fetchone()
        students = c.execute("SELECT COUNT(*) FROM students WHERE reg_no=?",
                             (fixture["reg_no"],)).fetchone()[0]
        c.close()
        self.assertEqual(exam["status"], "draft")
        self.assertEqual(exam["camera_policy"], "optional")
        self.assertEqual(students, 1)

    def test_android_host_package_export_requires_admin_login(self):
        fixture = self._proctor_fixture("off")
        response = self.client.get(f"/api/admin/remote-host/package/{fixture['exam_id']}")
        self.assertEqual(response.status_code, 401)


    def test_android_host_pairing_code_is_one_time_and_token_is_hashed(self):
        import hashlib
        import uuid
        with self.client.session_transaction() as sess:
            sess["admin"] = "admin"
        generated = self.client.post("/api/admin/android-host/pairing-code")
        self.assertEqual(generated.status_code, 200, generated.get_json())
        code = generated.get_json()["pairing_code"]
        device_id = str(uuid.uuid4())
        paired = self.client.post("/api/android-host/pair", json={
            "pairing_code": code, "device_id": device_id, "label": "GTMC Test Phone"
        }, environ_overrides={"wsgi.url_scheme": "https"})
        self.assertEqual(paired.status_code, 200, paired.get_json())
        token = paired.get_json()["device_token"]
        import app as cbt
        with cbt.app.app_context():
            row = cbt.q1("select token_hash from android_host_devices where device_id=?", (device_id,))
        self.assertEqual(row["token_hash"], hashlib.sha256(token.encode()).hexdigest())
        self.assertNotEqual(row["token_hash"], token)
        second = self.client.post("/api/android-host/pair", json={
            "pairing_code": code, "device_id": str(uuid.uuid4())
        }, environ_overrides={"wsgi.url_scheme": "https"})
        self.assertEqual(second.status_code, 401)

    def test_android_host_sync_rejects_unpaired_device(self):
        response = self.client.post("/api/android-host/sync-results", json={
            "device_id": "not-a-device", "attempt_uuid": "00000000-0000-4000-8000-000000000001"
        })
        self.assertEqual(response.status_code, 401)

    def test_android_host_sync_status_requires_admin(self):
        response = self.client.get("/api/admin/android-host/status")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
