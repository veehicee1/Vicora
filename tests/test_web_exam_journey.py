"""End-to-end browser examination journey using an isolated test database."""
import os
import tempfile
import time
import unittest
import uuid

# Never point this test at a real school database.
os.environ.setdefault("CBT_DATA", tempfile.mkdtemp(prefix="vicora-web-exam-e2e-"))

import app as cbt  # noqa: E402
from app import question_fingerprint  # noqa: E402


class QuestionRepeatProtectionTests(unittest.TestCase):
    def test_fingerprint_ignores_case_spacing_and_punctuation_but_preserves_math_signs(self):
        self.assertEqual(question_fingerprint("What is 2 + 2?"),
                         question_fingerprint(" what IS 2+2 "))
        self.assertNotEqual(question_fingerprint("What is 2 + 2?"),
                            question_fingerprint("What is 2 - 2?"))


class WebExaminationJourneyTests(unittest.TestCase):
    def setUp(self):
        cbt.app.config.update(TESTING=True)
        self.client = cbt.app.test_client()
        suffix = uuid.uuid4().hex[:10]
        self.reg_no = "WEB" + suffix
        self.code = "WEB123"
        db = cbt.raw()
        self.class_id = db.execute(
            "INSERT INTO classes(name) VALUES(?)", ("Web E2E Class " + suffix,)
        ).lastrowid
        self.subject_id = db.execute(
            "INSERT INTO subjects(name) VALUES(?)", ("Web E2E Subject " + suffix,)
        ).lastrowid
        self.student_id = db.execute(
            "INSERT INTO students(reg_no,name,class_id,access_code) VALUES(?,?,?,?)",
            (self.reg_no, "Web Journey Candidate", self.class_id, self.code),
        ).lastrowid
        self.objective_id = db.execute(
            """INSERT INTO questions(subject_id,text,a,b,c,d,answer,marks,question_type)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (self.subject_id, "E2E objective " + suffix, "Alpha", "Bravo", "Charlie",
             "Delta", "B", 2, "objective"),
        ).lastrowid
        self.theory_id = db.execute(
            """INSERT INTO questions(subject_id,text,answer,marks,question_type,
                                     answer_text,marking_mode)
               VALUES(?,?,?,?,?,?,?)""",
            (self.subject_id, "E2E theory " + suffix, "", 3, "theory",
             "A complete test response", "exact"),
        ).lastrowid
        self.exam_id = db.execute(
            """INSERT INTO exams(title,subject_id,duration_min,num_questions,shuffle,
                                 show_score,pass_mark,instructions,status,created_ts,
                                 objective_count,theory_count,camera_policy)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("Web E2E Exam " + suffix, self.subject_id, 30, 1, 0, 1, 50,
             "Automated end-to-end test", "live", int(time.time()), 1, 1, "off"),
        ).lastrowid
        db.execute("INSERT INTO exam_classes(exam_id,class_id) VALUES(?,?)",
                   (self.exam_id, self.class_id))
        db.commit()
        db.close()
        self.credentials = {"reg_no": self.reg_no, "code": self.code}

    def tearDown(self):
        db = cbt.raw()
        db.execute("DELETE FROM sessions WHERE exam_id=?", (self.exam_id,))
        db.execute("DELETE FROM exams WHERE id=?", (self.exam_id,))
        db.execute("DELETE FROM questions WHERE subject_id=?", (self.subject_id,))
        db.execute("DELETE FROM students WHERE id=?", (self.student_id,))
        db.execute("DELETE FROM subjects WHERE id=?", (self.subject_id,))
        db.execute("DELETE FROM classes WHERE id=?", (self.class_id,))
        db.commit()
        db.close()

    def test_candidate_completes_web_exam_and_receives_published_result(self):
        login = self.client.post("/api/student/login", json=self.credentials)
        self.assertEqual(login.status_code, 200, login.get_json())
        payload = login.get_json()
        self.assertEqual(payload["student"]["reg_no"], self.reg_no)
        self.assertEqual(len(payload["exams"]), 1)
        self.assertEqual(payload["exams"][0]["id"], self.exam_id)
        self.assertEqual(payload["exams"][0]["state"], "new")

        begin = self.client.post("/api/student/begin", json={
            **self.credentials, "exam_id": self.exam_id, "device": "automated-browser"
        })
        self.assertEqual(begin.status_code, 200, begin.get_json())
        token = begin.get_json()["token"]
        headers = {"X-Token": token}
        paper_response = self.client.get("/api/student/paper", headers=headers)
        self.assertEqual(paper_response.status_code, 200, paper_response.get_json())
        paper = paper_response.get_json()
        self.assertEqual(len(paper["questions"]), 2)
        self.assertTrue(paper["school"])
        by_type = {question["type"]: question for question in paper["questions"]}
        self.assertEqual(set(by_type), {"objective", "theory"})
        for question in paper["questions"]:
            self.assertNotIn("answer", question)
            self.assertNotIn("answer_text", question)

        objective_save = self.client.post(
            "/api/student/answer",
            json={"qid": by_type["objective"]["id"], "choice": "B"},
            headers=headers,
        )
        self.assertEqual(objective_save.status_code, 200, objective_save.get_json())
        theory_save = self.client.post(
            "/api/student/answer",
            json={"qid": by_type["theory"]["id"],
                  "response_text": "A complete test response"},
            headers=headers,
        )
        self.assertEqual(theory_save.status_code, 200, theory_save.get_json())
        heartbeat = self.client.post("/api/student/heartbeat", json={}, headers=headers)
        self.assertEqual(heartbeat.status_code, 200, heartbeat.get_json())
        self.assertTrue(heartbeat.get_json()["ok"])

        submitted = self.client.post("/api/student/submit", json={}, headers=headers)
        self.assertEqual(submitted.status_code, 200, submitted.get_json())
        self.assertTrue(submitted.get_json()["done"])
        self.assertEqual(submitted.get_json()["score"], 5)
        self.assertEqual(submitted.get_json()["total"], 5)

        grades = self.client.post("/api/student/grades", json=self.credentials)
        self.assertEqual(grades.status_code, 200, grades.get_json())
        rows = grades.get_json()["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["exam"], "Web E2E Exam " + self.reg_no[3:])
        self.assertEqual(rows[0]["score"], 5)
        self.assertEqual(rows[0]["total"], 5)
        self.assertEqual(rows[0]["percent"], 100)
        self.assertEqual(rows[0]["grade"], "A")


if __name__ == "__main__":
    unittest.main()
