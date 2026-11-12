"""Tests for the additive legacy-school tenant bootstrap."""
import sqlite3
import unittest

from tenant_migration import LEGACY_SCHOOL_TABLES, migrate_legacy_school


class LegacySchoolMigrationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT)")
        self.db.execute("INSERT INTO settings(key,value) VALUES('school_name','Greater Tomorrow Model College')")
        for table in LEGACY_SCHOOL_TABLES:
            self.db.execute(f"CREATE TABLE {table}(id INTEGER PRIMARY KEY, label TEXT)")
        self.db.execute("INSERT INTO students(label) VALUES('Existing student')")
        self.db.execute("INSERT INTO exams(label) VALUES('Existing examination')")
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_existing_records_are_assigned_without_changing_ids_or_data(self):
        result = migrate_legacy_school(self.db)
        student = self.db.execute("SELECT id,label,school_id FROM students").fetchone()
        exam = self.db.execute("SELECT id,label,school_id FROM exams").fetchone()
        school = self.db.execute("SELECT school_id,school_code,name,status FROM schools").fetchone()
        self.assertEqual(student[:2], (1, "Existing student"))
        self.assertEqual(exam[:2], (1, "Existing examination"))
        self.assertEqual(student[2], result["school_id"])
        self.assertEqual(exam[2], result["school_id"])
        self.assertEqual(school[0], result["school_id"])
        self.assertEqual(school[2], "Greater Tomorrow Model College")
        self.assertEqual(school[3], "approved")

    def test_migration_is_idempotent_and_keeps_school_identity(self):
        first = migrate_legacy_school(self.db)
        second = migrate_legacy_school(self.db)
        self.assertEqual(first["school_id"], second["school_id"])
        self.assertEqual(first["school_code"], second["school_code"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM schools").fetchone()[0], 1)

    def test_legacy_single_school_inserts_inherit_school_id(self):
        result = migrate_legacy_school(self.db)
        self.db.execute("INSERT INTO students(label) VALUES('New legacy-path student')")
        row = self.db.execute("SELECT school_id FROM students WHERE label='New legacy-path student'").fetchone()
        self.assertEqual(row[0], result["school_id"])

    def test_explicit_school_id_is_not_overwritten(self):
        migrate_legacy_school(self.db)
        self.db.execute("INSERT INTO students(label,school_id) VALUES('Explicit tenant row','school-2')")
        row = self.db.execute("SELECT school_id FROM students WHERE label='Explicit tenant row'").fetchone()
        self.assertEqual(row[0], "school-2")


if __name__ == "__main__":
    unittest.main()
