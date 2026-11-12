"""Regression tests for the Windows-host bootstrap without launching a GUI/server."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import windows_host


class WindowsHostBootstrapTests(unittest.TestCase):
    def test_host_environment_uses_persistent_school_data_and_binds_lan(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp) / "bundle"
            (bundle / "web").mkdir(parents=True)
            with patch.dict(os.environ, {}, clear=False):
                data_dir, web_dir = windows_host.configure_environment(
                    program_data=Path(temp) / "ProgramData",
                    bundle_dir=bundle,
                    host="0.0.0.0",
                    port=8000,
                )
                self.assertTrue(data_dir.is_dir())
                self.assertEqual(web_dir, bundle / "web")
                self.assertEqual(os.environ["CBT_DATA"], str(data_dir.resolve()))
                self.assertEqual(os.environ["CBT_WEB"], str(web_dir.resolve()))
                self.assertEqual(os.environ["CBT_HOST"], "0.0.0.0")
                self.assertEqual(os.environ["CBT_PORT"], "8000")
                self.assertEqual(os.environ["CBT_TRUST_PROXY"], "0")
                self.assertEqual(os.environ["CBT_TRUSTED_PROXY_IPS"], "127.0.0.1,::1")

    def test_missing_bundled_web_assets_fails_safely(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, "web assets"):
                windows_host.configure_environment(
                    program_data=Path(temp) / "ProgramData",
                    bundle_dir=Path(temp) / "missing",
                )

    def test_school_code_is_validated_and_can_be_supplied_by_host_setup(self):
        with patch.dict(os.environ, {"CBT_HOST_SCHOOL_CODE": "vic-a1b2c3d4"}):
            self.assertEqual(windows_host.collect_school_code("VIC-00000000"), "VIC-A1B2C3D4")
        with patch.dict(os.environ, {"CBT_HOST_SCHOOL_CODE": "not-a-school-code"}):
            with self.assertRaisesRegex(ValueError, "VIC-XXXXXXXX"):
                windows_host.collect_school_code("")

    def test_school_name_comes_from_host_setup_or_existing_identity(self):
        with patch.dict(os.environ, {"CBT_HOST_SCHOOL_NAME": "  VICORA Demo School  "}):
            self.assertEqual(windows_host.collect_school_name(""), "VICORA Demo School")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CBT_HOST_SCHOOL_NAME", None)
            self.assertEqual(windows_host.collect_school_name("Existing School"), "Existing School")


if __name__ == "__main__":
    unittest.main()
