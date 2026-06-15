"""PACCA configuration — loaded from ~/.pacca/config.json and environment."""
from __future__ import annotations
import json
import os
import secrets
from dataclasses import dataclass, asdict, field
from pathlib import Path

PACCA_DIR = Path.home() / ".pacca"
CONFIG_FILE = PACCA_DIR / "config.json"


@dataclass
class PACCAConfig:
    provider: str = "anthropic"
    model: str = "claude-opus-4-5"
    sanitizer_provider: str = "anthropic"
    sanitizer_model: str = "claude-haiku-4-5"
    gemini_default_model: str = "gemini-2.0-flash"
    max_steps: int = 30
    risk_proceed_threshold: float = 30.0
    risk_confirm_threshold: float = 100.0
    max_file_egress_bytes: int = 32_768
    audit_log_path_mode: str = "full"
    audit_log_retention_days: int = 90
    audit_log_encryption_enabled: bool = False
    archive_max_files: int = 1000
    archive_max_bytes: int = 500_000_000
    archive_max_ratio: float = 100.0
    archive_allow_symlinks: bool = False
    archive_allow_hardlinks: bool = False
    allowed_path_prefixes: list[str] = field(default_factory=list)
    offline_mode: bool = False
    dry_run_mode: bool = False
    show_egress_notices: bool = True
    grant_ttl_seconds: int = 300
    browser_headless: bool = True

    @classmethod
    def load(cls) -> "PACCAConfig":
        cfg = cls()
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    data = json.load(f)
                for k, v in data.items():
                    if hasattr(cfg, k):
                        setattr(cfg, k, v)
            except Exception:
                pass

        if not cfg.allowed_path_prefixes:
            home = str(Path.home())
            cwd = os.getcwd()
            cfg.allowed_path_prefixes = list({home, cwd, str(PACCA_DIR)})

        # Replit AI Integrations for Anthropic — takes priority over all other keys
        if os.environ.get("AI_INTEGRATIONS_ANTHROPIC_API_KEY"):
            cfg.provider = "anthropic"
            # Use a supported integration model; upgrade if the saved model is an older alias
            _INTEGRATION_MODELS = {
                "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6",
                "claude-opus-4-5", "claude-opus-4-1",
                "claude-sonnet-4-6", "claude-sonnet-4-5", "claude-haiku-4-5",
            }
            if cfg.model not in _INTEGRATION_MODELS:
                cfg.model = "claude-sonnet-4-5"
            return cfg

        # Auto-switch provider to match whichever key is actually present
        key_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gemini": "GEMINI_API_KEY",
        }
        if not os.environ.get(key_map.get(cfg.provider, "")):
            for prov, env in key_map.items():
                if os.environ.get(env):
                    cfg.provider = prov
                    if prov == "gemini":
                        cfg.model = cfg.gemini_default_model
                    elif prov == "openai":
                        cfg.model = "gpt-4o"
                    break

        return cfg

    def save(self) -> None:
        PACCA_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(asdict(self), f, indent=2)
        os.chmod(CONFIG_FILE, 0o600)


_GRANT_SECRET_KEY: bytes | None = None


def get_grant_secret_key() -> bytes:
    global _GRANT_SECRET_KEY
    if _GRANT_SECRET_KEY is None:
        _GRANT_SECRET_KEY = secrets.token_bytes(32)
    return _GRANT_SECRET_KEY
