import sqlite3
import unittest

from multi_tenant import activate_tenant_views, migrate_multi_tenant_schema


class TenantSqlViewIsolationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE schools(
              school_id TEXT PRIMARY KEY, school_code TEXT NOT NULL UNIQUE,
              name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'approved',
              is_legacy_default INTEGER NOT NULL DEFAULT 0,
              created_ts INTEGER NOT NULL DEFAULT 0, approved_ts INTEGER);
            INSERT INTO schools VALUES('school-a','VIC-AAAA1111','Alpha School','approved',1,1,1);
            INSERT INTO schools VALUES('school-b','VIC-BBBB2222','Beta School','approved',0,2,2);
            CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);
            INSERT INTO settings VALUES('school_name','Alpha School');
            INSERT INTO settings VALUES('vicora_legacy_school_id','school-a');
            CREATE TABLE admins(id INTEGER PRIMARY KEY,username TEXT NOT NULL,password_hash TEXT NOT NULL,
              role TEXT NOT NULL DEFAULT 'super_admin',active INTEGER NOT NULL DEFAULT 1,school_id TEXT NOT NULL);
            CREATE UNIQUE INDEX ux_admins_school_username ON admins(school_id,username);
            CREATE TABLE classes(id INTEGER PRIMARY KEY,name TEXT NOT NULL,school_id TEXT NOT NULL);
            CREATE TABLE subjects(id INTEGER PRIMARY KEY,name TEXT NOT NULL,school_id TEXT NOT NULL);
            CREATE TABLE students(id INTEGER PRIMARY KEY,reg_no TEXT NOT NULL,name TEXT NOT NULL,
              class_id INTEGER NOT NULL,access_code TEXT NOT NULL,school_id TEXT NOT NULL);
            CREATE TABLE questions(id INTEGER PRIMARY KEY,subject_id INTEGER NOT NULL,text TEXT NOT NULL,school_id TEXT NOT NULL);
            CREATE TABLE exams(id INTEGER PRIMARY KEY,title TEXT NOT NULL,subject_id INTEGER NOT NULL,school_id TEXT NOT NULL);
            CREATE TABLE sessions(id INTEGER PRIMARY KEY,exam_id INTEGER NOT NULL,student_id INTEGER NOT NULL,
              token TEXT,school_id TEXT NOT NULL);
            CREATE TABLE messages(id INTEGER PRIMARY KEY,student_id INTEGER NOT NULL,title TEXT NOT NULL,
              body TEXT NOT NULL,school_id TEXT NOT NULL);
            CREATE TABLE exam_classes(exam_id INTEGER,class_id INTEGER,PRIMARY KEY(exam_id,class_id));
            CREATE TABLE session_questions(session_id INTEGER,pos INTEGER,question_id INTEGER,opt_order TEXT,
              PRIMARY KEY(session_id,pos));
            CREATE TABLE staff_exam_assignments(staff_id INTEGER,exam_id INTEGER,assigned_by TEXT,
              assigned_ts INTEGER,PRIMARY KEY(staff_id,exam_id));
            CREATE TABLE messages(id INTEGER PRIMARY KEY,student_id INTEGER,exam_id INTEGER,title TEXT,
              body TEXT,school_id TEXT);
            CREATE TABLE answers(session_id INTEGER,question_id INTEGER,choice TEXT,response_text TEXT,
              response_drawing TEXT,flagged INTEGER,ts INTEGER,school_id TEXT,PRIMARY KEY(session_id,question_id));
            CREATE TABLE theory_marks(session_id INTEGER,question_id INTEGER,mark REAL,school_id TEXT,
              PRIMARY KEY(session_id,question_id));
            CREATE TABLE proctor_events(id INTEGER PRIMARY KEY,session_id INTEGER,request_id TEXT,
              event_type TEXT,server_ts INTEGER,school_id TEXT);
            CREATE TABLE android_sync_receipts(id INTEGER PRIMARY KEY,attempt_uuid TEXT,device_id TEXT,
              session_id INTEGER,payload_hash TEXT,synced_ts INTEGER,school_id TEXT);
            INSERT INTO admins(id,username,password_hash,school_id) VALUES(1,'principal','hash-a','school-a');
            INSERT INTO admins(id,username,password_hash,school_id) VALUES(2,'principal','hash-b','school-b');
            INSERT INTO classes VALUES(10,'JSS1','school-a');
            INSERT INTO classes VALUES(20,'JSS1','school-b');
            INSERT INTO subjects VALUES(30,'Mathematics','school-a');
            INSERT INTO subjects VALUES(40,'Mathematics','school-b');
            INSERT INTO students VALUES(50,'A001','Student A',10,'A-CODE','school-a');
            INSERT INTO students VALUES(60,'A001','Student B',20,'B-CODE','school-b');
            INSERT INTO questions VALUES(70,30,'Question A','school-a');
            INSERT INTO questions VALUES(80,40,'Question B','school-b');
            INSERT INTO exams VALUES(90,'Exam A',30,'school-a');
            INSERT INTO exams VALUES(100,'Exam B',40,'school-b');
            INSERT INTO sessions VALUES(110,90,50,'token-a','school-a');
            INSERT INTO sessions VALUES(120,100,60,'token-b','school-b');
            INSERT INTO exam_classes VALUES(90,10);
            INSERT INTO exam_classes VALUES(100,20);
            INSERT INTO session_questions VALUES(110,1,70,'AB');
            INSERT INTO session_questions VALUES(120,1,80,'BA');
            INSERT INTO staff_exam_assignments VALUES(1,90,'owner',1);
            INSERT INTO staff_exam_assignments VALUES(2,100,'owner',1);
        """)
        self.db.commit()
        migrate_multi_tenant_schema(self.db)
        self.db.execute("INSERT INTO main.settings(key,value,school_id) VALUES('school_name','Beta School','school-b')")
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_tenant_views_filter_reads_and_stamp_writes(self):
        activate_tenant_views(self.db, "school-a")
        self.assertEqual([r["username"] for r in self.db.execute("SELECT username FROM admins")], ["principal"])
        self.assertEqual(self.db.execute("SELECT id FROM students").fetchall()[0][0], 50)
        self.assertEqual(self.db.execute("SELECT value FROM settings WHERE key='school_name'").fetchone()[0], "Alpha School")
        self.db.execute("INSERT INTO classes(name) VALUES('JSS2')")
        inserted = self.db.execute("SELECT school_id FROM main.classes WHERE name='JSS2'").fetchone()[0]
        self.assertEqual(inserted, "school-a")
        self.db.execute("UPDATE classes SET name='JSS1A' WHERE id=10")
        self.assertEqual(self.db.execute("SELECT name FROM main.classes WHERE id=10").fetchone()[0], "JSS1A")
        self.db.execute("INSERT INTO settings VALUES('school_theme','{}')")
        self.assertEqual(self.db.execute("SELECT school_id FROM main.settings WHERE key='school_theme'").fetchone()[0], "school-a")

    def test_relationship_views_prevent_cross_school_links(self):
        activate_tenant_views(self.db, "school-a")
        self.assertEqual(self.db.execute("SELECT exam_id FROM exam_classes").fetchone()[0], 90)
        self.assertEqual(self.db.execute("SELECT question_id FROM session_questions").fetchone()[0], 70)
        self.assertEqual(self.db.execute("SELECT staff_id FROM staff_exam_assignments").fetchone()[0], 1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO exam_classes VALUES(90,20)")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO session_questions VALUES(110,2,80,'AB')")

    def test_core_foreign_keys_cannot_cross_school_boundaries(self):
        activate_tenant_views(self.db, "school-a")
        invalid = [
            ("INSERT INTO students(reg_no,name,class_id,access_code) VALUES('A002','Bad Student',20,'X')", ()),
            ("INSERT INTO questions(subject_id,text,school_id) VALUES(40,'Cross subject question','school-a')", ()),
            ("INSERT INTO exams(title,subject_id,school_id) VALUES('Cross subject exam',40,'school-a')", ()),
            ("INSERT INTO sessions(exam_id,student_id,school_id) VALUES(90,60,'school-a')", ()),
            ("INSERT INTO messages(student_id,title,body,school_id) VALUES(60,'Bad','Cross student','school-a')", ()),
            ("INSERT INTO answers(session_id,question_id,school_id) VALUES(110,80,'school-a')", ()),
            ("INSERT INTO theory_marks(session_id,question_id,school_id) VALUES(110,80,'school-a')", ()),
            ("INSERT INTO proctor_events(session_id,request_id,event_type,server_ts,school_id) VALUES(120,'x','test',1,'school-a')", ()),
            ("INSERT INTO android_sync_receipts(attempt_uuid,device_id,session_id,payload_hash,synced_ts,school_id) VALUES('attempt-x','dev',120,'hash',1,'school-a')", ()),
        ]
        for sql, params in invalid:
            with self.subTest(sql=sql):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.db.execute(sql, params)

    def test_explicit_foreign_school_id_is_rejected_and_context_can_switch(self):
        activate_tenant_views(self.db, "school-a")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO admins(username,password_hash,school_id) VALUES('intruder','x','school-b')")
        activate_tenant_views(self.db, "school-b")
        self.assertEqual(self.db.execute("SELECT id FROM students").fetchone()[0], 60)
        self.assertEqual(self.db.execute("SELECT value FROM settings WHERE key='school_name'").fetchone()[0], "Beta School")
        self.assertEqual(self.db.execute("SELECT id FROM admins").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
