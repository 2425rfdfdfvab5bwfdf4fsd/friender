"""PACCA Autonomous Goal Execution — Supervisor loop with:
- LLM-powered goal decomposition
- Self-reflection on step failure (Gap #3)
- Goal-level filesystem rollback/checkpointing (Gap #9)
- Skill saving after successful goals (Gap #12)
"""
from __future__ import annotations
import asyncio
import json
import os
import re
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Callable, Any


@dataclass
class SubTask:
    task_id: str
    description: str
    command: str
    status: str = "pending"   # pending, running, success, failed, skipped
    result_summary: str = ""
    attempt: int = 0
    max_attempts: int = 2
    skip: bool = False        # Gap #7: user-deselected steps


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
    # Gap #9: checkpoint info
    checkpoint_dir: str | None = None
    files_created: list[str] = field(default_factory=list)


# ── LLM prompts ───────────────────────────────────────────────────────────────

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


_REFLECT_SYSTEM = """You are PACCA's error recovery engine. A step in an autonomous goal has failed.
Your job is to suggest ONE revised approach that avoids the same failure.

Rules:
1. Output ONLY a single revised command string — no prose, no explanation, no JSON.
2. The revised command should accomplish the same intent using a different approach.
3. If the error suggests a missing file, suggest creating it first.
4. If the error suggests a permission issue, suggest an alternative path.
5. If the error is clearly unrecoverable (e.g., network down, tool unavailable), output: SKIP
6. Keep the revised command concise — PACCA will parse it."""


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
    r'^search .{5,} and\s+(save|create|write|store)\b',
    r'\band\s+(save|create|write|store)\s+.{5,}\b',
    r'^open url .{10,} and\b',
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

    Features:
    - LLM-powered decomposition (with heuristic fallback)
    - Self-reflection on step failure (Gap #3)
    - Goal-level rollback via checkpoint (Gap #9)
    - Skill saving after successful goals (Gap #12)
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
        self._memory: Any = None  # Optional MemoryManager for skill saving

    def set_llm_client(self, client: Any) -> None:
        self._llm_client = client

    def set_memory(self, memory: Any) -> None:
        self._memory = memory

    # ── LLM-based decomposition ───────────────────────────────────────────────

    async def _llm_decompose_goal(self, goal: str) -> list[str] | None:
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

    # ── Gap #3: Self-reflection on step failure ───────────────────────────────

    async def _reflect_on_failure(
        self,
        command: str,
        error: str,
        goal: str,
        previous_results: list[str],
    ) -> str | None:
        """Ask LLM to suggest a revised command after a step failure.

        Returns revised command string, "SKIP" to skip the step, or None if LLM unavailable.
        """
        if self._llm_client is None or not self._llm_client.is_available():
            return None

        context = (
            f"Goal: {goal}\n"
            f"Failed step: {command}\n"
            f"Error: {error[:300]}\n"
        )
        if previous_results:
            context += f"Previous successful results: {'; '.join(previous_results[:3])}\n"
        context += "\nSuggest ONE revised command string (or SKIP if unrecoverable):"

        try:
            revised = await self._llm_client._call(
                _REFLECT_SYSTEM,
                context,
                max_tokens=150,
            )
            revised = revised.strip().strip('"\'')
            if revised and len(revised) > 4:
                return revised
        except Exception:
            pass
        return None

    # ── Gap #9: Goal-level checkpoint / rollback ──────────────────────────────

    def _create_checkpoint(self, goal_id: str) -> str | None:
        """Create an isolated checkpoint directory for this goal."""
        try:
            base = Path(tempfile.gettempdir()) / "pacca_checkpoints"
            base.mkdir(exist_ok=True)
            ckpt = base / goal_id
            ckpt.mkdir(exist_ok=True)
            return str(ckpt)
        except Exception:
            return None

    def checkpoint_file(self, plan: GoalPlan, file_path: str) -> None:
        """Back up a file before modification so it can be restored on rollback."""
        if not plan.checkpoint_dir:
            return
        try:
            src = Path(file_path).expanduser().resolve()
            if src.exists() and src.is_file():
                ckpt = Path(plan.checkpoint_dir)
                # Preserve relative structure
                rel = src.name
                ckpt_file = ckpt / rel
                counter = 0
                while ckpt_file.exists():
                    counter += 1
                    ckpt_file = ckpt / f"{src.stem}_{counter}{src.suffix}"
                shutil.copy2(str(src), str(ckpt_file))
        except Exception:
            pass

    def rollback_goal(self, goal_id: str) -> dict:
        """Delete files created during the goal and report what was rolled back."""
        plan = self._active_goals.get(goal_id)
        results = {"goal_id": goal_id, "deleted": [], "errors": []}

        if plan:
            for fp in plan.files_created:
                try:
                    p = Path(fp)
                    if p.exists():
                        p.unlink()
                        results["deleted"].append(fp)
                except Exception as e:
                    results["errors"].append(f"{fp}: {e}")

        # Clean checkpoint dir
        try:
            if plan and plan.checkpoint_dir:
                shutil.rmtree(plan.checkpoint_dir, ignore_errors=True)
        except Exception:
            pass

        return results

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
        plan = GoalPlan(
            goal=goal,
            subtasks=subtasks,
            total_steps=len(subtasks),
            decomposition_method=method,
        )
        plan.checkpoint_dir = self._create_checkpoint(plan.goal_id)
        return plan

    # ── Main execution loop ───────────────────────────────────────────────────

    async def execute_goal(self, goal: str,
                           emit: Callable[[str, dict], None],
                           skip_steps: list[int] | None = None) -> None:
        sub_commands = await self._llm_decompose_goal(goal)
        method = "llm" if sub_commands else "heuristic"
        if not sub_commands:
            sub_commands = decompose_goal(goal)

        plan = self._build_plan(goal, sub_commands, method=method)
        self._active_goals[plan.goal_id] = plan

        # Gap #7: Mark user-deselected steps (1-indexed)
        if skip_steps:
            for idx in skip_steps:
                if 1 <= idx <= len(plan.subtasks):
                    plan.subtasks[idx - 1].skip = True

        emit("goal_start", {
            "goal_id": plan.goal_id,
            "goal": goal,
            "subtask_count": len(plan.subtasks),
            "subtasks": [
                {"id": t.task_id, "description": t.description, "skip": t.skip}
                for t in plan.subtasks
            ],
            "decomposition_method": method,
            "has_checkpoint": bool(plan.checkpoint_dir),
        })

        start_time = time.time()
        plan.status = "executing"
        previous_results: list[str] = []

        for i, subtask in enumerate(plan.subtasks):
            if plan.goal_id in self._cancelled:
                plan.status = "cancelled"
                emit("goal_cancelled", {"goal_id": plan.goal_id})
                self._cleanup_checkpoint(plan)
                return

            if time.time() - start_time > self.goal_timeout:
                plan.status = "failed"
                emit("goal_error", {
                    "goal_id": plan.goal_id,
                    "error": f"Goal timed out after {self.goal_timeout:.0f}s",
                })
                return

            # Gap #7: Skip user-deselected steps
            if subtask.skip:
                emit("subtask_skipped", {
                    "goal_id": plan.goal_id,
                    "task_id": subtask.task_id,
                    "step": i + 1,
                    "reason": "user_deselected",
                })
                continue

            emit("subtask_start", {
                "goal_id": plan.goal_id,
                "task_id": subtask.task_id,
                "step": i + 1,
                "total": len(plan.subtasks),
                "description": subtask.description,
            })

            success = await self._execute_subtask(
                subtask, plan, emit, previous_results
            )

            if success:
                plan.completed_steps += 1
                if subtask.result_summary:
                    previous_results.append(subtask.result_summary[:100])
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
        elapsed = round(time.time() - start_time, 1)

        # Gap #12: Offer to save as skill after successful completion
        skill_hint = None
        if self._memory and plan.completed_steps >= 2:
            try:
                skill_id = self._memory.save_skill_from_goal(
                    goal=goal,
                    steps=[t.command for t in plan.subtasks if t.status == "success"],
                    method=method,
                )
                skill_hint = skill_id
            except Exception:
                pass

        emit("goal_complete", {
            "goal_id": plan.goal_id,
            "goal": goal,
            "steps_completed": plan.completed_steps,
            "steps_total": len(plan.subtasks),
            "elapsed": elapsed,
            "decomposition_method": method,
            "skill_saved": skill_hint,
        })
        self._cleanup_checkpoint(plan)
        self._active_goals.pop(plan.goal_id, None)

    def _cleanup_checkpoint(self, plan: GoalPlan) -> None:
        if plan.checkpoint_dir:
            try:
                shutil.rmtree(plan.checkpoint_dir, ignore_errors=True)
            except Exception:
                pass

    async def _execute_subtask(
        self,
        subtask: SubTask,
        plan: GoalPlan,
        emit: Callable[[str, dict], None],
        previous_results: list[str],
    ) -> bool:
        subtask.status = "running"
        last_error = ""
        current_command = subtask.command

        max_total = subtask.max_attempts + 1  # +1 for initial attempt
        for attempt in range(max_total):
            subtask.attempt = attempt

            if attempt > 0:
                await asyncio.sleep(1.5 * attempt)
                emit("subtask_retry", {
                    "goal_id": plan.goal_id,
                    "task_id": subtask.task_id,
                    "attempt": attempt + 1,
                    "revised_command": current_command if current_command != subtask.command else None,
                })

            try:
                results = []
                task_id = str(uuid.uuid4())
                async for event in self._run_command(current_command, task_id):
                    if event.type == "step_complete":
                        r = event.data.get("result", {})
                        if "error" not in r:
                            results.append(str(r)[:100])
                            # Gap #9: track files created
                            if "created" in r or "saved" in r:
                                fp = r.get("created") or r.get("saved", "")
                                if fp and isinstance(fp, str):
                                    plan.files_created.append(fp)
                    elif event.type == "completed":
                        steps = event.data.get("steps_executed", 0)
                        subtask.result_summary = (
                            f"{steps} step(s) completed. " + "; ".join(results[:3])
                        )
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
                    elif event.type == "goal_complete":
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

            # Gap #3: Self-reflection before next retry
            if attempt < max_total - 1 and self._llm_client:
                revised = await self._reflect_on_failure(
                    command=current_command,
                    error=last_error,
                    goal=plan.goal,
                    previous_results=previous_results,
                )
                if revised == "SKIP":
                    subtask.status = "skipped"
                    subtask.result_summary = "Skipped after reflection — step deemed unrecoverable"
                    emit("subtask_reflected", {
                        "goal_id": plan.goal_id,
                        "task_id": subtask.task_id,
                        "action": "skip",
                        "reason": last_error[:100],
                    })
                    return False
                elif revised and revised != current_command:
                    emit("subtask_reflected", {
                        "goal_id": plan.goal_id,
                        "task_id": subtask.task_id,
                        "action": "revise",
                        "original": current_command[:80],
                        "revised": revised[:80],
                    })
                    current_command = revised

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
