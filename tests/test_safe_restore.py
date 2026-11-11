"""Disposable-database tests for the explicit offline restore utility."""
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("CBT_DATA", tempfile.mkdtemp(prefix="gtmc-restore-import-"))
import app as gtmc  # noqa: E402
from restore_backup import RestoreError, restore_backup, validate_database  # noqa: E402


class SafeRestoreTests(unittest.TestCase):
    def setUp(self):
        gtmc.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = gtmc.app.test_client()
        self.original_backup_dir = gtmc.BK
        self.temp = tempfile.TemporaryDirectory(prefix="gtmc-safe-restore-")
        self.root = Path(self.temp.name)
        self.backups = self.root / "backups"
        self.backups.mkdir()
        self.active = self.root / "cbt.db"
        self._make_db(self.active, "CURRENT_DATABASE")
        self.backup_name = "cbt_20261109_110000_manual.db"
        self.selected = self.backups / self.backup_name
        self._make_db(self.selected, "RESTORED_DATABASE")

    def tearDown(self):
        gtmc.BK = self.original_backup_dir
        self.temp.cleanup()

    def _make_db(self, path, class_name):
        conn = sqlite3.connect(path)
        conn.executescript(gtmc.SCHEMA)
        conn.execute("INSERT INTO classes(name) VALUES(?)", (class_name,))
        conn.commit()
        conn.close()

    def _has_class(self, path, name):
        conn = sqlite3.connect(path)
        try:
            return conn.execute("SELECT 1 FROM classes WHERE name=?", (name,)).fetchone() is not None
        finally:
            conn.close()

    def test_restore_requires_explicit_confirmation_and_changes_nothing(self):
        with self.assertRaisesRegex(RestoreError, "Explicit confirmation"):
            restore_backup(self.root, self.backup_name)
        self.assertTrue(self._has_class(self.active, "CURRENT_DATABASE"))

    def test_valid_backup_restores_and_keeps_pre_restore_copy(self):
        result = restore_backup(self.root, self.backup_name, confirmed=True)
        self.assertTrue(self._has_class(self.active, "RESTORED_DATABASE"))
        self.assertFalse(self._has_class(self.active, "CURRENT_DATABASE"))
        pre_restore = self.backups / result["pre_restore_backup"]
        self.assertTrue(pre_restore.is_file())
        validate_database(pre_restore)
        self.assertTrue(self._has_class(pre_restore, "CURRENT_DATABASE"))

    def test_path_traversal_filename_is_rejected(self):
        with self.assertRaisesRegex(RestoreError, "Invalid backup filename"):
            restore_backup(self.root, "../cbt.db", confirmed=True)
        self.assertTrue(self._has_class(self.active, "CURRENT_DATABASE"))

    def test_corrupt_backup_is_rejected_without_changing_active_database(self):
        self.selected.write_bytes(b"not a sqlite database")
        with self.assertRaises(RestoreError):
            restore_backup(self.root, self.backup_name, confirmed=True)
        self.assertTrue(self._has_class(self.active, "CURRENT_DATABASE"))

    def test_backup_missing_required_table_is_rejected(self):
        conn = sqlite3.connect(self.selected)
        conn.execute("DROP TABLE answers")
        conn.commit()
        conn.close()
        with self.assertRaisesRegex(RestoreError, "missing required tables"):
            validate_database(self.selected)
        self.assertTrue(self._has_class(self.active, "CURRENT_DATABASE"))

    def test_live_exam_attempt_blocks_restore(self):
        conn = sqlite3.connect(self.active)
        conn.execute("INSERT INTO subjects(name) VALUES('Test Subject')")
        subject_id = conn.execute("SELECT id FROM subjects WHERE name='Test Subject'").fetchone()[0]
        conn.execute(
            "INSERT INTO exams(title,subject_id,duration_min,num_questions,status) VALUES(?,?,?,?,?)",
            ("Live exam", subject_id, 30, 1, "live"),
        )
        exam_id = conn.execute("SELECT id FROM exams WHERE title='Live exam'").fetchone()[0]
        conn.execute("INSERT INTO students(reg_no,name,class_id,access_code) VALUES(?,?,?,?)",
                     ("RESTORE001", "Test Student", 1, "123456"))
        student_id = conn.execute("SELECT id FROM students WHERE reg_no='RESTORE001'").fetchone()[0]
        conn.execute("INSERT INTO sessions(exam_id,student_id,status) VALUES(?,?,?)",
                     (exam_id, student_id, "in_progress"))
        conn.commit()
        conn.close()
        with self.assertRaisesRegex(RestoreError, "live exam is still open"):
            restore_backup(self.root, self.backup_name, confirmed=True)
        self.assertTrue(self._has_class(self.active, "CURRENT_DATABASE"))

    def test_wrong_or_incomplete_database_is_rejected(self):
        invalid = self.root / "not-cbt.db"
        conn = sqlite3.connect(invalid)
        conn.execute("CREATE TABLE random_data(value TEXT)")
        conn.commit()
        conn.close()
        with self.assertRaisesRegex(RestoreError, "missing required tables"):
            validate_database(invalid)


    def test_pre_restore_safety_copy_uses_downloadable_filename(self):
        filename = "cbt_20261109_110000_manual_pre_restore_ab12cd34.db"
        shutil.copyfile(self.selected, self.backups / filename)
        gtmc.BK = str(self.backups)
        with self.client.session_transaction() as session:
            session["admin"] = "restore-test-admin"
        response = self.client.get(
            f"/api/admin/backups/{filename}",
            environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)


if __name__ == "__main__":
    unittest.main()
