"""Unit tests for the Android embedded host bootstrap (no device required)."""
import importlib
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

PYTHON_DIR = Path(__file__).resolve().parents[1] / "android" / "app" / "src" / "main" / "python"
sys.path.insert(0, str(PYTHON_DIR))
import android_server


class FakeServer:
    def __init__(self):
        self.stopped = threading.Event()

    def serve_forever(self):
        self.stopped.wait(5)

    def shutdown(self):
        self.stopped.set()


class FakeBackend:
    app = object()

    def __init__(self):
        self.worker_starts = 0

    def start_background(self):
        self.worker_starts += 1


class AndroidServerBootstrapTests(unittest.TestCase):
    def setUp(self):
        android_server._server = None
        android_server._server_thread = None
        android_server._worker_started = False
        self.temp = tempfile.TemporaryDirectory()
        self.data_dir = os.path.join(self.temp.name, "private-data")
        self.web_dir = os.path.join(self.temp.name, "web")
        os.makedirs(self.web_dir)
        self.backend = FakeBackend()
        self.server = FakeServer()

    def tearDown(self):
        if android_server._server is not None:
            android_server._server.shutdown()
        if android_server._server_thread is not None:
            android_server._server_thread.join(timeout=2)
        android_server._server = None
        android_server._server_thread = None
        android_server._worker_started = False
        self.temp.cleanup()

    def test_host_bootstrap_sets_private_paths_before_import_and_binds_lan(self):
        with patch.dict(os.environ, {}, clear=False), \
             patch("werkzeug.serving.make_server", return_value=self.server) as make_server, \
             patch.object(importlib, "import_module", return_value=self.backend) as importer:
            result = android_server.start_server(self.data_dir, self.web_dir, "0.0.0.0", 8765, "VICORA Demo School")

            self.assertEqual(result["port"], 8765)
            self.assertFalse(result["already_running"])
            self.assertEqual(os.environ["CBT_DATA"], self.data_dir)
            self.assertEqual(os.environ["CBT_WEB"], self.web_dir)
            self.assertEqual(os.environ["CBT_HOST"], "0.0.0.0")
            self.assertEqual(os.environ["CBT_PORT"], "8765")
            self.assertEqual(os.environ["CBT_INITIAL_SCHOOL_NAME"], "VICORA Demo School")
            importer.assert_called_once_with("app")
            make_server.assert_called_once_with("0.0.0.0", 8765, self.backend.app, threaded=True)
            self.assertEqual(self.backend.worker_starts, 1)

            again = android_server.start_server(self.data_dir, self.web_dir, "0.0.0.0", 8765)
            self.assertTrue(again["already_running"])
            self.assertEqual(self.backend.worker_starts, 1)
            make_server.assert_called_once()

    def test_missing_web_assets_fails_before_starting_backend(self):
        missing = os.path.join(self.temp.name, "missing-web")
        with patch.object(importlib, "import_module") as importer:
            with self.assertRaisesRegex(RuntimeError, "web interface"):
                android_server.start_server(self.data_dir, missing)
            importer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
