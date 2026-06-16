"""Onboarding wizard — shown on first run; cannot be skipped."""
from __future__ import annotations
import json
import os
from pathlib import Path

Arix_DIR = Path.home() / ".arix"
ONBOARDING_FILE = Arix_DIR / "onboarding_complete.json"

DISCLOSURE_TEXT = """
╔══════════════════════════════════════════════════════════════════════╗
║              Arix v5.2 — Privacy & Data Disclosure                 ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  Arix uses cloud AI services to understand your commands and        ║
║  plan actions. The following data may be sent to AI providers:       ║
║                                                                      ║
║  • Your command text (sensitive patterns are redacted first)         ║
║  • Excerpts of files you ask Arix to read (max 32 KB, redacted)    ║
║  • Web page text when you ask Arix to browse (max 32 KB)           ║
║  • Git diffs when you ask Arix to commit (redacted)                ║
║                                                                      ║
║  Data that is NEVER sent:                                            ║
║  • Screenshots (for file/git tasks)                                  ║
║  • Raw file content beyond the 32 KB limit                          ║
║  • Browser cookies, passwords, or form data                          ║
║  • API keys or credentials (automatically redacted)                  ║
║                                                                      ║
║  Security protections:                                               ║
║  • Every action requires a single-use cryptographic grant            ║
║  • Destructive actions require your explicit "YES"                   ║
║  • Files are resolved via safe path resolver (no traversal)          ║
║  • Audit log written to ~/.arix/audit.log (owner-only)             ║
║                                                                      ║
║  Providers: Anthropic, OpenAI (per your configuration)              ║
║  Review their privacy policies before proceeding.                   ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
"""


def is_onboarding_complete() -> bool:
    return ONBOARDING_FILE.exists()


def complete_onboarding(provider_id: str = "anthropic") -> None:
    Arix_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "completed": True,
        "provider_consented": provider_id,
        "schema_version": "5.2",
    }
    with open(ONBOARDING_FILE, "w") as f:
        json.dump(data, f)
    os.chmod(ONBOARDING_FILE, 0o600)
