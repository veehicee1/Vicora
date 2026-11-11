"""Admin controls for paired Android Hosts and sync-conflict review."""
import os
import tempfile
import unittest
import uuid

os.environ.setdefault("CBT_DATA", tempfile.mkdtemp(prefix="vicora-android-admin-tests-"))

from app import app, ex, q1  # noqa: E402


class AndroidHostAdminTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()
        self.attempt_uuid = str(uuid.uuid4())
        with app.app_context():
            ex("UPDATE admins SET role='super_admin', active=1 WHERE username='admin'")
            ex("DELETE FROM android_sync_conflicts WHERE attempt_uuid=?", (self.attempt_uuid,))
            ex(
                """INSERT INTO android_sync_conflicts
                   (attempt_uuid,device_id,exam_sync_uuid,student_sync_uuid,reason,payload,created_ts)
                   VALUES(?,?,?,?,?,?,?)""",
                (self.attempt_uuid, str(uuid.uuid4()), "exam-uuid", "student-uuid",
                 "Exam revision mismatch", "{}", 1234567890),
            )
        with self.client.session_transaction() as sess:
            sess["admin"] = "admin"

    def tearDown(self):
        with app.app_context():
            ex("DELETE FROM android_sync_conflicts WHERE attempt_uuid=?", (self.attempt_uuid,))

    def test_admin_can_save_conflict_review_state_and_note(self):
        with app.app_context():
            row = q1("SELECT id FROM android_sync_conflicts WHERE attempt_uuid=?", (self.attempt_uuid,))
        response = self.client.post(
            f"/api/admin/android-host/conflicts/{row['id']}/review",
            json={"review_state": "Needs follow-up", "review_note": "Check the matching exam package."},
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        with app.app_context():
            saved = q1(
                "SELECT review_state,review_note,reviewed_by,reviewed_ts FROM android_sync_conflicts WHERE id=?",
                (row["id"],),
            )
        self.assertEqual(saved["review_state"], "Needs follow-up")
        self.assertEqual(saved["review_note"], "Check the matching exam package.")
        self.assertEqual(saved["reviewed_by"], "admin")
        self.assertGreater(saved["reviewed_ts"], 0)

    def test_pairing_code_is_one_time_and_device_can_be_revoked(self):
        generated = self.client.post("/api/admin/android-host/pairing-code")
        self.assertEqual(generated.status_code, 200, generated.get_json())
        code = generated.get_json()["pairing_code"]
        device_id = str(uuid.uuid4())
        paired = self.client.post(
            "/api/android-host/pair",
            base_url="https://school.example",
            json={"pairing_code": code, "device_id": device_id, "label": "VICORA Test Android"},
        )
        self.assertEqual(paired.status_code, 200, paired.get_json())
        token = paired.get_json()["device_token"]
        self.assertGreaterEqual(len(token), 32)
        with app.app_context():
            device = q1("SELECT token_hash,revoked_ts FROM android_host_devices WHERE device_id=?", (device_id,))
        import hashlib
        self.assertNotEqual(device["token_hash"], token)
        self.assertEqual(device["token_hash"], hashlib.sha256(token.encode("utf-8")).hexdigest())
        self.assertEqual(device["revoked_ts"], 0)

        reused = self.client.post(
            "/api/android-host/pair",
            base_url="https://school.example",
            json={"pairing_code": code, "device_id": device_id, "label": "VICORA Test Android"},
        )
        self.assertEqual(reused.status_code, 401)

        revoked = self.client.post(f"/api/admin/android-host/devices/{device_id}/revoke")
        self.assertEqual(revoked.status_code, 200, revoked.get_json())
        with app.app_context():
            device = q1("SELECT revoked_ts FROM android_host_devices WHERE device_id=?", (device_id,))
        self.assertGreater(device["revoked_ts"], 0)
        with app.app_context():
            ex("DELETE FROM android_host_devices WHERE device_id=?", (device_id,))

    def test_remote_http_pairing_is_rejected(self):
        generated = self.client.post("/api/admin/android-host/pairing-code")
        self.assertEqual(generated.status_code, 200, generated.get_json())
        response = self.client.post(
            "/api/android-host/pair",
            json={"pairing_code": generated.get_json()["pairing_code"], "device_id": str(uuid.uuid4())},
            environ_overrides={"REMOTE_ADDR": "192.168.1.50"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("HTTPS", response.get_json()["error"])

    def test_admin_status_includes_review_details_for_dashboard(self):
        response = self.client.get("/api/admin/android-host/status")
        self.assertEqual(response.status_code, 200, response.get_json())
        row = next(x for x in response.get_json()["conflicts"] if x["attempt_uuid"] == self.attempt_uuid)
        self.assertIn("review_note", row)
        self.assertIn("reviewed_by", row)
        self.assertIn("reviewed_ts", row)


if __name__ == "__main__":
    unittest.main()
