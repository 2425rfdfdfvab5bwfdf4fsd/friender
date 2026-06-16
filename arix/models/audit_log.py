"""AuditLogEntry and AuditLogger — tamper-resistant, privacy-safe audit trail.

Gap #6: HMAC-chained audit log
- Each entry contains a `chain_hash` that is the HMAC-SHA256 of the previous entry's raw JSON.
- Any post-hoc modification to an earlier entry makes its successor's chain_hash invalid,
  making tampering immediately detectable with verify_chain().
- Env vars matching sensitive patterns are never written to the log.
"""
from __future__ import annotations
import hashlib
import hmac as _hmac
import json
import os
import re
import stat
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Literal, Any

Arix_DIR = Path.home() / ".arix"
AUDIT_LOG_FILE = Arix_DIR / "audit.log"

# Rotating chain-key file — regenerated on first run, stable across sessions
_CHAIN_KEY_FILE = Arix_DIR / ".audit_chain_key"

SECRET_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|apikey|secret|password|token|bearer|auth)[^\s]*\s*[=:]\s*\S+'),
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'sk-[a-zA-Z0-9]{32,}'),
    re.compile(r'ghp_[a-zA-Z0-9]{36}'),
    re.compile(r'xoxb-[0-9-]+'),
    re.compile(r'AIza[0-9A-Za-z_\-]{35}'),
]

_GENESIS_HASH = "0" * 64  # Starting sentinel for the first entry


def _load_or_create_chain_key() -> bytes:
    """Load or create the HMAC key used for chain hashing."""
    Arix_DIR.mkdir(parents=True, exist_ok=True)
    if _CHAIN_KEY_FILE.exists():
        try:
            raw = _CHAIN_KEY_FILE.read_bytes()
            if len(raw) == 32:
                return raw
        except Exception:
            pass
    import secrets
    key = secrets.token_bytes(32)
    _CHAIN_KEY_FILE.write_bytes(key)
    os.chmod(_CHAIN_KEY_FILE, 0o600)
    return key


_EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')


def _redact_email(text: str) -> str:
    return _EMAIL_RE.sub("[REDACTED:email]", text)


def _redact_url(url: str) -> str:
    if '?' in url:
        return url.split('?')[0] + "?[QUERY REDACTED]"
    return url


def _redact_secrets(text: str) -> str:
    for pat in SECRET_PATTERNS:
        text = pat.sub("[REDACTED:<secret>]", text)
    return text


def _compute_entry_hash(chain_key: bytes, raw_json: str) -> str:
    """Compute HMAC-SHA256 of a log entry's raw JSON."""
    return _hmac.new(chain_key, raw_json.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass
class AuditLogEntry:
    schema_version: str = "6.0"
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
    chain_hash: str | None = None  # HMAC of previous entry's raw JSON


class AuditLogger:
    def __init__(self, log_file: Path = AUDIT_LOG_FILE,
                 path_mode: str = "full", retention_days: int = 90):
        self.log_file = log_file
        self.path_mode = path_mode
        self.retention_days = retention_days
        self._chain_key = _load_or_create_chain_key()
        self._last_raw: str = _GENESIS_HASH
        self._ensure_log_file()
        self._load_last_hash()

    def _ensure_log_file(self) -> None:
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_file.exists():
            self.log_file.touch()
        os.chmod(self.log_file, 0o600)

    def _load_last_hash(self) -> None:
        """Read the last entry's raw JSON to prime the chain."""
        try:
            lines = self.log_file.read_text().splitlines()
            for line in reversed(lines):
                line = line.strip()
                if line:
                    self._last_raw = line
                    return
        except Exception:
            pass
        self._last_raw = _GENESIS_HASH

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
                    sanitized[k] = _redact_secrets(_redact_email(v))
            else:
                sanitized[k] = v
        return sanitized

    def log(self, entry: AuditLogEntry) -> None:
        if entry.timestamp == 0.0:
            entry.timestamp = time.time()
        if entry.sanitized_args:
            entry.sanitized_args = self._sanitize_args(entry.sanitized_args)

        # Compute chain hash from previous entry
        entry.chain_hash = _compute_entry_hash(self._chain_key, self._last_raw)

        line = json.dumps(asdict(entry), separators=(",", ":"))
        with open(self.log_file, "a") as f:
            f.write(line + "\n")

        self._last_raw = line

    def log_event(self, task_id: str, step_id: str, event_type: str, **kwargs: Any) -> None:
        entry = AuditLogEntry(
            timestamp=time.time(),
            task_id=task_id,
            step_id=step_id,
            event_type=event_type,
            **kwargs,
        )
        self.log(entry)

    def verify_chain(self) -> dict:
        """Verify the integrity of the audit log chain.

        Returns dict with: valid (bool), total_entries, first_broken_entry (if any).
        """
        if not self.log_file.exists():
            return {"valid": True, "total_entries": 0, "message": "Log file empty"}

        lines = [l.strip() for l in self.log_file.read_text().splitlines() if l.strip()]
        if not lines:
            return {"valid": True, "total_entries": 0}

        prev_raw = _GENESIS_HASH
        for i, line in enumerate(lines):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                return {"valid": False, "total_entries": len(lines),
                        "first_broken_entry": i + 1, "reason": "JSON parse error"}

            stored_hash = entry.get("chain_hash")
            if stored_hash is None and i == 0:
                # Old-format entries without chain hashes — skip
                prev_raw = line
                continue

            expected = _compute_entry_hash(self._chain_key, prev_raw)
            if stored_hash and stored_hash != expected:
                return {
                    "valid": False,
                    "total_entries": len(lines),
                    "first_broken_entry": i + 1,
                    "reason": "Chain hash mismatch — possible tampering detected",
                }
            prev_raw = line

        return {"valid": True, "total_entries": len(lines)}

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
        # Re-prime chain hash after pruning
        self._load_last_hash()
