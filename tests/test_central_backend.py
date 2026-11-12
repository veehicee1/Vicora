import json
import os
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask
from central_backend import install_central_backend_routes


class CentralBackendBridgeTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.testing = True
        install_central_backend_routes(
            self.app,
            lambda message, code=400: (__import__("flask").jsonify(error=message), code),
        )
        self.client = self.app.test_client()
        self.url = "https://script.google.com/macros/s/test-deployment-id/exec"

    def _response(self, payload, status=200):
        response = MagicMock()
        response.status = status
        response.read.return_value = json.dumps(payload).encode("utf-8")
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        return response

    def test_health_reports_connected_when_apps_script_is_healthy(self):
        with patch.dict(os.environ, {"VICORA_CENTRAL_APPS_SCRIPT_URL": self.url}):
            with patch("central_backend.urllib.request.urlopen", return_value=self._response({
                "ok": True, "service": "VICORA Central Apps Script API", "version": "1.0.0"
            })) as call:
                response = self.client.get("/api/central/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["connected"])
        self.assertIn("action=health", call.call_args.args[0].full_url)

    def test_health_fails_closed_when_url_is_not_configured(self):
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.get("/api/central/health")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.get_json()["connected"])

    def test_public_school_application_is_forwarded_without_admin_secret(self):
        upstream = {"ok": True, "data": {"applicationId": "app-1", "status": "pending"}}
        with patch.dict(os.environ, {"VICORA_CENTRAL_APPS_SCRIPT_URL": self.url}):
            with patch("central_backend.urllib.request.urlopen", return_value=self._response(upstream)) as call:
                response = self.client.post("/api/central/request", json={
                    "action": "applySchool", "schoolName": "Sample School",
                    "contactName": "School Admin", "contactEmail": "admin@example.com",
                    "contactPhone": "08012345678"
                })
        self.assertEqual(response.status_code, 200)
        sent = json.loads(call.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(sent["action"], "applySchool")
        self.assertNotIn("adminKey", sent)

    def test_platform_admin_action_is_not_available_on_public_endpoint(self):
        response = self.client.post("/api/central/request", json={
            "action": "admin.listApplications"
        })
        self.assertEqual(response.status_code, 403)

    def test_admin_key_is_added_only_server_side(self):
        upstream = {"ok": True, "data": []}
        with patch.dict(os.environ, {
            "VICORA_CENTRAL_APPS_SCRIPT_URL": self.url,
            "VICORA_CENTRAL_ADMIN_KEY": "server-only-test-key"
        }):
            with patch("central_backend.urllib.request.urlopen", return_value=self._response(upstream)) as call:
                response = self.client.post("/api/central/admin", json={
                    "action": "admin.listApplications"
                })
        self.assertEqual(response.status_code, 200)
        sent = json.loads(call.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(sent["adminKey"], "server-only-test-key")


if __name__ == "__main__":
    unittest.main()
