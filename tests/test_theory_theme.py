"""Regression tests for theory-question migrations and admin-controlled themes."""
import sqlite3
import unittest
import uuid

import app as server


class TheoryAndThemeTests(unittest.TestCase):
    def setUp(self):
        server.app.config.update(TESTING=True)
        self.client = server.app.test_client()
        with self.client.session_transaction() as sess:
            sess["admin"] = "admin"

    def test_additive_theory_schema_is_available(self):
        db = sqlite3.connect(server.DB_PATH)
        try:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIn("theory_marks", tables)
            columns = {
                table: {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
                for table in ("questions", "exams", "answers")
            }
            self.assertTrue({"question_type", "answer_text", "accepted_answers", "keywords",
                             "answer_space", "marking_mode"}.issubset(columns["questions"]))
            self.assertTrue({"objective_count", "theory_count"}.issubset(columns["exams"]))
            self.assertTrue({"response_text", "response_drawing"}.issubset(columns["answers"]))
        finally:
            db.close()

    def test_admin_can_save_school_wide_theme(self):
        theme = {
            "preset": "blue", "mode": "light", "primary": "#0756a8",
            "background": "#f3f7fc", "surface": "#ffffff",
            "text": "#14263d", "sidebar": "#062c53",
        }
        response = self.client.post(
            "/api/admin/settings",
            json={"school_name": "GTMC Test", "allow_remote_admin": False, "theme": theme},
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        public = self.client.get("/api/public/info").get_json()
        self.assertEqual(public["school"], "GTMC Test")
        self.assertEqual(public["theme"]["primary"], "#0756a8")

    def test_admin_can_create_theory_question_with_manual_marking(self):
        subject_name = "Theory Test " + uuid.uuid4().hex[:8]
        db = server.raw()
        subject_id = db.execute("INSERT INTO subjects(name) VALUES(?)", (subject_name,)).lastrowid
        db.commit()
        db.close()
        try:
            response = self.client.post(
                "/api/admin/questions",
                json={
                    "subject_id": subject_id,
                    "text": "Explain the test concept.",
                    "question_type": "theory",
                    "marks": 5,
                    "answer_space": "large",
                    "marking_mode": "manual",
                    "answer_text": "Model answer",
                },
            )
            self.assertEqual(response.status_code, 200, response.get_json())
            db = server.raw()
            row = db.execute(
                "SELECT question_type,answer_space,marking_mode FROM questions WHERE subject_id=?",
                (subject_id,),
            ).fetchone()
            self.assertEqual(tuple(row), ("theory", "large", "manual"))
            db.execute("DELETE FROM questions WHERE subject_id=?", (subject_id,))
            db.execute("DELETE FROM subjects WHERE id=?", (subject_id,))
            db.commit()
            db.close()
        finally:
            db = server.raw()
            db.execute("DELETE FROM questions WHERE subject_id=?", (subject_id,))
            db.execute("DELETE FROM subjects WHERE id=?", (subject_id,))
            db.commit()
            db.close()


if __name__ == "__main__":
    unittest.main()
