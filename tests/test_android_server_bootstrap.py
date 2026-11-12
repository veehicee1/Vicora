"""Unit tests for the Android embedded host bootstrap (no device required)."""
import importlib
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

PYTHON_DIR = Path(__file__).resolve().parents[1] / "android" / "app" / "src" / "main" / "python"
sys.path.insert(0, str(PYTHON_DIR))
import android_server


class FakeServer:
    def __init__(self):
        self.stopped = threading.Event()
        self.closed = threading.Event()

    def serve_forever(self):
        self.stopped.wait(5)

    def shutdown(self):
        self.stopped.set()

    def server_close(self):
        self.closed.set()


class FakeResult:
    def __init__(self, row=None):
        self.row = row
    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self):
        self.executed = []
    def execute(self, sql, values=()):
        self.executed.append((sql, values))
        if "SELECT school_id,school_code FROM schools" in sql:
            return FakeResult({"school_id": "legacy-school", "school_code": "VIC-11112222"})
        return FakeResult()
    def commit(self):
        pass
    def close(self):
        pass


class FakeBackend:
    app = object()

    def __init__(self):
        self.worker_starts = 0
        self.connection = FakeConnection()

    def raw(self):
        return self.connection

    def start_background(self):
        self.worker_starts += 1


class AndroidServerBootstrapTests(unittest.TestCase):
    def setUp(self):
        android_server._server = None
        android_server._server_thread = None
        android_server._server_host = None
        android_server._server_port = None
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
        android_server._server_host = None
        android_server._server_port = None
        android_server._worker_started = False
        self.temp.cleanup()

    def test_host_bootstrap_sets_private_paths_before_import_and_binds_lan(self):
        with patch.dict(os.environ, {}, clear=False), \
             patch("werkzeug.serving.make_server", return_value=self.server) as make_server, \
             patch.object(importlib, "import_module", return_value=self.backend) as importer, \
             patch.object(android_server, "health_check", return_value=True):
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

    def test_switching_from_offline_loopback_to_host_mode_rebinds_lan(self):
        second_server = FakeServer()
        with patch.dict(os.environ, {}, clear=False), \
             patch("werkzeug.serving.make_server", side_effect=[self.server, second_server]) as make_server, \
             patch.object(importlib, "import_module", return_value=self.backend), \
             patch.object(android_server, "health_check", return_value=True):
            offline = android_server.start_server(self.data_dir, self.web_dir, "127.0.0.1", 8765)
            self.assertEqual(offline["host"], "127.0.0.1")
            hosted = android_server.start_server(self.data_dir, self.web_dir, "0.0.0.0", 8765)
            self.assertEqual(hosted["host"], "0.0.0.0")
            self.assertFalse(hosted["already_running"])
            self.assertTrue(self.server.stopped.is_set())
            self.assertTrue(self.server.closed.is_set())
            self.assertEqual(make_server.call_count, 2)
            self.assertEqual(android_server._server_host, "0.0.0.0")
    def test_explicit_stop_closes_lan_listener(self):
        with patch.dict(os.environ, {}, clear=False), \
             patch("werkzeug.serving.make_server", return_value=self.server), \
             patch.object(importlib, "import_module", return_value=self.backend), \
             patch.object(android_server, "health_check", return_value=True):
            android_server.start_server(self.data_dir, self.web_dir, "0.0.0.0", 8765)
            result = android_server.stop_server()
            self.assertTrue(result["ok"])
            self.assertFalse(result["already_stopped"])
            self.assertTrue(self.server.stopped.is_set())
            self.assertTrue(self.server.closed.is_set())
            self.assertIsNone(android_server._server)
            self.assertIsNone(android_server._server_thread)
            self.assertEqual(android_server._server_host, None)

    def test_health_check_uses_readiness_endpoint_and_requires_ready_database(self):
        response = MagicMock()
        response.status = 200
        response.read.return_value = b'{"ok":true,"database":"ready"}'
        response.__enter__.return_value = response
        with patch("urllib.request.urlopen", return_value=response) as open_url:
            self.assertTrue(android_server.health_check("127.0.0.1", 8765))
        self.assertIn("/api/health", open_url.call_args.args[0].full_url)

    def test_missing_web_assets_fails_before_starting_backend(self):
        missing = os.path.join(self.temp.name, "missing-web")
        with patch.object(importlib, "import_module") as importer:
            with self.assertRaisesRegex(RuntimeError, "web interface"):
                android_server.start_server(self.data_dir, missing)
            importer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
