"""PACCA Autonomous Goal Execution — Supervisor loop with LLM-powered goal decomposition."""
from __future__ import annotations
import asyncio
import json
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
    decomposition_method: str = "heuristic"  # heuristic | llm


# ── LLM goal decomposition prompt ───────────────────────────────────────────

_LLM_DECOMPOSE_SYSTEM = """You are PACCA's goal decomposition engine. Break a multi-step goal into concrete, atomic sub-commands that PACCA can execute one by one.

RULES:
1. Output ONLY a JSON array of command strings — no prose, no markdown, no explanation.
2. Each command must be an atomic, executable instruction (1 tool call).
3. Maximum 8 commands. Minimum 2 commands.
4. Use natural language — PACCA will parse and route each command.
5. Commands must be sequential and build on each other logically.
6. Be specific about file paths, using ~/ for home directory.

EXAMPLES:
Goal: "research the top 5 LLM APIs and create a comparison spreadsheet"
Output: ["search the web for top 5 LLM APIs 2026", "search the web for pricing and features of OpenAI Anthropic Gemini Cohere APIs", "search the web for LLM API performance benchmarks 2026", "create file ~/Desktop/llm_comparison.md with the research findings structured as a comparison table"]

Goal: "check git status and commit any changed files with message 'daily update'"
Output: ["git status in current directory", "git add all changed files in current directory", "git commit with message 'daily update'"]

Goal: "search the web for Python async best practices and save to a file"
Output: ["search the web for Python async await best practices 2025", "search the web for asyncio patterns common mistakes Python", "create file ~/async_notes.md with the research findings"]

Goal: "list the files in my downloads folder and find any large files over 100MB"
Output: ["list files in ~/Downloads", "search for files larger than 100MB in ~/Downloads"]"""


# ── Heuristic goal detection ──────────────────────────────────────────────────

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
    """Split a multi-step goal into individual sub-commands using heuristics."""
    lower = goal.lower()

    step_patterns = [
        r'\d+\.\s+',
        r'(?:first|1st)[,:]?\s+',
        r'\bthen\b[,:]?\s+',
        r'\bafter that\b[,:]?\s+',
        r'\bfinally\b[,:]?\s+',
        r'\bnext\b[,:]?\s+',
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
    """Supervises autonomous multi-step goal execution.

    Uses LLM-powered decomposition when an LLM client is available,
    falling back to heuristic (regex) decomposition otherwise.
    """

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
        self._llm_client: Any = None

    def set_llm_client(self, client: Any) -> None:
        """Wire in an LLM client for intelligent goal decomposition."""
        self._llm_client = client

    # ── LLM-based decomposition ───────────────────────────────────────────────

    async def _llm_decompose_goal(self, goal: str) -> list[str] | None:
        """Use the LLM to decompose the goal into atomic sub-commands.

        Returns None if the LLM is unavailable or decomposition fails.
        """
        if self._llm_client is None:
            return None
        try:
            if not self._llm_client.is_available():
                return None
            raw = await self._llm_client._call(
                _LLM_DECOMPOSE_SYSTEM,
                f"Goal: {goal}",
                max_tokens=512,
            )
            raw = raw.strip()
            # Strip markdown fences if the model adds them
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(lines[1:])
                if "```" in raw:
                    raw = raw[:raw.rfind("```")].strip()
            commands = json.loads(raw)
            if isinstance(commands, list) and len(commands) >= 2:
                valid = [str(c).strip() for c in commands if str(c).strip()]
                if valid:
                    return valid[:8]
        except Exception:
            pass
        return None

    # ── Plan building ─────────────────────────────────────────────────────────

    def _build_plan(self, goal: str, sub_commands: list[str],
                    method: str = "heuristic") -> GoalPlan:
        subtasks = [
            SubTask(
                task_id=str(uuid.uuid4())[:8],
                description=cmd[:120],
                command=cmd,
                max_attempts=self.max_retries,
            )
            for cmd in sub_commands
        ]
        return GoalPlan(
            goal=goal,
            subtasks=subtasks,
            total_steps=len(subtasks),
            decomposition_method=method,
        )

    # ── Main execution loop ───────────────────────────────────────────────────

    async def execute_goal(self, goal: str,
                            emit: Callable[[str, dict], None]) -> None:
        # Attempt LLM decomposition first; fall back to heuristics
        sub_commands = await self._llm_decompose_goal(goal)
        method = "llm" if sub_commands else "heuristic"
        if not sub_commands:
            sub_commands = decompose_goal(goal)

        plan = self._build_plan(goal, sub_commands, method=method)
        self._active_goals[plan.goal_id] = plan

        emit("goal_start", {
            "goal_id": plan.goal_id,
            "goal": goal,
            "subtask_count": len(plan.subtasks),
            "subtasks": [{"id": t.task_id, "description": t.description}
                         for t in plan.subtasks],
            "decomposition_method": method,
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
            "decomposition_method": method,
        })
        self._active_goals.pop(plan.goal_id, None)

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
                    elif event.type in ("goal_complete",):
                        # Nested goal execution succeeded
                        subtask.result_summary = "goal completed"
                        subtask.status = "success"
                        return True

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
                "decomposition_method": g.decomposition_method,
                "elapsed": round(time.time() - g.created_at, 1),
            }
            for g in self._active_goals.values()
        ]
