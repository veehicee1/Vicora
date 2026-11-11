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

    def test_admin_status_includes_review_details_for_dashboard(self):
        response = self.client.get("/api/admin/android-host/status")
        self.assertEqual(response.status_code, 200, response.get_json())
        row = next(x for x in response.get_json()["conflicts"] if x["attempt_uuid"] == self.attempt_uuid)
        self.assertIn("review_note", row)
        self.assertIn("reviewed_by", row)
        self.assertIn("reviewed_ts", row)


if __name__ == "__main__":
    unittest.main()
