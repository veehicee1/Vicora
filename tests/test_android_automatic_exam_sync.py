"""Automatic Android Host exam-package sync and import safety tests."""
import hashlib
import os
import tempfile
import unittest
import uuid
import sys

ANDROID_PYTHON = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "android", "app", "src", "main", "python"))
if ANDROID_PYTHON not in sys.path:
    sys.path.insert(0, ANDROID_PYTHON)

os.environ.setdefault("CBT_DATA", tempfile.mkdtemp(prefix="vicora-android-auto-sync-tests-"))

import app as cbt  # noqa: E402
import android_sync  # noqa: E402


class AndroidAutomaticExamSyncTests(unittest.TestCase):
    def setUp(self):
        cbt.app.config.update(TESTING=True)
        self.client = cbt.app.test_client()
        self.suffix = uuid.uuid4().hex[:10]
        self.device_id = str(uuid.uuid4())
        self.device_token = "device-token-" + uuid.uuid4().hex
        with cbt.app.app_context():
            cbt.ex("UPDATE admins SET role='super_admin',active=1 WHERE username='admin'")
            cbt.setset("school_name", "Automatic Sync Test School")
            self.class_id = cbt.ex("INSERT INTO classes(name) VALUES(?)", ("Auto Sync Class " + self.suffix,)).lastrowid
            self.subject_id = cbt.ex("INSERT INTO subjects(name) VALUES(?)", ("Auto Sync Subject " + self.suffix,)).lastrowid
            self.student_id = cbt.ex(
                "INSERT INTO students(reg_no,name,class_id,access_code) VALUES(?,?,?,?)",
                ("AS" + self.suffix, "Auto Sync Candidate", self.class_id, "PIN123"),
            ).lastrowid
            cbt.ex(
                """INSERT INTO questions(subject_id,text,a,b,c,d,answer,marks,question_type)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (self.subject_id, "Auto sync question " + self.suffix, "A", "B", "C", "D", "A", 1, "objective"),
            )
            self.exam_id = cbt.ex(
                """INSERT INTO exams(title,subject_id,duration_min,num_questions,status,created_ts,
                   objective_count,android_host_sync_enabled) VALUES(?,?,?,?,?,?,?,1)""",
                ("Auto Sync Exam " + self.suffix, self.subject_id, 30, 1, "draft", 1, 1),
            ).lastrowid
            cbt.ex("INSERT INTO exam_classes(exam_id,class_id) VALUES(?,?)", (self.exam_id, self.class_id))
            cbt.ex(
                """INSERT INTO android_host_devices(device_id,token_hash,label,created_ts,last_seen,revoked_ts)
                   VALUES(?,?,?,?,?,0)""",
                (self.device_id, hashlib.sha256(self.device_token.encode()).hexdigest(),
                 "Automated Android", 1, 1),
            )
            self.package = cbt._build_android_host_package(self.exam_id)
        with self.client.session_transaction() as sess:
            sess["admin"] = "admin"

    def tearDown(self):
        with cbt.app.app_context():
            cbt.ex("DELETE FROM android_host_devices WHERE device_id=?", (self.device_id,))
            cbt.setset("school_name", "")
            cbt.ex("DELETE FROM sessions WHERE exam_id=?", (self.exam_id,))
            cbt.ex("DELETE FROM exams WHERE id=?", (self.exam_id,))
            cbt.ex("DELETE FROM questions WHERE subject_id=?", (self.subject_id,))
            cbt.ex("DELETE FROM students WHERE id=?", (self.student_id,))
            cbt.ex("DELETE FROM subjects WHERE id=?", (self.subject_id,))
            cbt.ex("DELETE FROM classes WHERE id=?", (self.class_id,))

    def test_paired_host_pulls_only_enabled_exams_and_skips_known_revision(self):
        response = self.client.post(
            "/api/android-host/sync-pull",
            base_url="https://school.example",
            json={"device_id": self.device_id, "known_revisions": {}},
            headers={"Authorization": "Bearer " + self.device_token},
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        payload = response.get_json()
        self.assertEqual(len(payload["packages"]), 1)
        self.assertFalse(payload["more_available"])
        package = payload["packages"][0]
        self.assertEqual(package["exam"]["sync_uuid"], self.package["exam"]["sync_uuid"])
        self.assertRegex(package["roster_revision_hash"], r"^[a-f0-9]{64}$")
        known = {package["exam"]["sync_uuid"]:
                 package["exam"]["sync_revision_hash"] + "." + package["roster_revision_hash"]}
        again = self.client.post(
            "/api/android-host/sync-pull",
            base_url="https://school.example",
            json={"device_id": self.device_id, "known_revisions": known},
            headers={"Authorization": "Bearer " + self.device_token},
        )
        self.assertEqual(again.status_code, 200, again.get_json())
        self.assertEqual(again.get_json()["packages"], [])

    def test_sync_pull_returns_multiple_enabled_exam_packages_in_one_cycle(self):
        with cbt.app.app_context():
            second_subject_id = cbt.ex(
                "INSERT INTO subjects(name) VALUES(?)", ("Second Sync Subject " + self.suffix,)
            ).lastrowid
            cbt.ex(
                """INSERT INTO questions(subject_id,text,a,b,c,d,answer,marks,question_type)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (second_subject_id, "Second sync question " + self.suffix,
                 "A", "B", "C", "D", "B", 1, "objective"),
            )
            second_exam_id = cbt.ex(
                """INSERT INTO exams(title,subject_id,duration_min,num_questions,status,created_ts,
                   objective_count,android_host_sync_enabled) VALUES(?,?,?,?,?,?,?,1)""",
                ("Second Auto Sync Exam " + self.suffix, second_subject_id, 30, 1, "draft", 1, 1),
            ).lastrowid
            cbt.ex("INSERT INTO exam_classes(exam_id,class_id) VALUES(?,?)",
                   (second_exam_id, self.class_id))
        try:
            response = self.client.post(
                "/api/android-host/sync-pull",
                base_url="https://school.example",
                json={"device_id": self.device_id, "known_revisions": {}},
                headers={"Authorization": "Bearer " + self.device_token},
            )
            self.assertEqual(response.status_code, 200, response.get_json())
            payload = response.get_json()
            self.assertEqual(len(payload["packages"]), 2)
            self.assertFalse(payload["more_available"])
            self.assertEqual(
                {item["exam"]["sync_uuid"] for item in payload["packages"]},
                {self.package["exam"]["sync_uuid"],
                 cbt.q1("SELECT sync_uuid FROM exams WHERE id=?", (second_exam_id,))["sync_uuid"]},
            )
        finally:
            with cbt.app.app_context():
                cbt.ex("DELETE FROM exams WHERE id=?", (second_exam_id,))
                cbt.ex("DELETE FROM questions WHERE subject_id=?", (second_subject_id,))
                cbt.ex("DELETE FROM subjects WHERE id=?", (second_subject_id,))

    def test_admin_can_enable_and_disable_automatic_android_exam_sync(self):
        disabled = self.client.post(
            f"/api/admin/exams/{self.exam_id}/android-sync", json={"enabled": False}
        )
        self.assertEqual(disabled.status_code, 200, disabled.get_json())
        with cbt.app.app_context():
            row = cbt.q1("SELECT android_host_sync_enabled FROM exams WHERE id=?", (self.exam_id,))
        self.assertEqual(row["android_host_sync_enabled"], 0)
        enabled = self.client.post(
            f"/api/admin/exams/{self.exam_id}/android-sync", json={"enabled": True}
        )
        self.assertEqual(enabled.status_code, 200, enabled.get_json())
        with cbt.app.app_context():
            row = cbt.q1("SELECT android_host_sync_enabled FROM exams WHERE id=?", (self.exam_id,))
        self.assertEqual(row["android_host_sync_enabled"], 1)

    def test_sync_pull_rejects_plain_http_from_remote_network(self):
        response = self.client.post(
            "/api/android-host/sync-pull",
            base_url="http://school.example",
            json={"device_id": self.device_id, "known_revisions": {}},
            headers={"Authorization": "Bearer " + self.device_token},
            environ_overrides={"REMOTE_ADDR": "192.168.1.50"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("HTTPS", response.get_json()["error"])

    def test_android_package_import_creates_school_data_and_preserves_attempts(self):
        original_path = cbt.DB_PATH
        with tempfile.TemporaryDirectory(prefix="vicora-android-target-") as target_dir:
            try:
                cbt.DB_PATH = os.path.join(target_dir, "cbt.db")
                cbt.init_db()
                # init_db seeds a generic default school name. This test models a
                # freshly installed, not-yet-claimed Android host, so clear only
                # this disposable test database before importing the paired school.
                blank = cbt.raw()
                blank.execute("UPDATE settings SET value='' WHERE key='school_name'")
                blank.commit()
                blank.close()
                conn = android_sync._connect(target_dir)
                try:
                    result = android_sync._import_exam_package(conn, self.package)
                    conn.commit()
                    self.assertEqual(result["status"], "imported")
                    row = conn.execute("SELECT title,status FROM exams WHERE sync_uuid=?",
                                       (self.package["exam"]["sync_uuid"],)).fetchone()
                    self.assertEqual(row["title"], self.package["exam"]["title"])
                    self.assertEqual(row["status"], "draft")
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM students").fetchone()[0], 1)
                    school = conn.execute("SELECT value FROM settings WHERE key='school_name'").fetchone()
                    self.assertEqual(school["value"], "Automatic Sync Test School")
                    # A changed package must not overwrite an examination once candidates have attempts.
                    exam_id = conn.execute("SELECT id FROM exams WHERE sync_uuid=?",
                                           (self.package["exam"]["sync_uuid"],)).fetchone()[0]
                    student_id = conn.execute("SELECT id FROM students").fetchone()[0]
                    conn.execute(
                        """INSERT INTO sessions(exam_id,student_id,device,start_ts,last_seen,status,attempt_uuid)
                           VALUES(?,?,?,?,?,'submitted',?)""",
                        (exam_id, student_id, "test", 1, 1, str(uuid.uuid4())),
                    )
                    changed = dict(self.package)
                    changed["exam"] = dict(self.package["exam"])
                    changed["exam"]["sync_revision_hash"] = "f" * 64
                    with self.assertRaisesRegex(ValueError, "candidate attempts"):
                        android_sync._import_exam_package(conn, changed)
                    conn.rollback()
                finally:
                    conn.close()
            finally:
                cbt.DB_PATH = original_path


if __name__ == "__main__":
    unittest.main()
