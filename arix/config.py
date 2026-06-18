"""Arix configuration — loaded from ~/.arix/config.json and environment."""
from __future__ import annotations
import json
import os
import secrets
from dataclasses import dataclass, asdict, field
from pathlib import Path

Arix_DIR = Path.home() / ".arix"
CONFIG_FILE = Arix_DIR / "config.json"


@dataclass
class ArixConfig:
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
    tool_timeout_seconds: int = 60
    require_auth: bool = False
    allowed_ws_origins: list[str] = field(default_factory=list)  # empty = allow all origins
    api_rate_limit_per_minute: int = 120
    ws_command_rate_limit_per_minute: int = 20

    @classmethod
    def load(cls) -> "ArixConfig":
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
            cfg.allowed_path_prefixes = list({home, cwd, str(Arix_DIR), "/tmp", "/var/tmp"})

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

        # Auto-switch provider to match whichever key is actually present and valid
        def _key_valid(prov: str, val: str) -> bool:
            if not val:
                return False
            if prov == "gemini" and not val.startswith("AIza"):
                return False  # OAuth token, not an AI Studio key
            return True

        # Priority-ordered provider → env-var map (includes all 13 providers)
        key_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "groq": "GROQ_API_KEY",
            "together": "TOGETHER_API_KEY",
            "mistral": "MISTRAL_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "perplexity": "PERPLEXITY_API_KEY",
            "xai": "XAI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "fireworks": "FIREWORKS_API_KEY",
            "cerebras": "CEREBRAS_API_KEY",
            "cohere": "COHERE_API_KEY",
        }
        # Default model for each provider
        default_models = {
            "anthropic": "claude-opus-4-5",
            "openai": "gpt-4o",
            "gemini": cfg.gemini_default_model,
            "groq": "llama-3.3-70b-versatile",
            "together": "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
            "mistral": "mistral-large-latest",
            "deepseek": "deepseek-chat",
            "perplexity": "llama-3.1-sonar-large-128k-online",
            "xai": "grok-3-fast",
            "openrouter": "anthropic/claude-opus-4-5",
            "fireworks": "accounts/fireworks/models/llama-v3p1-70b-instruct",
            "cerebras": "llama3.1-70b",
            "cohere": "command-r-plus",
        }
        current_key = os.environ.get(key_map.get(cfg.provider, ""), "")
        if not _key_valid(cfg.provider, current_key):
            for prov, env in key_map.items():
                val = os.environ.get(env, "")
                if _key_valid(prov, val):
                    cfg.provider = prov
                    cfg.model = default_models.get(prov, cfg.model)
                    break

        return cfg

    def save(self) -> None:
        """Atomically write config to disk using write-then-rename."""
        import tempfile
        Arix_DIR.mkdir(parents=True, exist_ok=True)
        data = json.dumps(asdict(self), indent=2)
        fd, tmp_path = tempfile.mkstemp(dir=Arix_DIR, suffix=".tmp", prefix="config_")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(data)
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, CONFIG_FILE)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


_GRANT_SECRET_KEY: bytes | None = None


def get_grant_secret_key() -> bytes:
    global _GRANT_SECRET_KEY
    if _GRANT_SECRET_KEY is None:
        _GRANT_SECRET_KEY = secrets.token_bytes(32)
    return _GRANT_SECRET_KEY
