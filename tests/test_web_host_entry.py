"""Browser entry-point checks for the shared VICORA web examination client."""
import os
import tempfile
import unittest

# Keep this test isolated from any real school database.
os.environ.setdefault("CBT_DATA", tempfile.mkdtemp(prefix="vicora-web-host-entry-"))

import app as cbt  # noqa: E402


class WebHostEntryTests(unittest.TestCase):
    def setUp(self):
        cbt.app.config.update(TESTING=True)
        self.client = cbt.app.test_client()

    def test_browser_entry_points_serve_the_same_examination_client(self):
        root = self.client.get("/")
        home = self.client.get("/home")
        self.assertEqual(root.status_code, 200)
        self.assertEqual(home.status_code, 200)
        self.assertIn(b"function api(p,body,method)", root.data)
        self.assertIn(b"fetch('/api/student'", root.data)
        self.assertIn(b"fetch('/api/public/info')", root.data)
        self.assertEqual(root.data, home.data)

    def test_public_school_identity_is_available_to_the_web_client(self):
        response = self.client.get("/api/public/info")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload.get("school"))
        self.assertEqual(payload.get("school_logo_url"), "/api/public/school-logo")
        self.assertIsInstance(payload.get("theme"), dict)


if __name__ == "__main__":
    unittest.main()
