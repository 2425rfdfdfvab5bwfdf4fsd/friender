"""ProviderConsent — records user's acknowledgement of provider data-egress."""
from __future__ import annotations
import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Literal

Arix_DIR = Path.home() / ".arix"
CONSENT_FILE = Arix_DIR / "consent.json"

EgressType = Literal[
    "screenshot", "command_text", "file_metadata",
    "file_excerpt", "page_excerpt", "diff_excerpt", "task_counts",
]


@dataclass
class ProviderConsent:
    provider_id: str
    provider_display_name: str
    privacy_policy_url: str
    consented_at: float
    consent_schema_version: str
    egress_types_acknowledged: list[str]
    first_use_notice_shown: bool
    offline_mode_selected: bool = False


class ConsentStore:
    def __init__(self, consent_file: Path = CONSENT_FILE):
        self.consent_file = consent_file
        self._consents: dict[str, ProviderConsent] = {}
        self._load()

    def _load(self) -> None:
        if self.consent_file.exists():
            try:
                with open(self.consent_file) as f:
                    raw = json.load(f)
                for provider_id, data in raw.items():
                    self._consents[provider_id] = ProviderConsent(**data)
            except Exception:
                pass

    def _save(self) -> None:
        self.consent_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = {pid: asdict(pc) for pid, pc in self._consents.items()}
        with open(self.consent_file, "w") as f:
            json.dump(tmp, f, indent=2)
        os.chmod(self.consent_file, 0o600)

    def has_consent(self, provider_id: str) -> bool:
        return provider_id in self._consents

    def get_consent(self, provider_id: str) -> ProviderConsent | None:
        return self._consents.get(provider_id)

    def record_consent(self, provider_id: str, display_name: str,
                       privacy_url: str, egress_types: list[str]) -> ProviderConsent:
        pc = ProviderConsent(
            provider_id=provider_id,
            provider_display_name=display_name,
            privacy_policy_url=privacy_url,
            consented_at=time.time(),
            consent_schema_version="5.2",
            egress_types_acknowledged=egress_types,
            first_use_notice_shown=True,
            offline_mode_selected=False,
        )
        self._consents[provider_id] = pc
        self._save()
        return pc
