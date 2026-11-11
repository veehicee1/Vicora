"""Regression tests for VICORA staff roles and server-enforced permissions."""
import os
import tempfile
import unittest

os.environ.setdefault("CBT_DATA", tempfile.mkdtemp(prefix="vicora-rbac-tests-"))

from app import app, ex, q1  # noqa: E402


class StaffRBACTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()
        with app.app_context():
            ex("UPDATE admins SET role='super_admin', active=1 WHERE username='admin'")

    def query(self, sql, args=()):
        with app.app_context():
            return q1(sql, args)

    def execute(self, sql, args=()):
        with app.app_context():
            return ex(sql, args)

    def sign_in_as(self, username="admin"):
        with self.client.session_transaction() as sess:
            sess["admin"] = username

    def test_existing_admin_schema_has_additive_role_fields(self):
        with app.app_context():
            from app import db
            cols = {r["name"] for r in db().execute("PRAGMA table_info(admins)").fetchall()}
        self.assertIn("role", cols)
        self.assertIn("active", cols)
        admin = self.query("SELECT role, active FROM admins WHERE username='admin'")
        self.assertEqual(admin["role"], "super_admin")
        self.assertEqual(admin["active"], 1)

    def test_super_admin_can_manage_staff_accounts(self):
        self.sign_in_as()
        response = self.client.post("/api/admin/staff", json={
            "username": "marker.one",
            "password": "StrongPass123!",
            "role": "examiner",
        })
        self.assertEqual(response.status_code, 200, response.get_json())
        row = self.query("SELECT username, role, active, password_hash FROM admins WHERE username='marker.one'")
        self.assertEqual(row["role"], "examiner")
        self.assertEqual(row["active"], 1)
        self.assertNotEqual(row["password_hash"], "StrongPass123!")

    def test_auditor_is_read_only_and_cannot_open_question_bank(self):
        self.execute("UPDATE admins SET role='auditor' WHERE username='admin'")
        self.sign_in_as()
        allowed = self.client.get("/api/admin/audit")
        denied = self.client.get("/api/admin/questions")
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(denied.status_code, 403)

    def test_invigilator_can_monitor_but_cannot_manage_questions_or_pause_exam(self):
        self.execute("UPDATE admins SET role='invigilator' WHERE username='admin'")
        self.sign_in_as()
        monitor = self.client.get("/api/admin/monitor/1")
        questions = self.client.get("/api/admin/questions")
        pause_exam = self.client.post("/api/admin/exams/1/status", json={"status": "paused"})
        self.assertNotEqual(monitor.status_code, 403)
        self.assertEqual(questions.status_code, 403)
        self.assertEqual(pause_exam.status_code, 403)

    def test_examiner_can_open_theory_marking_but_not_question_bank(self):
        self.execute("UPDATE admins SET role='examiner' WHERE username='admin'")
        self.sign_in_as()
        theory = self.client.get("/api/admin/theory/1")
        questions = self.client.get("/api/admin/questions")
        self.assertNotEqual(theory.status_code, 403)
        self.assertEqual(questions.status_code, 403)

    def test_exam_administrator_cannot_manage_staff_or_backups(self):
        self.execute("UPDATE admins SET role='exam_administrator' WHERE username='admin'")
        self.sign_in_as()
        students = self.client.get("/api/admin/students")
        staff = self.client.get("/api/admin/staff")
        backups = self.client.get("/api/admin/backups")
        self.assertNotEqual(students.status_code, 403)
        self.assertEqual(staff.status_code, 403)
        self.assertEqual(backups.status_code, 403)

    def test_marker_only_sees_and_marks_assigned_examinations(self):
        self.execute("DELETE FROM staff_exam_assignments WHERE staff_id IN (SELECT id FROM admins WHERE username='marker.rbac')")
        self.execute("DELETE FROM admins WHERE username='marker.rbac'")
        self.execute("INSERT OR IGNORE INTO subjects(name) VALUES('RBAC Test Subject')")
        subject = self.query("SELECT id FROM subjects WHERE name='RBAC Test Subject'")["id"]
        self.execute("INSERT INTO exams(title,subject_id,duration_min,num_questions,created_ts) VALUES('RBAC Assigned Exam',?,30,0,0)", (subject,))
        assigned = self.query("SELECT id FROM exams WHERE title='RBAC Assigned Exam'")["id"]
        self.execute("INSERT INTO exams(title,subject_id,duration_min,num_questions,created_ts) VALUES('RBAC Unassigned Exam',?,30,0,0)", (subject,))
        unassigned = self.query("SELECT id FROM exams WHERE title='RBAC Unassigned Exam'")["id"]
        self.sign_in_as()
        created = self.client.post("/api/admin/staff", json={
            "username": "marker.rbac", "password": "StrongPass123!", "role": "examiner"
        })
        self.assertEqual(created.status_code, 200, created.get_json())
        staff_id = self.query("SELECT id FROM admins WHERE username='marker.rbac'")["id"]
        saved = self.client.post(f"/api/admin/staff/{staff_id}/exams", json={"exam_ids": [assigned]})
        self.assertEqual(saved.status_code, 200, saved.get_json())
        self.sign_in_as("marker.rbac")
        exams = self.client.get("/api/admin/exams")
        self.assertEqual(exams.status_code, 200)
        self.assertEqual([row["id"] for row in exams.get_json()], [assigned])
        allowed = self.client.get(f"/api/admin/results/{assigned}")
        denied = self.client.get(f"/api/admin/results/{unassigned}")
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(denied.status_code, 403)

    def test_inactive_staff_session_is_rejected(self):
        self.execute("UPDATE admins SET active=0 WHERE username='admin'")
        self.sign_in_as()
        response = self.client.get("/api/admin/dashboard")
        self.assertEqual(response.status_code, 401)

    def test_staff_cannot_demote_or_deactivate_own_account(self):
        self.sign_in_as()
        admin_id = self.query("SELECT id FROM admins WHERE username='admin'")["id"]
        response = self.client.post(f"/api/admin/staff/{admin_id}", json={
            "role": "auditor",
            "active": False,
        })
        self.assertEqual(response.status_code, 400)
        row = self.query("SELECT role, active FROM admins WHERE username='admin'")
        self.assertEqual(row["role"], "super_admin")
        self.assertEqual(row["active"], 1)


if __name__ == "__main__":
    unittest.main()
