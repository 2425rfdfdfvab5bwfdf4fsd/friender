"""Parallel Multi-Agent Dispatcher — OpenClaw/OpenFang-inspired.

Runs multiple specialist agents concurrently for complex commands that
benefit from parallelism (e.g. "research AND code AND analyze").
Synthesizes all results into a unified response via the LLM.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, List, Optional

log = logging.getLogger(__name__)


@dataclass
class AgentResult:
    role: str
    icon: str
    output: str
    duration_s: float
    success: bool
    error: str = ""


@dataclass
class DispatchPlan:
    command: str
    roles: List[str]
    reason: str
    parallel: bool = True


# Keywords that suggest multi-domain intent
_PARALLEL_TRIGGERS = [
    ("research", "code"),
    ("research", "analyze"),
    ("search", "write"),
    ("find", "create"),
    ("look up", "implement"),
    ("gather", "build"),
    ("study", "develop"),
]

_MULTI_DOMAIN_WORDS = [
    "and then", "also", "additionally", "as well as",
    "while", "simultaneously", "at the same time",
    "both", "combined", "together",
]


def should_parallelize(command: str) -> Optional[DispatchPlan]:
    """Detect if a command benefits from parallel agent dispatch.
    
    Returns a DispatchPlan if parallelism is warranted, else None.
    """
    lower = command.lower()

    # Check multi-domain trigger pairs
    detected_roles = []
    for kw_a, kw_b in _PARALLEL_TRIGGERS:
        if kw_a in lower and kw_b in lower:
            if "researcher" not in detected_roles:
                detected_roles.append("researcher")
            if kw_b in ("code", "implement", "develop", "build"):
                if "coder" not in detected_roles:
                    detected_roles.append("coder")
            if kw_b in ("analyze", "report", "metrics"):
                if "analyst" not in detected_roles:
                    detected_roles.append("analyst")

    # Connective words suggest multi-step multi-domain work
    multi_word_found = any(w in lower for w in _MULTI_DOMAIN_WORDS)
    if multi_word_found and len(detected_roles) == 0:
        return None  # Multi-step but not clearly multi-domain

    if len(detected_roles) >= 2:
        return DispatchPlan(
            command=command,
            roles=detected_roles,
            reason=f"Detected {' + '.join(detected_roles)} domains",
            parallel=True,
        )
    return None


class ParallelDispatcher:
    """Runs specialist agents in parallel and synthesizes results."""

    def __init__(self) -> None:
        self._run_command_fn: Optional[Callable] = None
        self._llm_client: Any = None
        self._active_dispatches: List[dict] = []
        self._history: List[dict] = []

    def set_command_fn(self, fn: Callable) -> None:
        self._run_command_fn = fn

    def set_llm_client(self, client: Any) -> None:
        self._llm_client = client

    async def dispatch(
        self,
        plan: DispatchPlan,
    ) -> AsyncIterator[str]:
        """Execute the dispatch plan, yielding streamed output."""
        if self._run_command_fn is None:
            yield "⚠️ Parallel dispatch not configured.\n"
            return

        t0 = time.time()
        record = {
            "command": plan.command[:120],
            "roles": plan.roles,
            "started_at": t0,
            "status": "running",
        }
        self._active_dispatches.append(record)

        yield f"⚡ **Parallel Dispatch** — spawning {len(plan.roles)} agents simultaneously\n"
        for role in plan.roles:
            yield f"  › Launching **{role}** agent…\n"
        yield "\n"

        # Build per-role sub-commands
        role_commands = self._build_role_commands(plan)

        # Run all agents concurrently
        tasks = [
            asyncio.create_task(
                self._run_agent(role, cmd),
                name=f"agent-{role}",
            )
            for role, cmd in role_commands.items()
        ]

        results: List[AgentResult] = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions
        clean_results: List[AgentResult] = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                role = list(role_commands.keys())[i]
                clean_results.append(AgentResult(
                    role=role, icon="⚠️",
                    output=f"Agent error: {r}", duration_s=0,
                    success=False, error=str(r),
                ))
            else:
                clean_results.append(r)

        # Stream individual results
        for res in clean_results:
            status = "✅" if res.success else "⚠️"
            yield f"{status} **{res.icon} {res.role.title()} agent** ({res.duration_s:.1f}s):\n"
            yield res.output[:1200] + "\n\n"

        # Synthesize with LLM if available
        if self._llm_client and self._llm_client.is_available() and len(clean_results) > 1:
            yield "🔀 **Synthesizing results…**\n\n"
            synthesis = await self._synthesize(plan.command, clean_results)
            yield synthesis + "\n"

        duration = time.time() - t0
        record["status"] = "done"
        record["duration_s"] = round(duration, 2)
        self._history.append(record)
        if len(self._history) > 50:
            self._history = self._history[-50:]
        self._active_dispatches = [d for d in self._active_dispatches if d is not record]

    def _build_role_commands(self, plan: DispatchPlan) -> dict[str, str]:
        """Build a focused sub-command for each role."""
        cmd = plan.command
        role_cmds = {}
        for role in plan.roles:
            if role == "researcher":
                role_cmds[role] = f"research: {cmd}"
            elif role == "coder":
                role_cmds[role] = f"write code for: {cmd}"
            elif role == "analyst":
                role_cmds[role] = f"analyze and report on: {cmd}"
            elif role == "planner":
                role_cmds[role] = f"create a plan for: {cmd}"
            else:
                role_cmds[role] = cmd
        return role_cmds

    async def _run_agent(self, role: str, command: str) -> AgentResult:
        """Run a single agent and collect its full output."""
        ICONS = {
            "researcher": "🔬", "coder": "💻",
            "analyst": "📊", "planner": "🗺️",
        }
        icon = ICONS.get(role, "🤖")
        t0 = time.time()
        try:
            chunks = []
            async for chunk in self._run_command_fn(command):
                if isinstance(chunk, str):
                    chunks.append(chunk)
                elif hasattr(chunk, "text"):
                    chunks.append(chunk.text)
            output = "".join(chunks).strip() or "(no output)"
            return AgentResult(
                role=role, icon=icon,
                output=output,
                duration_s=round(time.time() - t0, 2),
                success=True,
            )
        except Exception as e:
            return AgentResult(
                role=role, icon=icon,
                output=f"Failed: {e}",
                duration_s=round(time.time() - t0, 2),
                success=False,
                error=str(e),
            )

    async def _synthesize(
        self, original_cmd: str, results: List[AgentResult]
    ) -> str:
        """Use the LLM to synthesize multi-agent results into a coherent response."""
        parts = [f"Original request: {original_cmd}\n"]
        for r in results:
            parts.append(f"\n{r.icon} {r.role.title()} agent output:\n{r.output[:600]}")

        system = (
            "You are a senior AI coordinator. Multiple specialist agents have each "
            "tackled a different aspect of the user's request in parallel. Synthesize "
            "their outputs into a single, coherent, well-organized response. "
            "Highlight key findings, resolve any conflicts, and provide a clear summary. "
            "Be concise — aim for 3-5 paragraphs maximum."
        )
        try:
            return await self._llm_client._call(
                system, "\n".join(parts), max_tokens=600
            )
        except Exception as e:
            log.debug("Synthesis error: %s", e)
            return "(Synthesis unavailable — see individual agent outputs above)"

    def get_status(self) -> dict:
        return {
            "active_dispatches": len(self._active_dispatches),
            "total_dispatched": len(self._history),
            "recent": self._history[-5:],
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

_dispatcher: Optional[ParallelDispatcher] = None


def get_dispatcher() -> ParallelDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = ParallelDispatcher()
    return _dispatcher
