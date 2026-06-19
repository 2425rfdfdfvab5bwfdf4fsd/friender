"""Arix Workflow Automation System — natural language workflow builder with APScheduler."""
from __future__ import annotations
import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Awaitable

import yaml

WORKFLOWS_DIR = Path.home() / ".arix" / "workflows"


@dataclass
class WorkflowStep:
    tool: str
    args: dict = field(default_factory=dict)
    description: str = ""


@dataclass
class WorkflowTrigger:
    type: str  # "cron", "manual", "event"
    schedule: str | None = None  # cron string e.g. "0 9 * * 1-5"
    event: str | None = None


@dataclass
class Workflow:
    name: str
    description: str
    trigger: WorkflowTrigger
    steps: list[WorkflowStep]
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    last_run: float | None = None
    last_outcome: str | None = None
    run_count: int = 0
    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "last_run": self.last_run,
            "last_outcome": self.last_outcome,
            "run_count": self.run_count,
            "trigger": asdict(self.trigger),
            "steps": [asdict(s) for s in self.steps],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Workflow":
        trigger_data = data.get("trigger", {})
        trigger = WorkflowTrigger(
            type=trigger_data.get("type", "manual"),
            schedule=trigger_data.get("schedule"),
            event=trigger_data.get("event"),
        )
        steps = [
            WorkflowStep(
                tool=s["tool"],
                args=s.get("args", {}),
                description=s.get("description", ""),
            )
            for s in data.get("steps", [])
        ]
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            trigger=trigger,
            steps=steps,
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", time.time()),
            last_run=data.get("last_run"),
            last_outcome=data.get("last_outcome"),
            run_count=data.get("run_count", 0),
            workflow_id=data.get("workflow_id", str(uuid.uuid4())[:8]),
        )


# ── Natural language trigger parser ──────────────────────────────────────────

_CRON_PATTERNS = [
    (r"every day at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?", lambda m: _time_to_cron(m)),
    (r"every weekday at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?", lambda m: _time_to_cron(m, "1-5")),
    (r"every morning(?: at (\d{1,2})(?::(\d{2}))?)?", lambda m: "0 9 * * *"),
    (r"every hour", lambda m: "0 * * * *"),
    (r"every (\d+) minutes?", lambda m: f"*/{m.group(1)} * * * *"),
    (r"every monday(?: at (\d{1,2}))?", lambda m: f"0 {_hour(m)} * * 1"),
    (r"daily(?: at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?)?", lambda m: _time_to_cron(m) if m.group(1) else "0 9 * * *"),
]


def _hour(m: re.Match) -> int:
    try:
        return int(m.group(1))
    except Exception:
        return 9


def _time_to_cron(m: re.Match, days: str = "*") -> str:
    try:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        ampm = m.group(3) if len(m.groups()) >= 3 else None
        if ampm and ampm.lower() == "pm" and hour != 12:
            hour += 12
        elif ampm and ampm.lower() == "am" and hour == 12:
            hour = 0
        return f"{minute} {hour} * * {days}"
    except Exception:
        return "0 9 * * *"


def parse_trigger_from_text(text: str) -> WorkflowTrigger:
    lower = text.lower()
    for pattern, cron_fn in _CRON_PATTERNS:
        m = re.search(pattern, lower)
        if m:
            cron = cron_fn(m)
            return WorkflowTrigger(type="cron", schedule=cron)
    return WorkflowTrigger(type="manual")


def parse_workflow_from_command(command: str, steps_hint: list[dict] | None = None) -> Workflow | None:
    """Parse a natural language workflow definition into a Workflow object."""
    lower = command.lower()

    # Prefer explicit "called <name>" / "named <name>" pattern first
    called_match = re.search(
        r'(?:called|named)\s+["\']?([a-zA-Z0-9_][a-zA-Z0-9_ -]*?)["\']?\s*(?:--|every|at\s+\d|on\s+\w|\Z)',
        lower
    )
    if called_match:
        name = called_match.group(1).strip()
    else:
        save_match = re.search(
            r'(?:save|name|call)\s+(?:this\s+)?(?:as\s+)?["\']?([a-zA-Z0-9_ ]+?)["\']?\s*(?:workflow)?(?:\s|$)',
            lower
        )
        name = save_match.group(1).strip() if save_match else f"workflow_{int(time.time())}"
    name = re.sub(r'[^a-zA-Z0-9_]', '_', name).strip('_') or f"workflow_{int(time.time())}"

    trigger = parse_trigger_from_text(command)

    steps = []
    if steps_hint:
        for s in steps_hint:
            steps.append(WorkflowStep(
                tool=s.get("tool", ""),
                args=s.get("args", {}),
                description=s.get("description", ""),
            ))

    if not steps:
        if "git" in lower and ("status" in lower or "pull" in lower):
            steps.append(WorkflowStep("git_status", {"repo_path": "~"}, "Check git status"))
        if "system" in lower or "monitor" in lower:
            steps.append(WorkflowStep("system_monitor", {}, "Check system metrics"))
        if "list" in lower and "file" in lower:
            steps.append(WorkflowStep("list_directory", {"path": "~"}, "List home directory"))

    return Workflow(
        name=name,
        description=command[:200],
        trigger=trigger,
        steps=steps,
    )


class WorkflowRegistry:
    """CRUD operations on workflow YAML files in ~/.arix/workflows/."""

    def __init__(self) -> None:
        WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        safe = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
        return WORKFLOWS_DIR / f"{safe}.yaml"

    def save(self, workflow: Workflow) -> None:
        data = workflow.to_dict()
        path = self._path(workflow.name)
        path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))

    def load(self, name: str) -> Workflow | None:
        path = self._path(name)
        if not path.exists():
            return None
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            return Workflow.from_dict(data)
        except Exception:
            return None

    def list_all(self) -> list[Workflow]:
        workflows = []
        for p in sorted(WORKFLOWS_DIR.glob("*.yaml")):
            try:
                data = yaml.safe_load(p.read_text(encoding="utf-8"))
                workflows.append(Workflow.from_dict(data))
            except Exception:
                continue
        return workflows

    def delete(self, name: str) -> bool:
        path = self._path(name)
        if path.exists():
            path.unlink()
            return True
        return False

    def update_run_result(self, name: str, outcome: str) -> None:
        wf = self.load(name)
        if wf:
            wf.last_run = time.time()
            wf.last_outcome = outcome
            wf.run_count += 1
            self.save(wf)


class WorkflowManager:
    """Orchestrates the workflow registry and scheduler."""

    def __init__(self, run_command_fn: Callable[[str], Awaitable[Any]] | None = None) -> None:
        self.registry = WorkflowRegistry()
        self._run_command_fn = run_command_fn
        self._scheduler = None
        self._scheduler_started = False

    def start_scheduler(self) -> None:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            self._scheduler = AsyncIOScheduler()
            self._register_all_jobs()
            self._scheduler.start()
            self._scheduler_started = True
        except ImportError:
            import logging
            logging.getLogger("arix.workflows").warning(
                "apscheduler not installed — cron workflows will NOT run automatically. "
                "Install it with: pip install apscheduler"
            )

    def stop_scheduler(self) -> None:
        if self._scheduler and self._scheduler_started:
            try:
                self._scheduler.shutdown(wait=False)
            except Exception:
                pass

    def _register_all_jobs(self) -> None:
        if not self._scheduler:
            return
        for wf in self.registry.list_all():
            if wf.enabled and wf.trigger.type == "cron" and wf.trigger.schedule:
                self._register_job(wf)

    def _register_job(self, wf: Workflow) -> None:
        if not self._scheduler or not wf.trigger.schedule:
            return
        try:
            parts = wf.trigger.schedule.split()
            if len(parts) == 5:
                minute, hour, day, month, day_of_week = parts
                existing = self._scheduler.get_job(f"wf_{wf.name}")
                if existing:
                    existing.remove()
                self._scheduler.add_job(
                    self._execute_workflow,
                    trigger="cron",
                    id=f"wf_{wf.name}",
                    name=wf.name,
                    minute=minute,
                    hour=hour,
                    day=day,
                    month=month,
                    day_of_week=day_of_week,
                    args=[wf.name],
                    replace_existing=True,
                )
        except Exception:
            pass

    async def _execute_workflow(self, name: str) -> None:
        wf = self.registry.load(name)
        if not wf or not wf.enabled:
            return
        if self._run_command_fn:
            try:
                command = f"run workflow steps: {wf.description}"
                await self._run_command_fn(command)
                self.registry.update_run_result(name, "success")
            except Exception as e:
                self.registry.update_run_result(name, f"error: {str(e)[:100]}")

    def save_workflow(self, workflow: Workflow) -> None:
        self.registry.save(workflow)
        if self._scheduler and workflow.trigger.type == "cron":
            self._register_job(workflow)

    def delete_workflow(self, name: str) -> bool:
        if self._scheduler:
            job = self._scheduler.get_job(f"wf_{name}")
            if job:
                job.remove()
        return self.registry.delete(name)

    def list_workflows(self) -> list[dict]:
        workflows = self.registry.list_all()
        result = []
        for wf in workflows:
            d = wf.to_dict()
            d["next_run"] = self._get_next_run(wf.name)
            result.append(d)
        return result

    def _get_next_run(self, name: str) -> str | None:
        if not self._scheduler:
            return None
        job = self._scheduler.get_job(f"wf_{name}")
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
        return None

    def run_now(self, name: str) -> bool:
        if self._scheduler:
            job = self._scheduler.get_job(f"wf_{name}")
            if job:
                job.modify(next_run_time=__import__("datetime").datetime.now(
                    __import__("apscheduler.util", fromlist=["astimezone"]).astimezone(None)
                ))
                return True
        return False

    def toggle_workflow(self, name: str, enabled: bool) -> bool:
        wf = self.registry.load(name)
        if not wf:
            return False
        wf.enabled = enabled
        self.registry.save(wf)
        if self._scheduler:
            job = self._scheduler.get_job(f"wf_{name}")
            if job:
                if enabled:
                    job.resume()
                else:
                    job.pause()
        return True

    def is_workflow_command(self, command: str) -> str | None:
        """Returns the workflow sub-command type if this is a workflow management command."""
        lower = command.lower().strip()
        if re.search(r'\b(save|create|schedule)\b.{0,30}\bworkflow\b', lower):
            return "save"
        if re.search(r'\b(save this as|name this|call this)\b', lower):
            return "save"
        if re.search(r'\b(list|show)\b.{0,20}\bworkflow', lower):
            return "list"
        if re.search(r'\brun workflow\b', lower):
            return "run"
        if re.search(r'\b(delete|remove)\b.{0,20}\bworkflow\b', lower):
            return "delete"
        if re.search(r'\b(enable|disable|pause)\b.{0,20}\bworkflow\b', lower):
            return "toggle"
        return None
