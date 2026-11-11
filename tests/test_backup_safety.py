"""Regression tests for the local SQLite backup safety baseline.

All data is isolated in a temporary CBT_DATA directory. These tests never open
or modify a real school database.
"""
import os
import sqlite3
import tempfile
import unittest

os.environ.setdefault("CBT_DATA", tempfile.mkdtemp(prefix="gtmc-backup-tests-"))

import app as gtmc  # noqa: E402


class BackupSafetyTests(unittest.TestCase):
    def setUp(self):
        gtmc.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = gtmc.app.test_client()
        with self.client.session_transaction() as sess:
            sess["admin"] = "admin"

    def _seed_test_record(self):
        conn = gtmc.raw()
        conn.execute("INSERT OR IGNORE INTO classes(name) VALUES(?)", ("BACKUP_TEST_CLASS",))
        conn.commit()
        conn.close()

    def test_manual_backup_is_created_and_is_a_valid_sqlite_database(self):
        self._seed_test_record()
        filename = gtmc.do_backup("manual")
        path = os.path.join(gtmc.BK, filename)
        self.assertTrue(os.path.isfile(path))
        conn = sqlite3.connect(path)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
            self.assertEqual(result, "ok")
            row = conn.execute(
                "SELECT name FROM classes WHERE name=?", ("BACKUP_TEST_CLASS",)
            ).fetchone()
            self.assertIsNotNone(row)
        finally:
            conn.close()

    def test_admin_can_create_and_list_manual_backup(self):
        response = self.client.post(
            "/api/admin/backups",
            environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
        )
        self.assertEqual(response.status_code, 200)
        filename = response.get_json()["name"]
        self.assertTrue(filename.endswith("_manual.db"))

        listing = self.client.get(
            "/api/admin/backups",
            environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
        )
        self.assertEqual(listing.status_code, 200)
        self.assertIn(filename, [item["name"] for item in listing.get_json()])

    def test_admin_can_download_created_backup(self):
        filename = gtmc.do_backup("manual")
        response = self.client.get(
            f"/api/admin/backups/{filename}",
            environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)

    def test_backup_download_rejects_untrusted_filename(self):
        response = self.client.get(
            "/api/admin/backups/../../cbt.db",
            environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
        )
        self.assertIn(response.status_code, (400, 404))


if __name__ == "__main__":
    unittest.main()
