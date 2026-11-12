"""Regression tests for school-scoped natural-key uniqueness."""
import sqlite3
import unittest

from school_scoped_migration import migrate_school_scoped_unique_keys


class SchoolScopedUniqueMigrationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE schools(school_id TEXT PRIMARY KEY, name TEXT);
            INSERT INTO schools VALUES('school-a','School A');
            INSERT INTO schools VALUES('school-b','School B');
            CREATE TABLE admins(
                id INTEGER PRIMARY KEY, username TEXT UNIQUE,
                password_hash TEXT, role TEXT NOT NULL DEFAULT 'super_admin',
                active INTEGER NOT NULL DEFAULT 1, school_id TEXT
            );
            CREATE TABLE classes(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL,
                sync_uuid TEXT, school_id TEXT);
            CREATE TABLE subjects(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL,
                sync_uuid TEXT, school_id TEXT);
            CREATE TABLE students(id INTEGER PRIMARY KEY, reg_no TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL, class_id INTEGER NOT NULL REFERENCES classes(id),
                access_code TEXT NOT NULL, sync_uuid TEXT, school_id TEXT);
            CREATE TABLE staff_exam_assignments(
                staff_id INTEGER NOT NULL REFERENCES admins(id),
                exam_id INTEGER NOT NULL, assigned_by TEXT, assigned_ts INTEGER,
                PRIMARY KEY(staff_id, exam_id)
            );
            CREATE TABLE exams(id INTEGER PRIMARY KEY,
                subject_id INTEGER NOT NULL REFERENCES subjects(id));
            CREATE INDEX idx_admins_school_id ON admins(school_id);
            CREATE TRIGGER trg_admin_legacy AFTER INSERT ON admins
            WHEN NEW.school_id IS NULL
            BEGIN UPDATE admins SET school_id='school-a' WHERE id=NEW.id; END;
            INSERT INTO admins(id,username,password_hash,school_id)
                VALUES(1,'principal','hash-a','school-a');
            INSERT INTO classes(id,name,school_id) VALUES(10,'JSS1','school-a');
            INSERT INTO subjects(id,name,school_id) VALUES(20,'Mathematics','school-a');
            INSERT INTO students(id,reg_no,name,class_id,access_code,school_id)
                VALUES(30,'STU001','Existing Student',10,'ABC123','school-a');
            INSERT INTO exams(id,subject_id) VALUES(40,20);
            INSERT INTO staff_exam_assignments(staff_id,exam_id)
                VALUES(1,40);
        """)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_existing_ids_data_indexes_triggers_and_foreign_keys_survive(self):
        migrate_school_scoped_unique_keys(self.db)
        self.assertEqual(self.db.execute(
            "SELECT id,username,password_hash,school_id FROM admins"
        ).fetchone(), (1, "principal", "hash-a", "school-a"))
        self.assertEqual(self.db.execute(
            "SELECT id,name,school_id FROM classes"
        ).fetchone(), (10, "JSS1", "school-a"))
        self.assertEqual(self.db.execute(
            "SELECT id,reg_no,name,class_id FROM students"
        ).fetchone(), (30, "STU001", "Existing Student", 10))
        self.assertEqual(self.db.execute(
            "SELECT staff_id,exam_id FROM staff_exam_assignments"
        ).fetchone(), (1, 40))
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.db.execute(
            "INSERT INTO admins(username,password_hash,school_id) VALUES('new','hash','school-a')"
        )
        self.assertEqual(self.db.execute(
            "SELECT school_id FROM admins WHERE username='new'"
        ).fetchone()[0], "school-a")

    def test_same_natural_keys_are_allowed_in_different_schools(self):
        migrate_school_scoped_unique_keys(self.db)
        self.db.execute(
            "INSERT INTO admins(username,password_hash,school_id) VALUES('principal','hash-b','school-b')"
        )
        self.db.execute("INSERT INTO classes(name,school_id) VALUES('JSS1','school-b')")
        self.db.execute("INSERT INTO subjects(name,school_id) VALUES('Mathematics','school-b')")
        self.db.execute(
            "INSERT INTO students(reg_no,name,class_id,access_code,school_id) "
            "VALUES('STU001','Other Student',10,'DEF456','school-b')"
        )

    def test_duplicate_natural_keys_remain_rejected_within_one_school(self):
        migrate_school_scoped_unique_keys(self.db)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO admins(username,password_hash,school_id) VALUES('principal','x','school-a')"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO classes(name,school_id) VALUES('JSS1','school-a')")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO subjects(name,school_id) VALUES('Mathematics','school-a')")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO students(reg_no,name,class_id,access_code,school_id) "
                "VALUES('STU001','Duplicate',10,'X','school-a')"
            )

    def test_migration_is_idempotent(self):
        first = migrate_school_scoped_unique_keys(self.db)
        second = migrate_school_scoped_unique_keys(self.db)
        self.assertEqual(first, second)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM admins").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
