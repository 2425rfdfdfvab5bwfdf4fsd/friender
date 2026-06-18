"""Autonomous Research Mode — HermitClaw-inspired.

When enabled, Arix autonomously picks topics from the user's history,
interests, and configured seeds, then researches them without prompting.
Findings are saved to the knowledge base and surfaced as notifications.

Like HermitClaw, the agent "lives" in an ongoing research loop — developing
a body of knowledge that reflects the user's interests over time.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional

log = logging.getLogger(__name__)

_STATE_FILE = Path.home() / ".arix" / "research_mode_state.json"
_FINDINGS_FILE = Path.home() / ".arix" / "research_findings.jsonl"
_DEFAULT_INTERVAL_MIN = 45  # minutes between auto-research sessions
_MAX_FINDINGS = 200


@dataclass
class ResearchFinding:
    finding_id: str
    topic: str
    summary: str
    source: str        # "auto" | "seeded" | "user_triggered"
    created_at: float = field(default_factory=time.time)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "finding_id": self.finding_id,
            "topic": self.topic,
            "summary": self.summary,
            "source": self.source,
            "created_at": self.created_at,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ResearchFinding":
        return cls(
            finding_id=d.get("finding_id", str(uuid.uuid4())[:8]),
            topic=d.get("topic", ""),
            summary=d.get("summary", ""),
            source=d.get("source", "auto"),
            created_at=d.get("created_at", time.time()),
            tags=d.get("tags", []),
        )


@dataclass
class ResearchState:
    enabled: bool = False
    interval_minutes: int = _DEFAULT_INTERVAL_MIN
    seed_topics: List[str] = field(default_factory=list)
    last_run_at: float = 0.0
    last_topic: str = ""
    total_sessions: int = 0
    auto_topics_from_history: bool = True


class AutonomousResearcher:
    """Background research loop that autonomously explores topics."""

    def __init__(self) -> None:
        self._state: ResearchState = ResearchState()
        self._llm_client: Any = None
        self._run_command_fn: Optional[Callable] = None
        self._memory_manager: Any = None
        self._notify_fn: Optional[Callable] = None
        self._task: Optional[asyncio.Task] = None
        self._load_state()

    def set_llm_client(self, client: Any) -> None:
        self._llm_client = client

    def set_command_fn(self, fn: Callable) -> None:
        self._run_command_fn = fn

    def set_memory_manager(self, mm: Any) -> None:
        self._memory_manager = mm

    def set_notify_fn(self, fn: Callable) -> None:
        """Optional callback(topic, summary) for push notifications."""
        self._notify_fn = fn

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load_state(self) -> None:
        try:
            if _STATE_FILE.exists():
                data = json.loads(_STATE_FILE.read_text())
                self._state = ResearchState(**{
                    k: v for k, v in data.items()
                    if k in ResearchState.__dataclass_fields__
                })
        except Exception as e:
            log.debug("Research state load error: %s", e)

    def _save_state(self) -> None:
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "enabled": self._state.enabled,
                "interval_minutes": self._state.interval_minutes,
                "seed_topics": self._state.seed_topics,
                "last_run_at": self._state.last_run_at,
                "last_topic": self._state.last_topic,
                "total_sessions": self._state.total_sessions,
                "auto_topics_from_history": self._state.auto_topics_from_history,
            }
            _STATE_FILE.write_text(json.dumps(data, indent=2))
        except Exception as e:
            log.debug("Research state save error: %s", e)

    def _append_finding(self, finding: ResearchFinding) -> None:
        try:
            _FINDINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_FINDINGS_FILE, "a") as f:
                f.write(json.dumps(finding.to_dict()) + "\n")

            # Trim to max findings
            lines = _FINDINGS_FILE.read_text().splitlines()
            if len(lines) > _MAX_FINDINGS:
                _FINDINGS_FILE.write_text(
                    "\n".join(lines[-_MAX_FINDINGS:]) + "\n"
                )
        except Exception as e:
            log.debug("Finding append error: %s", e)

    def get_findings(self, limit: int = 20) -> List[dict]:
        try:
            if not _FINDINGS_FILE.exists():
                return []
            lines = _FINDINGS_FILE.read_text().strip().splitlines()
            findings = []
            for line in reversed(lines):
                try:
                    findings.append(json.loads(line))
                except Exception:
                    pass
                if len(findings) >= limit:
                    break
            return findings
        except Exception:
            return []

    # ── Topic selection ───────────────────────────────────────────────────────

    async def _pick_topic(self) -> str:
        """Pick the next research topic from seeds or history."""
        candidates: List[str] = []

        # 1. User-defined seed topics (round-robin)
        if self._state.seed_topics:
            idx = self._state.total_sessions % len(self._state.seed_topics)
            candidates.append(self._state.seed_topics[idx])

        # 2. Topics inferred from task history via LLM
        if self._state.auto_topics_from_history and self._memory_manager:
            try:
                recent = self._memory_manager.recent_tasks(limit=20)
                commands = [t.get("command", "") for t in recent if t.get("command")]
                if commands and self._llm_client and self._llm_client.is_available():
                    history_text = "\n".join(f"- {c[:80]}" for c in commands[:15])
                    system = (
                        "Based on recent user activity, suggest ONE specific research topic "
                        "that would be genuinely useful to explore further. "
                        "The topic should be concrete and researchable (e.g. 'Rust async patterns', "
                        "'Python type hint best practices 2026', 'Cloudflare Workers vs Vercel Edge'). "
                        "Respond with ONLY the topic — no explanation."
                    )
                    topic = await self._llm_client._call(
                        system, f"Recent activity:\n{history_text}", max_tokens=30
                    )
                    topic = topic.strip().strip('"').strip("'")
                    if topic:
                        candidates.insert(0, topic)
            except Exception as e:
                log.debug("Topic inference error: %s", e)

        if not candidates:
            # Fallback topics
            fallbacks = [
                "AI agent architecture patterns 2026",
                "Python performance optimization tips",
                "Open source tools for personal productivity",
                "Security best practices for local AI assistants",
            ]
            idx = self._state.total_sessions % len(fallbacks)
            candidates.append(fallbacks[idx])

        return candidates[0]

    # ── Research execution ────────────────────────────────────────────────────

    async def _run_session(self) -> Optional[ResearchFinding]:
        """Execute one research session."""
        topic = await self._pick_topic()
        log.info("AutonomousResearcher: researching '%s'", topic)

        self._state.last_topic = topic
        self._state.last_run_at = time.time()
        self._state.total_sessions += 1
        self._save_state()

        summary_parts = []

        if self._run_command_fn:
            try:
                cmd = f"research {topic} — write a 200 word summary with key findings"
                output = await self._run_command_fn(cmd)
                if isinstance(output, str) and output.strip():
                    summary_parts.append(output.strip()[:1000])
            except Exception as e:
                log.debug("Research command error: %s", e)

        if not summary_parts and self._llm_client and self._llm_client.is_available():
            try:
                system = (
                    "You are a research assistant. Provide a concise, informative "
                    "200-word summary on the given topic. Include key insights, "
                    "current trends, and practical takeaways."
                )
                result = await self._llm_client._call(
                    system, f"Research topic: {topic}", max_tokens=350
                )
                summary_parts.append(result.strip())
            except Exception as e:
                log.debug("LLM research error: %s", e)

        if not summary_parts:
            return None

        summary = "\n\n".join(summary_parts)

        # Save to knowledge base
        if self._memory_manager:
            try:
                self._memory_manager.store_knowledge(
                    f"[Auto-Research] {topic}\n\n{summary}",
                    source="autonomous_researcher",
                    tags=["research", "auto", topic.lower()[:30]],
                )
            except Exception as e:
                log.debug("Knowledge store error: %s", e)

        finding = ResearchFinding(
            finding_id=str(uuid.uuid4())[:8],
            topic=topic,
            summary=summary[:800],
            source="auto",
            tags=["auto-research"],
        )
        self._append_finding(finding)

        # Notify if callback registered
        if self._notify_fn:
            try:
                await self._notify_fn(topic, summary[:200])
            except Exception:
                pass

        log.info("AutonomousResearcher: completed '%s'", topic)
        return finding

    # ── Background loop ───────────────────────────────────────────────────────

    async def _loop(self) -> None:
        """Main background research loop."""
        log.info("AutonomousResearcher: loop started (interval=%d min)",
                 self._state.interval_minutes)
        while self._state.enabled:
            try:
                await self._run_session()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning("AutonomousResearcher session error: %s", e)

            # Wait for next interval
            interval_s = self._state.interval_minutes * 60
            try:
                await asyncio.sleep(interval_s)
            except asyncio.CancelledError:
                break

        log.info("AutonomousResearcher: loop stopped")

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self, interval_minutes: Optional[int] = None) -> dict:
        if interval_minutes:
            self._state.interval_minutes = max(5, interval_minutes)
        self._state.enabled = True
        self._save_state()

        if self._task is None or self._task.done():
            try:
                loop = asyncio.get_running_loop()
                self._task = loop.create_task(self._loop())
            except RuntimeError:
                pass

        return self.get_status()

    def stop(self) -> dict:
        self._state.enabled = False
        self._save_state()
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        return self.get_status()

    async def run_now(self) -> Optional[dict]:
        """Trigger an immediate research session."""
        finding = await self._run_session()
        return finding.to_dict() if finding else None

    def add_seed_topic(self, topic: str) -> None:
        if topic not in self._state.seed_topics:
            self._state.seed_topics.append(topic.strip())
            self._save_state()

    def remove_seed_topic(self, topic: str) -> None:
        self._state.seed_topics = [t for t in self._state.seed_topics if t != topic]
        self._save_state()

    def get_status(self) -> dict:
        next_run_in = 0
        if self._state.enabled and self._state.last_run_at > 0:
            elapsed = time.time() - self._state.last_run_at
            remaining = (self._state.interval_minutes * 60) - elapsed
            next_run_in = max(0, int(remaining))

        return {
            "enabled": self._state.enabled,
            "interval_minutes": self._state.interval_minutes,
            "seed_topics": self._state.seed_topics,
            "last_run_at": self._state.last_run_at,
            "last_topic": self._state.last_topic,
            "total_sessions": self._state.total_sessions,
            "auto_topics_from_history": self._state.auto_topics_from_history,
            "next_run_in_seconds": next_run_in,
            "is_running": self._task is not None and not (self._task.done() if self._task else True),
        }

    def update_settings(self, **kwargs: Any) -> dict:
        for k, v in kwargs.items():
            if hasattr(self._state, k):
                setattr(self._state, k, v)
        self._save_state()
        return self.get_status()


# ── Singleton ──────────────────────────────────────────────────────────────────

_researcher: Optional[AutonomousResearcher] = None


def get_autonomous_researcher() -> AutonomousResearcher:
    global _researcher
    if _researcher is None:
        _researcher = AutonomousResearcher()
    return _researcher
