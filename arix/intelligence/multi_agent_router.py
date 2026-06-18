"""Multi-Agent Router — OpenClaw-inspired specialist agent dispatch.

Routes commands to isolated specialist agents (Planner, Coder, Researcher, Ops)
each with their own workspace, private memory, persona, and tool allowlist.
Inspired by OpenClaw's multi-agent routing and Moxxy's isolated workspaces.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

# ── Agent role definitions ────────────────────────────────────────────────────

@dataclass
class AgentRole:
    name: str
    persona: str
    tool_domains: List[str]
    keywords: List[str]
    patterns: List[str]
    workspace_subdir: str
    icon: str
    description: str


AGENT_ROLES: List[AgentRole] = [
    AgentRole(
        name="researcher",
        persona=(
            "You are Arix's Research Specialist. Your expertise is web research, "
            "information synthesis, fact-checking, and producing structured reports. "
            "You prefer thorough multi-source research before drawing conclusions."
        ),
        tool_domains=["browser", "research", "file", "document"],
        keywords=[
            "research", "look up", "find out", "search for", "investigate",
            "what is", "how does", "explain", "summarize", "report on",
            "compare", "analyze", "study", "survey", "review", "learn about",
        ],
        patterns=[
            r"^research\b",
            r"^search (the web|for|online)\b",
            r"^find (out|information|data)\b",
            r"^look up\b",
            r"^summarize\b",
            r"^explain\b",
            r"\b(news|article|paper|study|report)\b",
        ],
        workspace_subdir="researcher",
        icon="🔬",
        description="Web research, synthesis, and report generation",
    ),
    AgentRole(
        name="coder",
        persona=(
            "You are Arix's Coding Specialist. Your expertise is writing, reviewing, "
            "refactoring, and debugging code. You produce clean, well-tested, idiomatic "
            "code with clear documentation. You always consider edge cases."
        ),
        tool_domains=["coding", "file", "git"],
        keywords=[
            "code", "script", "function", "class", "program", "write code",
            "generate code", "refactor", "debug", "fix bug", "test", "unit test",
            "implement", "build a", "develop", "create a script", "python", "javascript",
            "typescript", "rust", "go", "sql", "api", "endpoint",
        ],
        patterns=[
            r"^(write|generate|create) (a |the )?(code|script|function|class|program|test)\b",
            r"^(refactor|debug|fix|review|improve) (the |this |my )?(code|script|function|class)\b",
            r"^implement\b",
            r"\b(bug|error|exception|crash|failing test)\b",
            r"^run code\b",
            r"^explain (this |the )?code\b",
        ],
        workspace_subdir="coder",
        icon="💻",
        description="Code generation, review, debugging, and testing",
    ),
    AgentRole(
        name="ops",
        persona=(
            "You are Arix's Operations Specialist. Your expertise is system administration, "
            "file management, disk cleanup, process monitoring, backups, and automation. "
            "You are methodical and always verify before destructive operations."
        ),
        tool_domains=["file", "system", "app", "desktop"],
        keywords=[
            "delete", "move", "copy", "rename", "clean", "cleanup", "organize",
            "backup", "archive", "compress", "disk", "memory", "cpu", "process",
            "monitor", "system", "temp files", "cache", "free space", "storage",
        ],
        patterns=[
            r"^(clean|cleanup|organize|backup|archive)\b",
            r"^(delete|remove|trash) .{5,}\b",
            r"^(free|check) (disk|storage|space)\b",
            r"^(monitor|check) (system|cpu|memory|ram|disk)\b",
            r"\b(temp|temporary|junk|cache) files?\b",
            r"^compress\b",
        ],
        workspace_subdir="ops",
        icon="⚙️",
        description="File management, system monitoring, and automation",
    ),
    AgentRole(
        name="planner",
        persona=(
            "You are Arix's Planning Specialist. Your expertise is goal decomposition, "
            "workflow design, task sequencing, and project coordination. You break complex "
            "goals into clear, achievable steps with explicit dependencies."
        ),
        tool_domains=["file", "research", "coding", "system"],
        keywords=[
            "plan", "design", "architect", "strategy", "roadmap", "outline",
            "break down", "decompose", "sequence", "workflow", "project",
            "schedule", "organize tasks", "coordinate", "prioritize",
        ],
        patterns=[
            r"^(plan|design|architect)\b",
            r"^(create|make|build) (a |the )?(plan|roadmap|strategy|workflow)\b",
            r"^(break down|decompose|outline)\b",
            r"\b(multi.?step|complex goal|project plan)\b",
        ],
        workspace_subdir="planner",
        icon="🗺️",
        description="Goal decomposition, workflow design, and project planning",
    ),
]


# ── Routing logic ─────────────────────────────────────────────────────────────

class MultiAgentRouter:
    """Routes commands to the most appropriate specialist agent."""

    def __init__(self) -> None:
        self._active_agents: Dict[str, "AgentSession"] = {}
        self._routing_history: List[dict] = []
        self._run_command_fn: Optional[Callable] = None
        self._llm_client: Any = None

    def set_command_fn(self, fn: Callable) -> None:
        self._run_command_fn = fn

    def set_llm_client(self, client: Any) -> None:
        self._llm_client = client

    def detect_role(self, command: str) -> Optional[AgentRole]:
        """Detect the best specialist role for a command using keywords + patterns."""
        lower = command.lower().strip()
        scores: Dict[str, int] = {role.name: 0 for role in AGENT_ROLES}

        for role in AGENT_ROLES:
            for kw in role.keywords:
                if kw in lower:
                    scores[role.name] += 1
            for pat in role.patterns:
                if re.search(pat, lower, re.IGNORECASE):
                    scores[role.name] += 3

        best_name = max(scores, key=lambda k: scores[k])
        best_score = scores[best_name]

        if best_score == 0:
            return None

        for role in AGENT_ROLES:
            if role.name == best_name:
                return role
        return None

    async def llm_detect_role(self, command: str) -> Optional[str]:
        """Use LLM to detect specialist role when heuristics are ambiguous."""
        if self._llm_client is None or not self._llm_client.is_available():
            return None
        try:
            system = (
                "You classify user commands into one of these specialist agent roles:\n"
                "- researcher: web search, summarization, fact-finding, reports\n"
                "- coder: code generation, debugging, refactoring, testing\n"
                "- ops: file ops, system admin, cleanup, monitoring, backup\n"
                "- planner: goal decomposition, workflow design, project planning\n"
                "- none: general assistant (chit-chat, settings, memory)\n\n"
                "Respond with ONLY the role name, nothing else."
            )
            role_name = await self._llm_client._call(system, f"Command: {command}", max_tokens=10)
            role_name = role_name.strip().lower()
            for role in AGENT_ROLES:
                if role.name == role_name:
                    return role_name
            return None
        except Exception:
            return None

    def get_or_create_session(self, role: AgentRole) -> "AgentSession":
        if role.name not in self._active_agents:
            self._active_agents[role.name] = AgentSession(role=role)
        return self._active_agents[role.name]

    def get_all_sessions(self) -> List[dict]:
        return [s.to_dict() for s in self._active_agents.values()]

    def get_routing_history(self, limit: int = 20) -> List[dict]:
        return self._routing_history[-limit:]

    def record_routing(self, command: str, role_name: str, duration_ms: float) -> None:
        self._routing_history.append({
            "ts": time.time(),
            "command": command[:100],
            "role": role_name,
            "duration_ms": round(duration_ms, 1),
        })
        if len(self._routing_history) > 200:
            self._routing_history = self._routing_history[-200:]

    async def route(self, command: str) -> tuple[Optional[AgentRole], str]:
        """Detect and return (role, detection_method).

        Returns (None, 'general') when no specialist is needed.
        """
        t0 = time.monotonic()

        role = self.detect_role(command)
        method = "heuristic"

        if role is None and self._llm_client is not None:
            role_name = await self.llm_detect_role(command)
            if role_name:
                for r in AGENT_ROLES:
                    if r.name == role_name:
                        role = r
                        method = "llm"
                        break

        duration_ms = (time.monotonic() - t0) * 1000
        self.record_routing(command, role.name if role else "general", duration_ms)

        return role, method


@dataclass
class AgentSession:
    """Represents an active specialist agent with its own workspace and context."""
    role: AgentRole
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: float = field(default_factory=time.time)
    tasks_completed: int = 0
    tasks_failed: int = 0
    last_active: float = field(default_factory=time.time)
    context_snippets: List[str] = field(default_factory=list)

    @property
    def workspace_path(self) -> Path:
        p = Path.home() / ".arix" / "agents" / self.role.workspace_subdir
        p.mkdir(parents=True, exist_ok=True)
        return p

    def add_context(self, snippet: str) -> None:
        self.context_snippets.append(snippet[:300])
        if len(self.context_snippets) > 10:
            self.context_snippets = self.context_snippets[-10:]
        self.last_active = time.time()

    def get_system_prompt_suffix(self) -> str:
        """Extra context injected into the LLM system prompt for this role."""
        parts = [f"\n\n{self.role.persona}"]
        parts.append(f"\nYour private workspace: {self.workspace_path}")
        if self.context_snippets:
            parts.append("\nRecent context from prior tasks in this session:")
            for snip in self.context_snippets[-3:]:
                parts.append(f"  - {snip}")
        return "\n".join(parts)

    def to_dict(self) -> dict:
        return {
            "role": self.role.name,
            "icon": self.role.icon,
            "description": self.role.description,
            "session_id": self.session_id,
            "workspace": str(self.workspace_path),
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "last_active": self.last_active,
            "context_size": len(self.context_snippets),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

_router: Optional[MultiAgentRouter] = None


def get_router() -> MultiAgentRouter:
    global _router
    if _router is None:
        _router = MultiAgentRouter()
    return _router
