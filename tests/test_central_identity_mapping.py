import sqlite3
import unittest

from central_backend import _ensure_local_admin, _ensure_local_school


class CentralIdentityMappingTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE schools (
                school_id TEXT PRIMARY KEY, school_code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL, status TEXT NOT NULL,
                is_legacy_default INTEGER NOT NULL, created_ts INTEGER NOT NULL,
                approved_ts INTEGER, contact_email TEXT DEFAULT '',
                contact_phone TEXT DEFAULT '', country TEXT DEFAULT 'Nigeria',
                address TEXT DEFAULT '', website TEXT DEFAULT ''
            );
            CREATE TABLE admins (
                id INTEGER PRIMARY KEY, username TEXT UNIQUE,
                password_hash TEXT, role TEXT NOT NULL,
                active INTEGER NOT NULL, school_id TEXT
            );
        """)

    def tearDown(self):
        self.db.close()

    def test_central_school_identity_is_mirrored_without_changing_legacy_rows(self):
        self.db.execute(
            "INSERT INTO schools VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            ("legacy-id", "VIC-LEGACY1", "Legacy School", "approved", 1,
             1, 1, "", "", "Nigeria", "", "")
        )
        school_id = _ensure_local_school(self.db, {
            "schoolId": "central-id", "schoolCode": "VIC-ABC12345",
            "name": "Central School", "status": "approved", "country": "Nigeria"
        })
        self.assertEqual(school_id, "central-id")
        self.assertEqual(
            self.db.execute("SELECT school_code FROM schools WHERE school_id='legacy-id'").fetchone()[0],
            "VIC-LEGACY1"
        )
        self.assertEqual(
            self.db.execute("SELECT school_code FROM schools WHERE school_id='central-id'").fetchone()[0],
            "VIC-ABC12345"
        )

    def test_central_admin_maps_to_local_super_admin_without_reusing_password(self):
        school_id = _ensure_local_school(self.db, {
            "schoolId": "central-id", "schoolCode": "VIC-ABC12345",
            "name": "Central School", "status": "approved"
        })
        user = {
            "userId": "central-user-1", "email": "principal@example.com",
            "name": "Principal", "role": "school_admin"
        }
        username = _ensure_local_admin(self.db, school_id, user)
        local = self.db.execute(
            "SELECT username,password_hash,role,active,school_id FROM admins WHERE username=?",
            (username,)
        ).fetchone()
        mapping = self.db.execute(
            "SELECT email,central_role FROM central_user_map WHERE central_user_id='central-user-1'"
        ).fetchone()
        self.assertEqual(local["role"], "super_admin")
        self.assertEqual(local["active"], 1)
        self.assertEqual(local["school_id"], school_id)
        self.assertNotEqual(local["password_hash"], "principal-password")
        self.assertEqual(mapping["email"], "principal@example.com")
        self.assertEqual(mapping["central_role"], "school_admin")
        self.assertEqual(_ensure_local_admin(self.db, school_id, user), username)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM admins").fetchone()[0], 1)

    def test_duplicate_school_code_cannot_be_mapped_to_another_central_id(self):
        _ensure_local_school(self.db, {
            "schoolId": "central-id-1", "schoolCode": "VIC-ABC12345",
            "name": "First School", "status": "approved"
        })
        with self.assertRaises(RuntimeError):
            _ensure_local_school(self.db, {
                "schoolId": "central-id-2", "schoolCode": "VIC-ABC12345",
                "name": "Second School", "status": "approved"
            })


if __name__ == "__main__":
    unittest.main()
