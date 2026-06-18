"""Arix Autonomous Goal Execution — Supervisor loop with:
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

_LLM_DECOMPOSE_SYSTEM = """You are Arix's goal decomposition engine. Break a multi-step goal into concrete, atomic sub-commands.

THINK FIRST — reason through:
1. What is the logical sequence of steps?
2. Which steps are prerequisites for others? (e.g., create folder before creating file in it)
3. What could fail? Plan around it.
4. Are there sensitive actions (deleting files, sending messages, purchases, system changes) that need user confirmation?

RULES:
1. Output ONLY a JSON array of command strings — no prose, no markdown, no explanation.
2. Each command must be atomic — accomplishes exactly one thing (one file, one search, one action).
3. Maximum 10 commands. Minimum 2 commands.
4. Use natural language — Arix will parse and route each command.
5. Commands must be sequential and build on each other logically.
6. Be specific about file paths, using ~/ for home directory.
7. If a step depends on output from a prior step, describe what to do with that output.
8. For sensitive actions (delete, send message, publish, purchase), always scan/preview first, then act.

EXAMPLES:
Goal: "research the top 5 LLM APIs and create a comparison spreadsheet"
Output: ["search the web for top 5 LLM APIs pricing and features 2026", "search the web for OpenAI vs Anthropic vs Gemini vs Cohere API performance benchmarks", "create file ~/Desktop/llm_comparison.md with a structured comparison table of the research findings"]

Goal: "check git status and commit any changed files with message 'daily update'"
Output: ["git status in current directory", "git add all changed files in current directory", "git commit with message 'daily update'"]

Goal: "delete temp files from my PC"
Output: ["scan temp files older than 7 days dry run preview", "delete temp files older than 7 days including browser cache and python cache"]

Goal: "open TikTok and go to upload"
Output: ["open TikTok web app", "navigate to TikTok upload page"]

Goal: "open Instagram and scroll through reels"
Output: ["open Instagram web app", "navigate to Instagram reels section"]

Goal: "send a WhatsApp message to John saying I will be late"
Output: ["open WhatsApp web app messages", "search for contact John in WhatsApp", "type message I will be late in WhatsApp chat"]

Goal: "start recording on OBS Studio"
Output: ["open OBS Studio app", "click Start Recording button in OBS Studio"]

Goal: "post on LinkedIn about my new project"
Output: ["open LinkedIn feed to compose a post", "type post content about new project in LinkedIn"]

Goal: "search the web for Python async best practices and save to a file"
Output: ["search the web for Python async await best practices 2026", "search the web for asyncio common patterns and mistakes Python", "create file ~/async_notes.md with the research findings organized by topic"]

Goal: "organize my downloads folder by creating subfolders for each file type"
Output: ["list files in ~/Downloads", "create folder ~/Downloads/Images", "create folder ~/Downloads/Documents", "create folder ~/Downloads/Archives", "search for image files in ~/Downloads", "search for pdf and document files in ~/Downloads"]

Goal: "open Excel and create a budget spreadsheet"
Output: ["open Microsoft Excel", "create spreadsheet ~/Desktop/budget.xlsx with headers Month Income Expenses Balance"]

Goal: "clean up my PC and free up disk space"
Output: ["check system disk usage", "scan temp files older than 7 days dry run", "delete temp files older than 7 days", "list large files in ~/Downloads"]"""


_REFLECT_SYSTEM = """You are Arix's error recovery engine. A step in an autonomous goal has failed.
Your job is to suggest ONE revised approach that avoids the same failure.

Rules:
1. Output ONLY a single revised command string — no prose, no explanation, no JSON.
2. The revised command should accomplish the same intent using a different approach.
3. If the error suggests a missing file or directory, suggest creating it first.
4. If the error suggests a permission issue, suggest an alternative path (~/Downloads or /tmp).
5. If the error is network-related, suggest a simpler alternative or different search terms.
6. If the error is clearly unrecoverable (binary missing, service down), output: SKIP
7. Keep the revised command concise — Arix will parse it."""


# ── Self-healing patterns: (error_fragment, recovery_command_template) ─────────
# These fire BEFORE LLM reflection to fix common recoverable errors instantly.
_SELF_HEAL_PATTERNS: list[tuple[str, str]] = [
    ("no such file or directory", "create folder {parent}"),
    ("not a directory", "create folder {parent}"),
    ("file not found", "create folder {parent}"),
    ("permission denied", ""),          # handled separately → suggest /tmp
    ("no module named", ""),            # unrecoverable in this context → SKIP
    ("command not found", ""),          # tool missing → SKIP
]


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
    # Digital employee task patterns
    r'^open .{3,30} and\b',            # "open TikTok and go to messages"
    r'\bsend .{5,} (to|for)\b',        # "send a message to John"
    r'^delete .{5,} from\b',           # "delete temp files from my PC"
    r'^clean(?: up)? .{5,}\b',         # "clean up my downloads folder"
    r'^free .{3,} (space|disk)\b',     # "free up disk space"
    r'^organize .{5,}\b',              # "organize my downloads"
    r'^post .{5,} (on|to)\b',          # "post a photo on Instagram"
    r'^upload .{5,} (to|on)\b',        # "upload a video to YouTube"
    r'^message .{3,} (saying|with|about)\b',  # "message John saying I'll be late"
    r'(from|on) my (pc|computer|laptop|mac|desktop)\b',  # "...from my PC"
    r'\b(temp|temporary|junk|cache) files?\b',  # "temp files"
    r'^backup .{5,}\b',                # "backup my documents"
    r'^download .{5,} and\b',          # "download X and save it"
    r'^(schedule|set up|book) .{5,}\b', # "schedule a meeting"
    r'^(start|begin|stop|end) (recording|streaming|broadcast)',  # OBS
]

_SIMPLE_PATTERNS = [
    r'^(list|show|check|read|close|git|system|monitor)\b',
    r'^what\b',
    r'^how\b',
    r'^why\b',
    r'^explain\b',
    r'^open (chrome|firefox|excel|word|obs|spotify|slack|discord|zoom|terminal|calculator|notepad)\s*$',
]

# Tasks that are always treated as multi-step digital employee goals
_ALWAYS_GOAL_PHRASES = [
    "delete temp files",
    "delete temporary files",
    "clean up temp",
    "clean temp files",
    "free up space",
    "free disk space",
    "clear cache",
    "clean up my",
    "organize my",
    "back up my",
    "backup my",
    "start recording",
    "stop recording",
    "start streaming",
    "stop streaming",
    "go live on",
    "post on instagram",
    "post on tiktok",
    "post on linkedin",
    "upload to youtube",
    "upload to tiktok",
    "send a message to",
    "send whatsapp",
    "send message to",
    "open and go to",
]


def is_multi_step_goal(command: str) -> bool:
    lower = command.lower().strip()

    # Always-goal phrases override simple pattern check
    for phrase in _ALWAYS_GOAL_PHRASES:
        if phrase in lower:
            return True

    for sp in _SIMPLE_PATTERNS:
        if re.match(sp, lower):
            return False

    word_count = len(lower.split())
    if word_count < 6:
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

    # ── Self-healing: instant recovery for common errors ─────────────────────

    def _self_heal(self, command: str, error: str) -> str | None:
        """Return an immediate recovery command for well-known error patterns.

        This fires BEFORE the slower LLM reflection pass so the retry loop can
        attempt a fix on the very next attempt without an extra API round-trip.
        Returns a revised command string, "SKIP" to skip the step, or None when
        no instant fix is available.
        """
        err_low = error.lower()

        # Missing directory → try to create the parent folder first
        if any(p in err_low for p in ("no such file or directory", "not a directory",
                                       "file not found", "no such file")):
            import re as _re
            # Extract a path-like token from the command
            path_match = _re.search(r'~/[\w/.\-]+|/[\w/.\-]+', command)
            if path_match:
                raw_path = path_match.group(0)
                from pathlib import Path as _Path
                parent = str(_Path(raw_path).parent)
                if parent and parent not in ("/", "~"):
                    return f"create folder {parent}"
            return None  # can't determine path — fall through to LLM

        # Permission denied → suggest /tmp as the target directory
        if "permission denied" in err_low:
            import re as _re
            path_match = _re.search(r'(~/[\w/.\-]+|/[\w/.\-]+)', command)
            if path_match:
                from pathlib import Path as _Path
                filename = _Path(path_match.group(0)).name
                return f"{command.replace(path_match.group(0), f'/tmp/{filename}')}"
            return None

        # Missing Python module / binary → unrecoverable in this context
        if any(p in err_low for p in ("no module named", "command not found",
                                       "not installed", "modulenotfounderror")):
            return "SKIP"

        return None

    # ── Adaptive goal re-planning ─────────────────────────────────────────────

    async def _adaptive_replan(
        self,
        plan: "GoalPlan",
        failed_subtask: "SubTask",
        current_index: int,
        emit,
    ) -> bool:
        """Ask the LLM to synthesize a revised plan for the remaining steps.

        Replaces the not-yet-executed subtasks in *plan* with the LLM's revised
        commands.  Emits a ``goal_replanning`` event so the UI can show the user
        what changed.  Returns True if re-planning succeeded and new steps were
        injected, False otherwise.
        """
        if self._llm_client is None or not self._llm_client.is_available():
            return False
        if not hasattr(self._llm_client, "synthesize_remaining"):
            return False

        completed = [t.command for t in plan.subtasks[:current_index] if t.status == "success"]
        remaining = [t.command for t in plan.subtasks[current_index + 1:] if not t.skip]

        try:
            new_commands = await self._llm_client.synthesize_remaining(
                goal=plan.goal,
                completed_steps=completed,
                failed_step=failed_subtask.command,
                failure_error=failed_subtask.result_summary,
                remaining_steps=remaining,
            )
        except Exception:
            return False

        if not new_commands:
            return False

        # Check for unrecoverable signal
        if len(new_commands) == 1 and new_commands[0].startswith("GOAL_FAILED:"):
            reason = new_commands[0][len("GOAL_FAILED:"):].strip()
            emit("goal_error", {
                "goal_id": plan.goal_id,
                "error": f"LLM determined goal is unrecoverable: {reason}",
                "replanning_triggered": True,
            })
            plan.status = "failed"
            return False

        # Splice the new commands into the plan, replacing everything from
        # current_index+1 onward with freshly synthesized subtasks.
        old_remaining_count = len(plan.subtasks) - (current_index + 1)
        new_subtasks = [
            SubTask(
                task_id=str(uuid.uuid4())[:8],
                description=cmd[:120],
                command=cmd,
                max_attempts=self.max_retries,
            )
            for cmd in new_commands
        ]
        plan.subtasks = plan.subtasks[: current_index + 1] + new_subtasks
        plan.total_steps = len(plan.subtasks)

        emit("goal_replanning", {
            "goal_id": plan.goal_id,
            "failed_step": failed_subtask.description[:80],
            "old_remaining": old_remaining_count,
            "new_remaining": len(new_subtasks),
            "new_steps": [t.description for t in new_subtasks],
        })
        return True

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

        Delegates to llm_client.reflect() (the canonical ReflectionPrompt template)
        if available; falls back to direct _call with _REFLECT_SYSTEM.

        Returns revised command string, "SKIP" to skip the step, or None if LLM unavailable.
        """
        if self._llm_client is None or not self._llm_client.is_available():
            return None

        # Use the canonical reflect() method on LLMClient (Gap #3 proper integration)
        if hasattr(self._llm_client, "reflect"):
            return await self._llm_client.reflect(
                command=command,
                error=error,
                goal=goal,
                previous_results=previous_results,
                max_tokens=200,
            )

        # Fallback: direct call with local _REFLECT_SYSTEM template
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
                max_tokens=200,
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
            base = Path(tempfile.gettempdir()) / "arix_checkpoints"
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
        """Roll back a goal by:
        1. Restoring checkpointed files that existed before execution.
        2. Deleting files that were newly created during execution.
        """
        plan = self._active_goals.get(goal_id)
        results = {
            "goal_id": goal_id,
            "restored": [],
            "deleted": [],
            "errors": [],
        }

        if plan:
            # ── 1. Restore pre-execution file snapshots ───────────────────
            if plan.checkpoint_dir:
                ckpt = Path(plan.checkpoint_dir)
                if ckpt.exists():
                    for snap_file in ckpt.iterdir():
                        if not snap_file.is_file():
                            continue
                        # Find the original path via the episodic record in
                        # files_created; best-effort restoration uses stem matching
                        try:
                            # Attempt to restore to the file path tracked in plan
                            # We stored: ckpt / original_filename (possibly suffixed)
                            # We restore to any matching file in files_created or cwd
                            stem = snap_file.stem.split("_")[0]  # strip counter suffix
                            restored = False
                            for candidate in plan.files_created:
                                cpath = Path(candidate)
                                if cpath.stem == stem or cpath.name == snap_file.name:
                                    shutil.copy2(str(snap_file), str(cpath))
                                    results["restored"].append(str(cpath))
                                    restored = True
                                    break
                            if not restored:
                                # Copy back to cwd as a best-effort recovery
                                dest = Path.home() / snap_file.name
                                shutil.copy2(str(snap_file), str(dest))
                                results["restored"].append(str(dest))
                        except Exception as e:
                            results["errors"].append(f"restore {snap_file.name}: {e}")

            # ── 2. Delete newly created files ─────────────────────────────
            for fp in plan.files_created:
                try:
                    p = Path(fp)
                    if p.exists():
                        p.unlink()
                        results["deleted"].append(fp)
                except Exception as e:
                    results["errors"].append(f"delete {fp}: {e}")

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
                        # Before giving up, attempt a full goal re-synthesis.
                        # If the LLM can suggest a revised path forward we inject
                        # those steps into the plan and continue executing.
                        replanned = await self._adaptive_replan(plan, subtask, i, emit)
                        if replanned:
                            # Re-synthesis succeeded — continue with the new steps.
                            # The loop will advance to i+1 which is now the first
                            # newly synthesized step.
                            continue
                        plan.status = "failed"
                        emit("goal_error", {
                            "goal_id": plan.goal_id,
                            "error": f"Blocking step failed: {subtask.description}",
                            "replanning_attempted": True,
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

        # v8.4: Notify Hermes Curator of goal completion
        curator_triggered = False
        try:
            from arix.intelligence.curator import get_curator
            curator = get_curator()
            should_run = curator.on_goal_completed(
                goal=goal,
                steps_completed=plan.completed_steps,
                success=True,
            )
            if should_run:
                asyncio.create_task(curator.run_loop())
                curator_triggered = True
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
            "curator_triggered": curator_triggered,
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
        """Execute one sub-task with progressive retry escalation.

        Retry strategy:
          attempt 0  — direct execution
          attempt 1  — instant self-heal (pattern-based, no LLM call)
          attempt 2  — LLM reflection (revised command via ReflectionPrompt)
          attempt 3+ — (handled at goal level via _adaptive_replan)
        """
        subtask.status = "running"
        last_error = ""
        current_command = subtask.command

        max_total = subtask.max_attempts + 1  # +1 for initial attempt
        for attempt in range(max_total):
            subtask.attempt = attempt

            if attempt > 0:
                backoff = min(1.5 * attempt, 8.0)  # cap at 8 s
                await asyncio.sleep(backoff)
                emit("subtask_retry", {
                    "goal_id": plan.goal_id,
                    "task_id": subtask.task_id,
                    "attempt": attempt + 1,
                    "strategy": "self_heal" if attempt == 1 else "reflection",
                    "revised_command": (
                        current_command if current_command != subtask.command else None
                    ),
                })

            try:
                results = []
                task_id = str(uuid.uuid4())
                # Tools whose execution may overwrite an EXISTING file on disk.
                # We snapshot these paths BEFORE execution so rollback can restore them.
                _SNAPSHOT_TOOLS = frozenset({
                    "create_file", "move_file", "copy_file",
                    "write_tests", "refactor_code",
                })
                # Which arg keys carry a destination/target file path
                _PATH_ARGS = ("path", "destination", "file_path")

                async for event in self._run_command(current_command, task_id):
                    if event.type == "plan":
                        # Gap #9: snapshot existing files before they can be overwritten
                        for step in event.data.get("steps", []):
                            tool = step.get("tool", "")
                            if tool in _SNAPSHOT_TOOLS:
                                args = step.get("args_preview", step.get("args", {}))
                                for field in _PATH_ARGS:
                                    fp = args.get(field, "")
                                    if fp and isinstance(fp, str):
                                        self.checkpoint_file(plan, fp)
                    elif event.type == "step_complete":
                        r = event.data.get("result", {})
                        if "error" not in r:
                            results.append(str(r)[:100])
                            # Gap #9: track files created (for deletion on rollback)
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

            # ── Progressive retry escalation ──────────────────────────────────
            if attempt >= max_total - 1:
                break  # exhausted all attempts

            if attempt == 0:
                # Attempt 1: instant self-heal (pattern-based, no API call)
                healed = self._self_heal(current_command, last_error)
                if healed == "SKIP":
                    subtask.status = "skipped"
                    subtask.result_summary = "Self-heal: step deemed unrecoverable"
                    emit("subtask_reflected", {
                        "goal_id": plan.goal_id,
                        "task_id": subtask.task_id,
                        "action": "skip",
                        "strategy": "self_heal",
                        "reason": last_error[:120],
                    })
                    return False
                elif healed:
                    emit("subtask_reflected", {
                        "goal_id": plan.goal_id,
                        "task_id": subtask.task_id,
                        "action": "revise",
                        "strategy": "self_heal",
                        "original": current_command[:80],
                        "revised": healed[:80],
                    })
                    current_command = healed
                    continue  # immediately retry with healed command (no extra sleep)

            # Attempt 2+: LLM reflection
            if self._llm_client and self._llm_client.is_available():
                revised = await self._reflect_on_failure(
                    command=current_command,
                    error=last_error,
                    goal=plan.goal,
                    previous_results=previous_results,
                )
                if revised == "SKIP":
                    subtask.status = "skipped"
                    subtask.result_summary = "LLM reflection: step deemed unrecoverable"
                    emit("subtask_reflected", {
                        "goal_id": plan.goal_id,
                        "task_id": subtask.task_id,
                        "action": "skip",
                        "strategy": "reflection",
                        "reason": last_error[:120],
                    })
                    return False
                elif revised and revised != current_command:
                    emit("subtask_reflected", {
                        "goal_id": plan.goal_id,
                        "task_id": subtask.task_id,
                        "action": "revise",
                        "strategy": "reflection",
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
