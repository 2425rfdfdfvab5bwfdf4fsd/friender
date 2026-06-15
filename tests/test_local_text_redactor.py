"""Tests for LocalTextRedactor — ensures secrets are stripped before LLM egress."""
import pytest
from pacca.security.local_text_redactor import LocalTextRedactor, REDACTION_PATTERNS


@pytest.fixture
def redactor():
    return LocalTextRedactor()


class TestAPIKeyRedaction:
    def test_openai_key(self, redactor):
        result = redactor.redact_text("key=sk-abcdefghijklmnopqrstuvwxyz123456")
        assert "sk-abcdefghijklmnopqrstuvwxyz" not in result
        assert "[REDACTED:openai_api_key]" in result

    def test_anthropic_key(self, redactor):
        text = "export ANTHROPIC=sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAA12345678901234"
        result = redactor.redact_text(text)
        assert "sk-ant-api03" not in result
        assert "[REDACTED:anthropic_api_key]" in result

    def test_aws_access_key(self, redactor):
        result = redactor.redact_text("AWS_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE_OK")
        assert "AKIAIOSFODNN7EXAMPLE" not in result

    def test_github_token(self, redactor):
        result = redactor.redact_text("token=ghp_ABCDE12345FGHIJ67890KLMNO12345678901")
        assert "ghp_ABCDE12345" not in result
        assert "[REDACTED:github_token]" in result

    def test_google_api_key(self, redactor):
        result = redactor.redact_text("key=AIzaSyABC123DEF456GHI789JKL012MNO345PQR")
        assert "AIzaSyABC123" not in result


class TestPasswordRedaction:
    def test_password_equals(self, redactor):
        result = redactor.redact_text("password=SuperSecret123!")
        assert "SuperSecret123" not in result
        assert "REDACTED" in result

    def test_password_colon(self, redactor):
        result = redactor.redact_text("pwd: MySecurePass99")
        assert "MySecurePass99" not in result


class TestPIIRedaction:
    def test_email_address(self, redactor):
        result = redactor.redact_text("Send to alice@example.com now")
        assert "alice@example.com" not in result
        assert "[REDACTED:email_address]" in result

    def test_credit_card_visa(self, redactor):
        result = redactor.redact_text("card: 4111111111111111")
        assert "4111111111111111" not in result

    def test_ssn(self, redactor):
        result = redactor.redact_text("SSN: 123-45-6789")
        assert "123-45-6789" not in result

    def test_private_key_header(self, redactor):
        result = redactor.redact_text("-----BEGIN RSA PRIVATE KEY-----")
        assert "BEGIN RSA PRIVATE KEY" not in result


class TestPreservesNonSensitive:
    def test_plain_text_unchanged(self, redactor):
        text = "list files in /home/user/documents"
        assert redactor.redact_text(text) == text

    def test_matched_patterns_reported(self, redactor):
        result = redactor.redact("password=abc12345678 and key=sk-abcdefghijklmnop12345")
        assert len(result.patterns_matched) >= 1

    def test_latency_under_50ms(self, redactor):
        import time
        text = "list files in ~/Documents and then open browser to https://example.com" * 20
        t0 = time.monotonic()
        redactor.redact(text)
        elapsed_ms = (time.monotonic() - t0) * 1000
        assert elapsed_ms < 50, f"Redaction took {elapsed_ms:.1f}ms — too slow"


class TestEgressPreparation:
    def test_truncation(self, redactor):
        long_text = "x" * 100_000
        truncated, was_truncated = redactor.truncate_for_egress(long_text, max_bytes=1000)
        assert was_truncated
        assert len(truncated.encode()) <= 1000 + 100  # slight slack for marker

    def test_no_truncation_small(self, redactor):
        text = "hello world"
        result, was_truncated = redactor.truncate_for_egress(text, max_bytes=1000)
        assert not was_truncated
        assert result == text

    def test_prepare_for_egress_combines(self, redactor):
        text = "my key=sk-abcdefghijklmnopqrstuvwxyz123456 " + "data " * 5000
        result_text, was_truncated, matched = redactor.prepare_for_egress(text, max_bytes=500)
        assert "sk-abcdefghijklmnop" not in result_text
        assert "openai_api_key" in matched
