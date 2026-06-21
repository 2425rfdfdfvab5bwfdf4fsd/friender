"""TaskHistory — persists completed task summaries across sessions."""
from __future__ import annotations
import json
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

Arix_DIR = Path.home() / ".arix"
HISTORY_FILE = Arix_DIR / "task_history.json"
MAX_HISTORY = 100


@dataclass
class TaskRecord:
    task_id: str
    command_redacted: str
    intent_domain: str
    intent_verb: str
    status: str
    steps_executed: int
    steps_total: int
    started_at: float
    completed_at: float | None
    duration_s: float | None
    risk_score: float
    error: str | None = None
    files_affected: list[str] = field(default_factory=list)
    egress_events: int = 0


class TaskHistory:
    def __init__(self, history_file: Path = HISTORY_FILE,
                 max_records: int = MAX_HISTORY):
        self.history_file = history_file
        self.max_records = max_records
        self._records: list[TaskRecord] = []
        self._load()

    def _load(self) -> None:
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._records = [TaskRecord(**r) for r in data if isinstance(r, dict)]
            except Exception:
                self._records = []

    def _save(self) -> None:
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in self._records[-self.max_records:]], f, indent=2)
        os.chmod(self.history_file, 0o600)

    def record_start(self, task_id: str, command_redacted: str,
                     intent_domain: str, intent_verb: str,
                     steps_total: int, risk_score: float) -> TaskRecord:
        record = TaskRecord(
            task_id=task_id,
            command_redacted=command_redacted,
            intent_domain=intent_domain,
            intent_verb=intent_verb,
            status="executing",
            steps_executed=0,
            steps_total=steps_total,
            started_at=time.time(),
            completed_at=None,
            duration_s=None,
            risk_score=risk_score,
        )
        self._records.append(record)
        self._save()
        return record

    def update_status(self, task_id: str, status: str,
                      steps_executed: int | None = None,
                      error: str | None = None,
                      files_affected: list[str] | None = None) -> None:
        for record in reversed(self._records):
            if record.task_id == task_id:
                record.status = status
                if steps_executed is not None:
                    record.steps_executed = steps_executed
                if error:
                    record.error = error
                if files_affected:
                    record.files_affected = files_affected[:20]
                if status in ("completed", "failed", "cancelled"):
                    record.completed_at = time.time()
                    record.duration_s = round(
                        record.completed_at - record.started_at, 2
                    )
                break
        self._save()

    def get_recent(self, n: int = 20) -> list[dict]:
        records = self._records[-n:]
        result = []
        for r in reversed(records):
            d = asdict(r)
            d["command_short"] = r.command_redacted[:60] + (
                "..." if len(r.command_redacted) > 60 else ""
            )
            result.append(d)
        return result

    def get_by_id(self, task_id: str) -> TaskRecord | None:
        for r in reversed(self._records):
            if r.task_id == task_id:
                return r
        return None
