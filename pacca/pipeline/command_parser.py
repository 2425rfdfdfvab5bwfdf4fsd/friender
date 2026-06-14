"""CommandParser — derives TaskScope from raw user command before external content."""
from __future__ import annotations
import os
import uuid
from pathlib import Path

from pacca.models.task_scope import TaskScope
from pacca.security.local_text_redactor import LocalTextRedactor

PACCA_DIR = Path.home() / ".pacca"


class CommandParser:
    def __init__(self, redactor: LocalTextRedactor | None = None,
                 allowed_path_prefixes: list[str] | None = None):
        self.redactor = redactor or LocalTextRedactor()
        self.allowed_path_prefixes = allowed_path_prefixes or self._default_prefixes()

    def _default_prefixes(self) -> list[str]:
        home = str(Path.home())
        cwd = os.getcwd()
        prefixes = [home, cwd]
        for extra in ["~/Desktop", "~/Downloads", "~/Documents",
                      "~/Pictures", "~/Music", "~/Videos"]:
            expanded = os.path.expanduser(extra)
            if os.path.exists(expanded):
                prefixes.append(expanded)
        prefixes.append(str(PACCA_DIR))
        return list(set(prefixes))

    def parse(self, raw_command: str, task_id: str | None = None) -> TaskScope:
        task_id = task_id or str(uuid.uuid4())
        redaction_result = self.redactor.redact(raw_command)
        redacted_command = redaction_result.redacted

        scope = TaskScope.derive(
            task_id=task_id,
            command=raw_command,
            redacted_command=redacted_command,
            allowed_path_prefixes=self.allowed_path_prefixes,
            max_steps=30,
        )
        return scope
