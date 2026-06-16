"""Tests for email redaction in AuditLogger (SEC-08)."""
import pytest
from arix.models.audit_log import AuditLogger, _redact_email

_MARKER = "[REDACTED:email]"


def test_redact_email_basic():
    result = _redact_email("Send to user@example.com please")
    assert "user@example.com" not in result
    assert _MARKER in result


def test_redact_email_multiple():
    result = _redact_email("From a@b.com to c@d.org")
    assert "a@b.com" not in result
    assert "c@d.org" not in result
    assert result.count(_MARKER) == 2


def test_redact_email_preserves_non_email():
    result = _redact_email("Hello world, no emails here")
    assert result == "Hello world, no emails here"


def test_redact_email_in_args():
    logger = AuditLogger()
    sanitized = logger._sanitize_args({
        "recipient": "victim@target.com",
        "subject": "Hello",
        "count": 42,
    })
    assert "victim@target.com" not in str(sanitized)
    assert _MARKER in str(sanitized)
    assert sanitized["subject"] == "Hello"
    assert sanitized["count"] == 42
