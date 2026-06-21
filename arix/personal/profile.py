"""User profile management — name, role, preferences, work hours, timezone."""
from __future__ import annotations
import json
import os
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

Arix_DIR = Path.home() / ".arix"
PROFILE_FILE = Arix_DIR / "profile.json"


@dataclass
class UserProfile:
    name: str = ""
    role: str = ""
    company: str = ""
    timezone: str = "UTC"
    work_start: str = "09:00"
    work_end: str = "18:00"
    work_days: list = field(default_factory=lambda: ["Mon", "Tue", "Wed", "Thu", "Fri"])
    communication_style: str = "balanced"  # terse | balanced | detailed
    primary_use_cases: list = field(default_factory=list)
    current_projects: list = field(default_factory=list)
    key_contacts: list = field(default_factory=list)
    avatar_color: str = "#4f8ef7"
    onboarding_complete: bool = False
    created_at: float = field(default_factory=time.time)

    def display_name(self) -> str:
        return self.name or "User"

    def initials(self) -> str:
        if self.name:
            parts = self.name.strip().split()
            if len(parts) >= 2:
                return (parts[0][0] + parts[-1][0]).upper()
            return parts[0][0].upper() if parts else "U"
        return "P"

    def greeting(self) -> str:
        hour = int(__import__('datetime').datetime.now().strftime('%H'))
        if hour < 12:
            prefix = "Good morning"
        elif hour < 17:
            prefix = "Good afternoon"
        else:
            prefix = "Good evening"
        name = self.name
        return f"{prefix}{', ' + name if name else ''}!"

    @classmethod
    def load(cls) -> "UserProfile":
        if PROFILE_FILE.exists():
            try:
                data = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
                p = cls()
                if isinstance(data, dict):
                    for k, v in data.items():
                        if hasattr(p, k):
                            setattr(p, k, v)
                return p
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        Arix_DIR.mkdir(parents=True, exist_ok=True)
        PROFILE_FILE.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        os.chmod(PROFILE_FILE, 0o600)

    def update(self, updates: dict) -> None:
        for k, v in updates.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self.save()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["initials"] = self.initials()
        d["greeting"] = self.greeting()
        return d
