"""Trusted HTTPS scheme forwarding is limited to configured local proxy IPs."""
import unittest

from app import TrustedLocalProxyScheme


class CaptureApplication:
    def __init__(self):
        self.scheme = None

    def __call__(self, environ, start_response):
        self.scheme = environ.get("wsgi.url_scheme")
        return []


class TrustedLocalProxySchemeTests(unittest.TestCase):
    def setUp(self):
        self.inner = CaptureApplication()
        self.middleware = TrustedLocalProxyScheme(self.inner, ["127.0.0.1", "::1"])

    def invoke(self, remote, forwarded, original="http"):
        environ = {
            "REMOTE_ADDR": remote,
            "HTTP_X_FORWARDED_PROTO": forwarded,
            "wsgi.url_scheme": original,
        }
        self.middleware(environ, lambda status, headers: None)
        return environ["wsgi.url_scheme"]

    def test_loopback_proxy_can_mark_a_request_https(self):
        self.assertEqual(self.invoke("127.0.0.1", "https"), "https")
        self.assertEqual(self.invoke("::1", "https"), "https")

    def test_remote_client_cannot_spoof_https_with_forwarded_header(self):
        self.assertEqual(self.invoke("192.168.1.40", "https"), "http")
        self.assertEqual(self.invoke("203.0.113.12", "https"), "http")

    def test_loopback_proxy_does_not_upgrade_plain_http(self):
        self.assertEqual(self.invoke("127.0.0.1", "http"), "http")

    def test_unconfigured_proxy_cannot_upgrade_scheme(self):
        middleware = TrustedLocalProxyScheme(self.inner, [])
        environ = {
            "REMOTE_ADDR": "127.0.0.1",
            "HTTP_X_FORWARDED_PROTO": "https",
            "wsgi.url_scheme": "http",
        }
        middleware(environ, lambda status, headers: None)
        self.assertEqual(environ["wsgi.url_scheme"], "http")


if __name__ == "__main__":
    unittest.main()
