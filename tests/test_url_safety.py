"""Tests for browser URL safety checks (SEC-07)."""
import pytest
from pacca.tools.browser_tools import _check_url_safety


@pytest.mark.parametrize("url,expected_safe", [
    # Allowed
    ("https://example.com", True),
    ("https://example.com/path?q=1", True),
    ("http://public.server.com", True),
    # Blocked: private IPv4
    ("http://localhost/", False),
    ("http://127.0.0.1/", False),
    ("http://10.0.0.1/", False),
    ("http://192.168.1.1/", False),
    ("http://172.16.0.1/", False),
    ("http://172.31.255.255/", False),
    ("http://0.0.0.0/", False),
    # Blocked: AWS/GCP metadata IP (SEC-07)
    ("http://169.254.169.254/latest/meta-data/", False),
    ("http://169.254.0.1/", False),
    # Blocked: IPv6 loopback / link-local / ULA (SEC-07)
    ("http://[::1]/", False),
    ("http://[fe80::1]/", False),
    ("http://[fc00::1]/", False),
    ("http://[fd00::1]/", False),
    # Blocked: credentials embedded in URL (SEC-07)
    ("https://user:password@example.com/", False),
    # Blocked: non-HTTP schemes
    ("file:///etc/passwd", False),
    ("data:text/html,<script>alert(1)</script>", False),
    ("javascript:alert(1)", False),
    # Blocked: payment URLs
    ("https://stripe.com/pay/session_123", False),
    # Blocked: empty URL
    ("", False),
])
def test_url_safety(url, expected_safe):
    safe, reason = _check_url_safety(url)
    assert safe == expected_safe, f"URL {url!r}: expected safe={expected_safe}, got safe={safe} ({reason!r})"
