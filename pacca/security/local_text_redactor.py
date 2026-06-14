"""LocalTextRedactor — deterministic offline redaction of sensitive patterns."""
from __future__ import annotations
import re
import time
from dataclasses import dataclass
from typing import NamedTuple

REDACTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("openai_api_key", re.compile(r'sk-[a-zA-Z0-9]{20,}')),
    ("anthropic_api_key", re.compile(r'sk-ant-[a-zA-Z0-9\-_]{20,}')),
    ("aws_access_key", re.compile(r'AKIA[0-9A-Z]{16}')),
    ("aws_secret_key", re.compile(r'(?i)aws.{0,20}secret.{0,20}[=:]\s*[A-Za-z0-9/+]{40}')),
    ("github_token", re.compile(r'gh[ps]_[a-zA-Z0-9]{36}')),
    ("slack_token", re.compile(r'xox[boas]-[0-9A-Za-z\-]+')),
    ("google_api_key", re.compile(r'AIza[0-9A-Za-z\-_]{35}')),
    ("generic_api_key", re.compile(r'(?i)(api[_-]?key|apikey)\s*[=:]\s*[\'"]?([A-Za-z0-9\-_]{16,})[\'"]?')),
    ("generic_password", re.compile(r'(?i)(password|passwd|pwd)\s*[=:]\s*[\'"]?(\S{8,})[\'"]?')),
    ("generic_secret", re.compile(r'(?i)(secret|token|bearer)\s*[=:]\s*[\'"]?([A-Za-z0-9\-_]{16,})[\'"]?')),
    ("private_key_header", re.compile(r'-----BEGIN [A-Z ]+PRIVATE KEY-----')),
    ("email_address", re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')),
    ("credit_card", re.compile(r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b')),
    ("ssn", re.compile(r'\b\d{3}-\d{2}-\d{4}\b')),
]

SECRET_PATTERNS = REDACTION_PATTERNS


class RedactionResult(NamedTuple):
    original: str
    redacted: str
    patterns_matched: list[str]
    latency_ms: float


class LocalTextRedactor:
    """
    Deterministic, offline, regex-based redaction.
    Applied to command text and file/page/diff excerpts before any cloud call.
    Latency target: < 10ms (p95) for command text.
    """

    def __init__(self, patterns: list[tuple[str, re.Pattern]] = REDACTION_PATTERNS):
        self.patterns = patterns

    def redact(self, text: str) -> RedactionResult:
        t0 = time.monotonic()
        redacted = text
        matched: list[str] = []
        for name, pattern in self.patterns:
            new = pattern.sub(f"[REDACTED:{name}]", redacted)
            if new != redacted:
                matched.append(name)
                redacted = new
        latency_ms = (time.monotonic() - t0) * 1000
        return RedactionResult(
            original=text,
            redacted=redacted,
            patterns_matched=matched,
            latency_ms=latency_ms,
        )

    def redact_text(self, text: str) -> str:
        return self.redact(text).redacted

    def truncate_for_egress(self, text: str,
                            max_bytes: int = 32_768) -> tuple[str, bool]:
        encoded = text.encode("utf-8")
        if len(encoded) <= max_bytes:
            return text, False
        truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
        return truncated, True

    def prepare_for_egress(self, text: str,
                           max_bytes: int = 32_768) -> tuple[str, bool, list[str]]:
        result = self.redact(text)
        truncated_text, was_truncated = self.truncate_for_egress(
            result.redacted, max_bytes
        )
        if was_truncated:
            truncated_text += "\n[TRUNCATED — content exceeded egress limit]"
        return truncated_text, was_truncated, result.patterns_matched
