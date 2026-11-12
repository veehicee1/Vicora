"""End-to-end tenant login and core API isolation tests."""
import os
import tempfile
import unittest
import uuid

os.environ.setdefault("CBT_DATA", tempfile.mkdtemp(prefix="vicora-tenant-api-tests-"))
import app as cbt  # noqa: E402


class MultiTenantLoginIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vicora-tenant-api-")
        old_path = cbt.DB_PATH
        self.addCleanup(setattr, cbt, "DB_PATH", old_path)
        cbt.DB_PATH = os.path.join(self.temp.name, "cbt.db")
        cbt.init_db()
        self.client = cbt.app.test_client()
        cbt.app.config.update(TESTING=True)

        db = cbt.raw()
        legacy = db.execute("SELECT school_id FROM schools WHERE is_legacy_default=1").fetchone()
        self.school_a = legacy["school_id"]
        self.school_b = "school-" + uuid.uuid4().hex
        db.execute("UPDATE schools SET school_code='VIC-AAAA1111',name='Alpha School' WHERE school_id=?",
                   (self.school_a,))
        db.execute(
            """INSERT INTO schools(school_id,school_code,name,status,is_legacy_default,created_ts,approved_ts)
               VALUES(?, 'VIC-BBBB2222','Beta School','approved',0,2,2)""",
            (self.school_b,),
        )
        db.execute("UPDATE settings SET value='Alpha School' WHERE key='school_name' AND school_id=?",
                   (self.school_a,))
        password_hash = cbt.generate_password_hash("School-Password-2026!")
        for school_id in (self.school_a, self.school_b):
            db.execute(
                "INSERT INTO admins(username,password_hash,role,active,school_id) VALUES('principal',?,'super_admin',1,?)",
                (password_hash, school_id),
            )
        self.class_a = db.execute(
            "INSERT INTO classes(name,school_id) VALUES('JSS1',?)", (self.school_a,)
        ).lastrowid
        self.class_b = db.execute(
            "INSERT INTO classes(name,school_id) VALUES('JSS1',?)", (self.school_b,)
        ).lastrowid
        self.subject_a = db.execute(
            "INSERT INTO subjects(name,school_id) VALUES('Mathematics',?)", (self.school_a,)
        ).lastrowid
        self.subject_b = db.execute(
            "INSERT INTO subjects(name,school_id) VALUES('Mathematics',?)", (self.school_b,)
        ).lastrowid
        db.execute(
            "INSERT INTO students(reg_no,name,class_id,access_code,school_id) VALUES('S001','Alpha Student',?,'PIN123',?)",
            (self.class_a, self.school_a),
        )
        db.execute(
            "INSERT INTO students(reg_no,name,class_id,access_code,school_id) VALUES('S001','Beta Student',?,'PIN123',?)",
            (self.class_b, self.school_b),
        )
        self.exam_a = db.execute(
            """INSERT INTO exams(title,subject_id,duration_min,num_questions,status,created_ts,school_id)
               VALUES('Alpha Mathematics',?,30,1,'live',1,?)""",
            (self.subject_a, self.school_a),
        ).lastrowid
        self.exam_b = db.execute(
            """INSERT INTO exams(title,subject_id,duration_min,num_questions,status,created_ts,school_id)
               VALUES('Beta Mathematics',?,30,1,'live',1,?)""",
            (self.subject_b, self.school_b),
        ).lastrowid
        db.execute("INSERT INTO exam_classes(exam_id,class_id) VALUES(?,?)", (self.exam_a, self.class_a))
        db.execute("INSERT INTO exam_classes(exam_id,class_id) VALUES(?,?)", (self.exam_b, self.class_b))
        db.commit()
        db.close()
        self.addCleanup(self.temp.cleanup)

    def test_admin_same_username_sees_only_the_school_selected_by_code(self):
        first = self.client.post("/api/admin/login", json={
            "school_code": "VIC-AAAA1111", "username": "principal",
            "password": "School-Password-2026!"
        })
        self.assertEqual(first.status_code, 200, first.get_json())
        classes_a = self.client.get("/api/admin/classes").get_json()
        students_a = self.client.get("/api/admin/students").get_json()
        self.assertEqual([row["name"] for row in classes_a], ["JSS1"])
        self.assertEqual([row["name"] for row in students_a["rows"]], ["Alpha Student"])

        self.client.post("/api/admin/logout")
        second = self.client.post("/api/admin/login", json={
            "school_code": "VIC-BBBB2222", "username": "principal",
            "password": "School-Password-2026!"
        })
        self.assertEqual(second.status_code, 200, second.get_json())
        classes_b = self.client.get("/api/admin/classes").get_json()
        students_b = self.client.get("/api/admin/students").get_json()
        self.assertEqual([row["name"] for row in classes_b], ["JSS1"])
        self.assertEqual([row["name"] for row in students_b["rows"]], ["Beta Student"])

    def test_student_login_with_school_code_returns_only_that_school_exams(self):
        alpha = self.client.post("/api/student/login", json={
            "school_code": "VIC-AAAA1111", "reg_no": "S001", "code": "PIN123"
        })
        beta = self.client.post("/api/student/login", json={
            "school_code": "VIC-BBBB2222", "reg_no": "S001", "code": "PIN123"
        })
        self.assertEqual(alpha.status_code, 200, alpha.get_json())
        self.assertEqual(beta.status_code, 200, beta.get_json())
        self.assertEqual([exam["title"] for exam in alpha.get_json()["exams"]], ["Alpha Mathematics"])
        self.assertEqual([exam["title"] for exam in beta.get_json()["exams"]], ["Beta Mathematics"])

    def test_android_host_pairing_code_is_bound_to_the_selected_school(self):
        login = self.client.post("/api/admin/login", json={
            "school_code": "VIC-AAAA1111", "username": "principal",
            "password": "School-Password-2026!"
        })
        self.assertEqual(login.status_code, 200)
        pairing = self.client.post("/api/admin/android-host/pairing-code")
        self.assertEqual(pairing.status_code, 200)
        device_id = str(uuid.uuid4())
        paired = self.client.post("/api/android-host/pair", json={
            "school_code": "VIC-AAAA1111",
            "pairing_code": pairing.get_json()["pairing_code"],
            "device_id": device_id,
            "label": "Alpha Android Host",
        })
        self.assertEqual(paired.status_code, 200, paired.get_json())
        db = cbt.raw()
        row = db.execute(
            "SELECT school_id FROM android_host_devices WHERE device_id=?", (device_id,)
        ).fetchone()
        db.close()
        self.assertEqual(row["school_id"], self.school_a)

    def test_new_school_host_token_heartbeat_is_school_scoped(self):
        login = self.client.post("/api/admin/login", json={
            "school_code": "VIC-AAAA1111", "username": "principal",
            "password": "School-Password-2026!"
        })
        self.assertEqual(login.status_code, 200)
        device_id = "vicora-alpha-android-01"
        enrolled = self.client.post("/api/admin/hosts/enroll", json={
            "device_id": device_id, "platform": "android", "label": "Alpha Cloud Host"
        })
        self.assertEqual(enrolled.status_code, 200, enrolled.get_json())
        credentials = enrolled.get_json()
        self.assertEqual(credentials["school_code"], "VIC-AAAA1111")
        heartbeat = self.client.post("/api/host/heartbeat", headers={
            "X-VICORA-HOST-TOKEN": credentials["host_token"]
        })
        self.assertEqual(heartbeat.status_code, 200, heartbeat.get_json())
        self.assertEqual(heartbeat.get_json()["school_id"], self.school_a)
        self.assertEqual(heartbeat.get_json()["device_id"], device_id)

    def test_unknown_school_code_fails_closed(self):
        response = self.client.post("/api/student/login", json={
            "school_code": "VIC-DEADBEEF", "reg_no": "S001", "code": "PIN123"
        })
        self.assertEqual(response.status_code, 401)


    def test_foreign_school_exam_id_is_hidden_from_results_and_exports(self):
        login = self.client.post("/api/admin/login", json={
            "school_code": "VIC-AAAA1111", "username": "principal",
            "password": "School-Password-2026!"
        })
        self.assertEqual(login.status_code, 200)
        results = self.client.get(f"/api/admin/results/{self.exam_b}")
        exported = self.client.get(f"/api/admin/export/results/{self.exam_b}")
        self.assertEqual(results.status_code, 404, results.get_json())
        self.assertEqual(exported.status_code, 404, exported.get_json())

    def test_foreign_school_student_id_cannot_be_deleted(self):
        login = self.client.post("/api/admin/login", json={
            "school_code": "VIC-AAAA1111", "username": "principal",
            "password": "School-Password-2026!"
        })
        self.assertEqual(login.status_code, 200)
        db = cbt.raw()
        foreign = db.execute(
            "SELECT id FROM students WHERE school_id=? AND name='Beta Student'",
            (self.school_b,),
        ).fetchone()
        db.close()
        self.assertIsNotNone(foreign)
        response = self.client.post("/api/admin/students/delete", json={"ids": [foreign["id"]]})
        self.assertEqual(response.status_code, 200, response.get_json())
        db = cbt.raw()
        still_there = db.execute(
            "SELECT id FROM students WHERE id=? AND school_id=?",
            (foreign["id"], self.school_b),
        ).fetchone()
        db.close()
        self.assertIsNotNone(still_there, "A school-A administrator must not delete a school-B student.")

    def test_shared_database_backup_routes_fail_closed_for_multiple_schools(self):
        login = self.client.post("/api/admin/login", json={
            "school_code": "VIC-AAAA1111", "username": "principal",
            "password": "School-Password-2026!"
        })
        self.assertEqual(login.status_code, 200)
        listing = self.client.get("/api/admin/backups")
        creation = self.client.post("/api/admin/backups")
        self.assertEqual(listing.status_code, 503, listing.get_json())
        self.assertEqual(creation.status_code, 503, creation.get_json())
        self.assertIn("School-specific backup", listing.get_json()["error"])

    def test_android_cloud_host_token_cannot_pull_another_school_exams(self):
        login = self.client.post("/api/admin/login", json={
            "school_code": "VIC-AAAA1111", "username": "principal",
            "password": "School-Password-2026!"
        })
        self.assertEqual(login.status_code, 200)
        device_id = "vicora-alpha-negative-sync"
        enrolled = self.client.post("/api/admin/hosts/enroll", json={
            "device_id": device_id, "platform": "android", "label": "Alpha Host"
        })
        self.assertEqual(enrolled.status_code, 200, enrolled.get_json())
        token = enrolled.get_json()["host_token"]
        db = cbt.raw()
        db.execute("UPDATE exams SET android_host_sync_enabled=1 WHERE id=?", (self.exam_b,))
        db.commit()
        db.close()
        response = self.client.post(
            "/api/android-host/sync-pull",
            base_url="https://api.vicora.example",
            json={"device_id": device_id, "known_revisions": {}},
            headers={"X-VICORA-HOST-TOKEN": token},
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        titles = [item["exam"]["title"] for item in response.get_json()["packages"]]
        self.assertNotIn("Beta Mathematics", titles)

if __name__ == "__main__":
    unittest.main()
