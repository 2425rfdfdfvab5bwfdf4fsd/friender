"""PACCA Autonomous Goal Execution — Supervisor loop for multi-step goal decomposition."""
from __future__ import annotations
import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Any


@dataclass
class SubTask:
    task_id: str
    description: str
    command: str
    status: str = "pending"  # pending, running, success, failed, skipped
    result_summary: str = ""
    attempt: int = 0
    max_attempts: int = 2


@dataclass
class GoalPlan:
    goal: str
    goal_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    subtasks: list[SubTask] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    status: str = "planning"  # planning, executing, completed, failed, cancelled
    total_steps: int = 0
    completed_steps: int = 0


# ── Goal detection ──────────────────────────────────────────────────────────

_GOAL_PATTERNS = [
    r'\band\b.{3,50}\band\b',
    r'\bthen\b',
    r'\bafter that\b',
    r'\bnext\b',
    r'\bfinally\b',
    r'\bfirst\b.{3,50}\bthen\b',
    r'\bstep[s]?\b',
    r'^research .{10,} and\b',
    r'^analyze .{10,} and\b',
    r'^build .{10,} and\b',
    r'^create .{10,} and\b',
]

_SIMPLE_PATTERNS = [
    r'^(list|show|check|read|open|close|git|system|monitor)\b',
    r'^what\b',
    r'^how\b',
    r'^why\b',
    r'^explain\b',
]


def is_multi_step_goal(command: str) -> bool:
    lower = command.lower().strip()
    for sp in _SIMPLE_PATTERNS:
        if re.match(sp, lower):
            return False
    word_count = len(lower.split())
    if word_count < 8:
        return False
    for pattern in _GOAL_PATTERNS:
        if re.search(pattern, lower):
            return True
    return False


def decompose_goal(goal: str) -> list[str]:
    """Split a multi-step goal into individual sub-commands."""
    lower = goal.lower()

    step_patterns = [
        r'\d+\.\s+',
        r'(?:first|1st)[,:]?\s+',
        r'\bthen\b[,:]?\s+',
        r'\bafter that\b[,:]?\s+',
        r'\bfinally\b[,:]?\s+',
        r'\bnext\b[,:]?\s+',
        r'\balsob\b[,:]?\s+',
        r'\band then\b[,:]?\s+',
    ]

    parts = [goal]
    for pattern in step_patterns:
        new_parts = []
        for part in parts:
            split = re.split(pattern, part, flags=re.IGNORECASE)
            new_parts.extend([p.strip() for p in split if p.strip()])
        parts = new_parts

    if re.search(r'\band\b', goal):
        and_parts = []
        for part in parts:
            sub = re.split(r'\b and \b', part, flags=re.IGNORECASE)
            if len(sub) <= 3:
                and_parts.extend([p.strip() for p in sub if p.strip()])
            else:
                and_parts.append(part)
        parts = and_parts

    parts = [p for p in parts if len(p) > 5]

    if len(parts) <= 1:
        word_count = len(goal.split())
        if word_count > 15:
            mid = word_count // 2
            words = goal.split()
            parts = [" ".join(words[:mid]), " ".join(words[mid:])]

    return parts[:8]


class GoalSupervisor:
    """Supervises autonomous multi-step goal execution with retry and replanning."""

    def __init__(
        self,
        run_command_fn: Callable[[str, str], AsyncIterator],
        max_retries: int = 2,
        goal_timeout: float = 600.0,
        max_depth: int = 3,
    ) -> None:
        self._run_command = run_command_fn
        self.max_retries = max_retries
        self.goal_timeout = goal_timeout
        self.max_depth = max_depth
        self._active_goals: dict[str, GoalPlan] = {}
        self._cancelled: set[str] = set()

    async def execute_goal(self, goal: str,
                            emit: Callable[[str, dict], None]) -> None:
        plan = self._build_plan(goal)
        self._active_goals[plan.goal_id] = plan

        emit("goal_start", {
            "goal_id": plan.goal_id,
            "goal": goal,
            "subtask_count": len(plan.subtasks),
            "subtasks": [{"id": t.task_id, "description": t.description}
                         for t in plan.subtasks],
        })

        start_time = time.time()
        plan.status = "executing"

        for i, subtask in enumerate(plan.subtasks):
            if plan.goal_id in self._cancelled:
                plan.status = "cancelled"
                emit("goal_cancelled", {"goal_id": plan.goal_id})
                return

            if time.time() - start_time > self.goal_timeout:
                plan.status = "failed"
                emit("goal_error", {
                    "goal_id": plan.goal_id,
                    "error": f"Goal timed out after {self.goal_timeout:.0f}s",
                })
                return

            emit("subtask_start", {
                "goal_id": plan.goal_id,
                "task_id": subtask.task_id,
                "step": i + 1,
                "total": len(plan.subtasks),
                "description": subtask.description,
            })

            success = await self._execute_subtask(subtask, plan.goal_id, emit)

            if success:
                plan.completed_steps += 1
                emit("subtask_complete", {
                    "goal_id": plan.goal_id,
                    "task_id": subtask.task_id,
                    "step": i + 1,
                    "total": len(plan.subtasks),
                    "result": subtask.result_summary[:200],
                })
            else:
                if subtask.status == "failed":
                    emit("subtask_failed", {
                        "goal_id": plan.goal_id,
                        "task_id": subtask.task_id,
                        "error": subtask.result_summary,
                    })
                    if self._is_blocking_failure(subtask):
                        plan.status = "failed"
                        emit("goal_error", {
                            "goal_id": plan.goal_id,
                            "error": f"Blocking step failed: {subtask.description}",
                        })
                        return

        plan.status = "completed"
        emit("goal_complete", {
            "goal_id": plan.goal_id,
            "goal": goal,
            "steps_completed": plan.completed_steps,
            "steps_total": len(plan.subtasks),
            "elapsed": round(time.time() - start_time, 1),
        })
        self._active_goals.pop(plan.goal_id, None)

    def _build_plan(self, goal: str) -> GoalPlan:
        sub_commands = decompose_goal(goal)
        subtasks = [
            SubTask(
                task_id=str(uuid.uuid4())[:8],
                description=cmd[:120],
                command=cmd,
                max_attempts=self.max_retries,
            )
            for cmd in sub_commands
        ]
        return GoalPlan(goal=goal, subtasks=subtasks, total_steps=len(subtasks))

    async def _execute_subtask(self, subtask: SubTask, goal_id: str,
                                emit: Callable[[str, dict], None]) -> bool:
        subtask.status = "running"
        last_error = ""

        for attempt in range(subtask.max_attempts + 1):
            subtask.attempt = attempt
            if attempt > 0:
                await asyncio.sleep(1.5 * attempt)
                emit("subtask_retry", {
                    "goal_id": goal_id,
                    "task_id": subtask.task_id,
                    "attempt": attempt + 1,
                })

            try:
                results = []
                task_id = str(uuid.uuid4())
                async for event in self._run_command(subtask.command, task_id):
                    if event.type in ("step_complete",):
                        r = event.data.get("result", {})
                        if "error" not in r:
                            results.append(str(r)[:100])
                    elif event.type == "completed":
                        steps = event.data.get("steps_executed", 0)
                        subtask.result_summary = f"{steps} step(s) completed. " + "; ".join(results[:3])
                        subtask.status = "success"
                        return True
                    elif event.type == "error":
                        last_error = event.data.get("message", "Unknown error")
                    elif event.type == "advisory":
                        subtask.result_summary = event.data.get("response", "")[:200]
                        subtask.status = "success"
                        return True
                    elif event.type == "cancelled":
                        subtask.status = "skipped"
                        return False

                if subtask.status != "success":
                    subtask.status = "failed"
                    subtask.result_summary = last_error or "No output"

            except Exception as e:
                last_error = str(e)
                subtask.status = "failed"
                subtask.result_summary = str(e)[:200]

            if subtask.status == "success":
                return True

        subtask.status = "failed"
        return False

    def _is_blocking_failure(self, subtask: SubTask) -> bool:
        critical_tools = ["create_file", "git_commit", "create_xlsx", "create_docx"]
        return any(t in subtask.command.lower() for t in critical_tools)

    def cancel_goal(self, goal_id: str) -> None:
        self._cancelled.add(goal_id)

    def active_goals(self) -> list[dict]:
        return [
            {
                "goal_id": g.goal_id,
                "goal": g.goal[:100],
                "status": g.status,
                "completed": g.completed_steps,
                "total": g.total_steps,
            }
            for g in self._active_goals.values()
        ]
