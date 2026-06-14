"""AuditLogEntry and AuditLogger — tamper-resistant, privacy-safe audit trail."""
from __future__ import annotations
import hashlib
import json
import os
import re
import stat
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Literal, Any

PACCA_DIR = Path.home() / ".pacca"
AUDIT_LOG_FILE = PACCA_DIR / "audit.log"

SECRET_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|apikey|secret|password|token|bearer|auth)[^\s]*\s*[=:]\s*\S+'),
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'sk-[a-zA-Z0-9]{32,}'),
    re.compile(r'ghp_[a-zA-Z0-9]{36}'),
    re.compile(r'xoxb-[0-9-]+'),
]


def _redact_url(url: str) -> str:
    """Strip query string from URL for audit log."""
    if '?' in url:
        return url.split('?')[0] + "?[QUERY REDACTED]"
    return url


def _redact_secrets(text: str) -> str:
    for pat in SECRET_PATTERNS:
        text = pat.sub("[REDACTED:<secret>]", text)
    return text


@dataclass
class AuditLogEntry:
    schema_version: str = "5.2"
    timestamp: float = 0.0
    task_id: str = ""
    step_id: str = ""
    event_type: str = ""
    tool_name: str | None = None
    sanitized_args: dict | None = None
    result_summary: str | None = None
    state_from: str | None = None
    state_to: str | None = None
    grant_id: str | None = None
    data_egress: bool = False
    egress_provider: str | None = None
    cumulative_risk_score: float | None = None
    task_scope_digest: str | None = None
    confirmation_receipt_id: str | None = None
    command_redacted: str | None = None
    error: str | None = None


class AuditLogger:
    def __init__(self, log_file: Path = AUDIT_LOG_FILE,
                 path_mode: str = "full", retention_days: int = 90):
        self.log_file = log_file
        self.path_mode = path_mode
        self.retention_days = retention_days
        self._ensure_log_file()

    def _ensure_log_file(self) -> None:
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_file.exists():
            self.log_file.touch()
        os.chmod(self.log_file, 0o600)

    def _sanitize_path(self, path: str) -> str:
        if self.path_mode == "hash":
            return hashlib.sha256(path.encode()).hexdigest()[:16]
        elif self.path_mode == "basename":
            return os.path.basename(path)
        elif self.path_mode == "omit":
            return "[PATH OMITTED]"
        return path

    def _sanitize_args(self, args: dict) -> dict:
        sanitized = {}
        for k, v in args.items():
            if isinstance(v, str):
                if any(cred in k.lower() for cred in ["password", "key", "token", "secret"]):
                    sanitized[k] = "[REDACTED]"
                elif k in ("path", "source", "destination", "src", "dst", "file_path"):
                    sanitized[k] = self._sanitize_path(v)
                elif k == "url":
                    sanitized[k] = _redact_url(v)
                elif k == "content":
                    sanitized[k] = f"[CONTENT OMITTED — {len(v)} bytes]"
                else:
                    sanitized[k] = _redact_secrets(v)
            else:
                sanitized[k] = v
        return sanitized

    def log(self, entry: AuditLogEntry) -> None:
        if entry.timestamp == 0.0:
            entry.timestamp = time.time()
        if entry.sanitized_args:
            entry.sanitized_args = self._sanitize_args(entry.sanitized_args)
        line = json.dumps(asdict(entry), separators=(",", ":"))
        with open(self.log_file, "a") as f:
            f.write(line + "\n")

    def log_event(self, task_id: str, step_id: str, event_type: str, **kwargs: Any) -> None:
        entry = AuditLogEntry(
            timestamp=time.time(),
            task_id=task_id,
            step_id=step_id,
            event_type=event_type,
            **kwargs,
        )
        self.log(entry)

    def prune_old_entries(self) -> None:
        cutoff = time.time() - (self.retention_days * 86400)
        if not self.log_file.exists():
            return
        lines = self.log_file.read_text().splitlines()
        kept = []
        for line in lines:
            try:
                entry = json.loads(line)
                if entry.get("timestamp", 0) >= cutoff:
                    kept.append(line)
            except Exception:
                kept.append(line)
        self.log_file.write_text("\n".join(kept) + ("\n" if kept else ""))
