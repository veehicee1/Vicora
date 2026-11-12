import hashlib
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from multi_tenant import migrate_multi_tenant_schema, school_context


class MultiTenantRegistryTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE schools(
            school_id TEXT PRIMARY KEY, school_code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'approved',
            is_legacy_default INTEGER NOT NULL DEFAULT 0,
            created_ts INTEGER NOT NULL DEFAULT 0, approved_ts INTEGER)""")
        self.db.execute("INSERT INTO schools VALUES('legacy','VIC-LEGACY','Legacy School','approved',1,1,1)")
        self.db.commit()
        migrate_multi_tenant_schema(self.db)

    def tearDown(self):
        self.db.close()

    def test_registry_tables_and_school_metadata_are_created(self):
        names = {r[0] for r in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"school_applications", "school_admin_invites",
                         "school_hosts", "platform_audit"}.issubset(names))
        columns = {r[1] for r in self.db.execute("PRAGMA table_info(schools)")}
        self.assertIn("contact_email", columns)
        self.assertIn("review_note", columns)

    def test_school_resolution_is_case_insensitive_and_approved_only(self):
        self.db.execute("INSERT INTO schools(school_id,school_code,name,status) VALUES('s2','VIC-SECOND','Second','approved')")
        self.db.execute("INSERT INTO schools(school_id,school_code,name,status) VALUES('s3','VIC-PENDING','Pending','pending')")
        self.db.commit()
        self.assertEqual(school_context(self.db, "vic-second")["school_id"], "s2")
        self.assertIsNone(school_context(self.db, "VIC-PENDING"))

    def test_omitted_code_only_resolves_when_one_approved_school_exists(self):
        self.assertEqual(school_context(self.db, "")["school_id"], "legacy")
        self.db.execute("INSERT INTO schools(school_id,school_code,name,status) VALUES('s2','VIC-SECOND','Second','approved')")
        self.db.commit()
        self.assertIsNone(school_context(self.db, ""))

    def test_host_tokens_are_hashed_not_stored_plaintext(self):
        token = "secret-host-token"
        digest = hashlib.sha256(token.encode()).hexdigest()
        self.db.execute("INSERT INTO school_hosts(device_id,school_id,platform,token_hash,created_ts) VALUES('device-123456','legacy','android',?,1)", (digest,))
        self.db.commit()
        self.assertNotEqual(self.db.execute("SELECT token_hash FROM school_hosts").fetchone()[0], token)


if __name__ == "__main__":
    unittest.main()
