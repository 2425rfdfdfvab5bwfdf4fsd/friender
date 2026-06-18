"""Capability Hands catalog — OpenFang-inspired autonomous capability packs.

Each Hand is a self-contained unit combining:
  - Expert knowledge base (domain context injected into planning)
  - Tool allowlist (restricts which tools the Hand may use)
  - Execution plan templates (pre-built plans for common tasks)
  - Performance metrics (tracks success rates and usage)
  - Specialized persona (overrides the generic Arix assistant prompt)
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_HANDS_STATE_FILE = Path.home() / ".arix" / "hands_state.json"


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class HandPlan:
    """A pre-built execution template for a specific task type."""
    name: str
    trigger_keywords: List[str]
    description: str
    steps: List[str]
    estimated_duration_s: int = 30


@dataclass
class HandMetrics:
    runs: int = 0
    successes: int = 0
    failures: int = 0
    avg_duration_s: float = 0.0
    last_run: float = 0.0

    def record(self, success: bool, duration_s: float) -> None:
        self.runs += 1
        if success:
            self.successes += 1
        else:
            self.failures += 1
        n = self.runs
        self.avg_duration_s = ((self.avg_duration_s * (n - 1)) + duration_s) / n
        self.last_run = time.time()

    @property
    def success_rate(self) -> float:
        if self.runs == 0:
            return 0.0
        return round(self.successes / self.runs * 100, 1)

    def to_dict(self) -> dict:
        return {
            "runs": self.runs,
            "successes": self.successes,
            "failures": self.failures,
            "avg_duration_s": round(self.avg_duration_s, 1),
            "last_run": self.last_run,
            "success_rate": self.success_rate,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HandMetrics":
        m = cls()
        m.runs = d.get("runs", 0)
        m.successes = d.get("successes", 0)
        m.failures = d.get("failures", 0)
        m.avg_duration_s = d.get("avg_duration_s", 0.0)
        m.last_run = d.get("last_run", 0.0)
        return m


@dataclass
class Hand:
    hand_id: str
    name: str
    icon: str
    description: str
    version: str
    category: str
    tool_domains: List[str]
    knowledge: List[str]           # Expert knowledge bullets injected into context
    plans: List[HandPlan]
    persona: str
    active: bool = True
    metrics: HandMetrics = field(default_factory=HandMetrics)
    installed_at: float = field(default_factory=time.time)

    def get_context_injection(self) -> str:
        """Returns expert knowledge to inject into the planning prompt."""
        lines = [f"\n\n{self.icon} {self.name} HAND — Expert Knowledge:"]
        for bullet in self.knowledge[:8]:
            lines.append(f"  • {bullet}")
        return "\n".join(lines)

    def find_plan(self, command: str) -> Optional[HandPlan]:
        lower = command.lower()
        for plan in self.plans:
            if any(kw in lower for kw in plan.trigger_keywords):
                return plan
        return None

    def to_dict(self) -> dict:
        return {
            "hand_id": self.hand_id,
            "name": self.name,
            "icon": self.icon,
            "description": self.description,
            "version": self.version,
            "category": self.category,
            "tool_domains": self.tool_domains,
            "knowledge_count": len(self.knowledge),
            "plan_count": len(self.plans),
            "active": self.active,
            "metrics": self.metrics.to_dict(),
            "installed_at": self.installed_at,
            "plans": [
                {
                    "name": p.name,
                    "description": p.description,
                    "trigger_keywords": p.trigger_keywords,
                    "steps": p.steps,
                }
                for p in self.plans
            ],
        }


# ── Built-in Hands ────────────────────────────────────────────────────────────

RESEARCHER_HAND = Hand(
    hand_id="researcher-hand",
    name="Researcher",
    icon="🔬",
    description="Deep research, multi-source synthesis, structured reports, and fact-checking. Searches the web, extracts content, cross-references sources, and produces markdown reports.",
    version="1.0.0",
    category="Research",
    tool_domains=["browser", "research", "file", "document"],
    knowledge=[
        "Always search at least 2-3 different queries for comprehensive coverage",
        "Cross-reference facts across multiple sources before reporting",
        "Lead with an executive summary, then detail, then sources",
        "Use specific search terms: 'site:github.com' for code, 'filetype:pdf' for papers",
        "Extract full article text rather than just snippets for accurate quotes",
        "Flag uncertainty explicitly: 'Source unclear' or 'Conflicting reports'",
        "Date-stamp all findings; AI/tech information goes stale quickly",
        "Save research findings to a markdown file for later reference",
    ],
    plans=[
        HandPlan(
            name="Competitive Research",
            trigger_keywords=["compare", "vs", "versus", "competitors", "alternatives"],
            description="Multi-source competitive analysis",
            steps=[
                "search the web for {topic} overview and key features",
                "search the web for {topic} alternatives and competitors comparison",
                "search the web for {topic} reviews and user feedback 2026",
                "create file ~/research/{topic}_comparison.md with structured comparison table",
            ],
            estimated_duration_s=90,
        ),
        HandPlan(
            name="Tech Deep Dive",
            trigger_keywords=["research", "learn about", "how does", "explain"],
            description="Technical deep-dive research",
            steps=[
                "search the web for {topic} technical overview",
                "search the web for {topic} best practices and examples",
                "search the web for {topic} common pitfalls and limitations",
                "create file ~/research/{topic}_notes.md with organized findings",
            ],
            estimated_duration_s=60,
        ),
    ],
    persona=(
        "You are Arix's Research Hand — a senior research analyst. You are thorough, "
        "methodical, and always cite sources. You prefer depth over breadth and always "
        "verify claims from multiple independent sources before reporting them as fact."
    ),
)

CODER_HAND = Hand(
    hand_id="coder-hand",
    name="Coder",
    icon="💻",
    description="Code generation, debugging, refactoring, test writing, and code quality analysis. Writes idiomatic, well-documented, production-ready code in any language.",
    version="1.0.0",
    category="Development",
    tool_domains=["coding", "file", "git"],
    knowledge=[
        "Write self-documenting code; add docstrings to all public functions",
        "Include error handling for all external calls (network, file I/O, subprocess)",
        "Write unit tests alongside implementation — aim for ≥80% coverage",
        "Use type hints in Python; TypeScript strict mode over JavaScript",
        "Follow the existing code style and naming conventions in the project",
        "Always check if a library/tool exists before suggesting to install it",
        "Prefer stdlib over third-party deps for simple tasks",
        "Run code after writing to verify it works before reporting success",
        "On debug tasks: add targeted print statements, don't guess — test hypotheses",
    ],
    plans=[
        HandPlan(
            name="New Script",
            trigger_keywords=["write a script", "create a script", "write code", "generate code"],
            description="Create a new well-tested script",
            steps=[
                "generate code for {task} with error handling and docstrings",
                "write tests for the generated {task} code",
                "create file ~/{output_file} with the generated code",
            ],
            estimated_duration_s=45,
        ),
        HandPlan(
            name="Bug Fix",
            trigger_keywords=["debug", "fix bug", "fix error", "not working"],
            description="Debug and fix a failing code issue",
            steps=[
                "read file {file_path}",
                "analyze code quality of {file_path}",
                "refactor code in {file_path} to fix {issue}",
            ],
            estimated_duration_s=30,
        ),
    ],
    persona=(
        "You are Arix's Coding Hand — a senior software engineer. You write clean, "
        "tested, production-ready code. You always consider edge cases, add proper error "
        "handling, and follow the idiomatic style of the target language."
    ),
)

OPS_HAND = Hand(
    hand_id="ops-hand",
    name="Ops",
    icon="⚙️",
    description="System operations, file management, disk cleanup, process monitoring, backups, and automation. Keeps systems healthy and organized.",
    version="1.0.0",
    category="Operations",
    tool_domains=["file", "system", "app", "desktop"],
    knowledge=[
        "Always dry-run before destructive operations (delete, move, overwrite)",
        "Check disk usage before and after cleanup operations",
        "Archive before deleting — zip files older than 30 days before removing",
        "Never delete without first listing what will be deleted",
        "Prefer move-to-trash over permanent delete for safety",
        "Report before/after sizes for all cleanup operations",
        "On backup: verify the destination has enough space first",
        "Schedule recurring ops tasks as Arix workflows, not one-off commands",
    ],
    plans=[
        HandPlan(
            name="System Cleanup",
            trigger_keywords=["clean", "cleanup", "free space", "temp files", "cache"],
            description="Safe system cleanup with verification",
            steps=[
                "check system disk usage and memory",
                "scan temp files older than 7 days dry run preview",
                "delete temp files older than 7 days including browser and python cache",
                "check system disk usage after cleanup",
            ],
            estimated_duration_s=60,
        ),
        HandPlan(
            name="Backup",
            trigger_keywords=["backup", "back up", "archive"],
            description="Create a timestamped backup archive",
            steps=[
                "check disk space available",
                "zip files {source_path} to backup archive with timestamp",
                "verify backup archive was created successfully",
            ],
            estimated_duration_s=30,
        ),
    ],
    persona=(
        "You are Arix's Ops Hand — a senior DevOps/SysAdmin specialist. You are methodical "
        "and cautious. You always verify before acting and prefer reversible operations. "
        "You report sizes, counts, and durations for all operations."
    ),
)

ANALYST_HAND = Hand(
    hand_id="analyst-hand",
    name="Analyst",
    icon="📊",
    description="Data analysis, spreadsheet generation, chart descriptions, metrics calculation, and business intelligence reporting.",
    version="1.0.0",
    category="Analytics",
    tool_domains=["document", "file", "research", "coding"],
    knowledge=[
        "Start every analysis with a data quality check (nulls, outliers, types)",
        "Always state your assumptions before computing metrics",
        "Use descriptive statistics: mean, median, std dev, min/max, quartiles",
        "Present numbers in context: 'Revenue up 23% vs. prior month' not just '23%'",
        "Include data source and date range in every report",
        "Flag data freshness: when was this data last updated?",
        "Round to 2 decimal places for percentages; whole numbers for counts",
        "Export key findings as both markdown report and xlsx spreadsheet",
    ],
    plans=[
        HandPlan(
            name="Data Report",
            trigger_keywords=["analyze data", "report on", "metrics", "statistics"],
            description="Generate a structured data analysis report",
            steps=[
                "read file {data_file}",
                "create xlsx spreadsheet with analysis and charts",
                "create file ~/reports/{topic}_report.md with executive summary",
            ],
            estimated_duration_s=45,
        ),
    ],
    persona=(
        "You are Arix's Analytics Hand — a senior data analyst. You are rigorous "
        "with numbers, clear about assumptions, and always present findings with context. "
        "You produce both raw data artifacts and human-readable summaries."
    ),
)

# ── Registry of all built-in Hands ────────────────────────────────────────────

BUILTIN_HANDS: List[Hand] = [
    RESEARCHER_HAND,
    CODER_HAND,
    OPS_HAND,
    ANALYST_HAND,
]


# ── Hand Manager ──────────────────────────────────────────────────────────────

class HandManager:
    """Manages active Hands and routes commands to relevant Hands."""

    def __init__(self) -> None:
        self._hands: Dict[str, Hand] = {h.hand_id: h for h in BUILTIN_HANDS}
        self._metrics_loaded = False
        self._load_metrics()

    def _load_metrics(self) -> None:
        if self._metrics_loaded:
            return
        self._metrics_loaded = True
        try:
            if _HANDS_STATE_FILE.exists():
                data = json.loads(_HANDS_STATE_FILE.read_text())
                for hand_id, m in data.get("metrics", {}).items():
                    if hand_id in self._hands:
                        self._hands[hand_id].metrics = HandMetrics.from_dict(m)
                for hand_id, active in data.get("active", {}).items():
                    if hand_id in self._hands:
                        self._hands[hand_id].active = active
        except Exception as e:
            log.warning("Hand metrics load error: %s", e)

    def _save_metrics(self) -> None:
        try:
            _HANDS_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "metrics": {hid: h.metrics.to_dict() for hid, h in self._hands.items()},
                "active": {hid: h.active for hid, h in self._hands.items()},
            }
            _HANDS_STATE_FILE.write_text(json.dumps(data, indent=2))
        except Exception as e:
            log.warning("Hand metrics save error: %s", e)

    def list_hands(self) -> List[dict]:
        return [h.to_dict() for h in self._hands.values()]

    def get_hand(self, hand_id: str) -> Optional[Hand]:
        return self._hands.get(hand_id)

    def get_active_hands(self) -> List[Hand]:
        return [h for h in self._hands.values() if h.active]

    def toggle_hand(self, hand_id: str) -> Optional[dict]:
        hand = self._hands.get(hand_id)
        if not hand:
            return None
        hand.active = not hand.active
        self._save_metrics()
        return hand.to_dict()

    def detect_relevant_hands(self, command: str) -> List[Hand]:
        """Returns active hands whose tool domains are relevant to this command."""
        lower = command.lower()
        relevant = []
        for hand in self.get_active_hands():
            plan = hand.find_plan(command)
            if plan:
                relevant.append(hand)
        return relevant

    def get_context_for_command(self, command: str) -> str:
        """Get expert knowledge injections for a command."""
        relevant = self.detect_relevant_hands(command)
        if not relevant:
            return ""
        parts = []
        for hand in relevant[:2]:
            parts.append(hand.get_context_injection())
        return "\n".join(parts)

    def record_run(self, hand_id: str, success: bool, duration_s: float) -> None:
        hand = self._hands.get(hand_id)
        if hand:
            hand.metrics.record(success, duration_s)
            self._save_metrics()

    def get_stats(self) -> dict:
        active = self.get_active_hands()
        total_runs = sum(h.metrics.runs for h in self._hands.values())
        return {
            "total_hands": len(self._hands),
            "active_hands": len(active),
            "total_runs": total_runs,
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

_manager: Optional[HandManager] = None


def get_hand_manager() -> HandManager:
    global _manager
    if _manager is None:
        _manager = HandManager()
    return _manager
