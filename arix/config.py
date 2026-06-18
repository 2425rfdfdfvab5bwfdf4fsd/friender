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
    provider: str = "gemini"
    model: str = "gemini-2.0-flash-lite"
    sanitizer_provider: str = "gemini"
    sanitizer_model: str = "gemini-2.0-flash-lite"
    gemini_default_model: str = "gemini-2.0-flash-lite"
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
            "anthropic": "claude-haiku-4-5",
            "openai": "gpt-4o-mini",
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


async def check_ollama_available(base_url: str = "http://localhost:11434") -> bool:
    """Return True if a local Ollama instance is reachable and has models loaded."""
    try:
        import asyncio
        import urllib.request
        import urllib.error

        def _check():
            try:
                req = urllib.request.urlopen(f"{base_url}/api/tags", timeout=2)
                import json
                data = json.loads(req.read())
                return len(data.get("models", [])) > 0
            except Exception:
                return False

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _check)
    except Exception:
        return False


async def auto_detect_and_switch_ollama(cfg: "ArixConfig") -> bool:
    """If no cloud provider is configured, check Ollama and switch to it.

    Returns True if switched to Ollama.
    """
    # Only auto-switch if currently in demo/heuristic mode (no real key)
    if cfg.provider != "anthropic" or os.environ.get("AI_INTEGRATIONS_ANTHROPIC_API_KEY"):
        return False

    # Check if any cloud key is present
    cloud_keys = [
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY",
        "TOGETHER_API_KEY", "MISTRAL_API_KEY", "DEEPSEEK_API_KEY", "PERPLEXITY_API_KEY",
        "XAI_API_KEY", "OPENROUTER_API_KEY", "FIREWORKS_API_KEY", "CEREBRAS_API_KEY",
        "COHERE_API_KEY",
    ]
    if any(os.environ.get(k, "").strip() for k in cloud_keys):
        return False

    # No cloud keys — check Ollama
    ollama_base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    if await check_ollama_available(ollama_base):
        cfg.provider = "ollama"
        cfg.model = os.environ.get("OLLAMA_DEFAULT_MODEL", "llama3.2")
        cfg.save()
        return True

    return False
