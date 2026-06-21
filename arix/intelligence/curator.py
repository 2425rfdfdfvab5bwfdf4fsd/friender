"""Hermes-inspired Curator — autonomous 4-stage skill self-improvement loop.

Every N completed goals the Curator:
  1. Pattern Extraction — mines task history for recurring sequences
  2. Skill Creation    — packages patterns into reusable workflow skills
  3. Skill Refinement  — scores existing skills; improves underperforming ones
  4. Pruning           — removes stale/low-value skills; promotes best to "core"

Core skills are injected into the GoalSupervisor's planning context automatically.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_CURATOR_FILE = Path.home() / ".arix" / "curator_state.json"
_CURATOR_INTERVAL = 15          # trigger after every N completed goals
_CORE_PROMOTE_THRESHOLD = 3.5   # skill score ≥ this → promoted to "core"
_PRUNE_THRESHOLD = 1.0          # skill score ≤ this → pruned
_MAX_SKILLS = 50


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class CuratedSkill:
    id: str
    name: str
    description: str
    pattern: str                   # the recurring trigger phrase
    steps: List[str]               # sub-commands to execute
    category: str
    source: str                    # "auto" | "user" | "promoted"
    uses: int = 0
    successes: int = 0
    failures: int = 0
    score: float = 2.0             # weighted success rate (0–5)
    is_core: bool = False          # injected into every planning context
    created_at: float = field(default_factory=time.time)
    last_used: float = 0.0
    refined_at: float = 0.0

    def update_score(self) -> None:
        if self.uses == 0:
            return
        raw = self.successes / self.uses
        recency = min(1.0, (time.time() - self.last_used) / 86400)  # days since use
        recency_penalty = recency * 0.5
        self.score = round((raw * 5.0) - recency_penalty, 2)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "pattern": self.pattern,
            "steps": self.steps,
            "category": self.category,
            "source": self.source,
            "uses": self.uses,
            "successes": self.successes,
            "failures": self.failures,
            "score": self.score,
            "is_core": self.is_core,
            "created_at": self.created_at,
            "last_used": self.last_used,
            "refined_at": self.refined_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CuratedSkill":
        return cls(
            id=d.get("id", str(uuid.uuid4())[:8]),
            name=d["name"],
            description=d.get("description", ""),
            pattern=d.get("pattern", ""),
            steps=d.get("steps", []),
            category=d.get("category", "General"),
            source=d.get("source", "auto"),
            uses=d.get("uses", 0),
            successes=d.get("successes", 0),
            failures=d.get("failures", 0),
            score=d.get("score", 2.0),
            is_core=d.get("is_core", False),
            created_at=d.get("created_at", time.time()),
            last_used=d.get("last_used", 0.0),
            refined_at=d.get("refined_at", 0.0),
        )


@dataclass
class CuratorState:
    goals_since_last_run: int = 0
    total_goals_processed: int = 0
    last_run_at: float = 0.0
    last_run_summary: str = ""
    skills: List[CuratedSkill] = field(default_factory=list)
    run_count: int = 0

    def to_dict(self) -> dict:
        return {
            "goals_since_last_run": self.goals_since_last_run,
            "total_goals_processed": self.total_goals_processed,
            "last_run_at": self.last_run_at,
            "last_run_summary": self.last_run_summary,
            "skills": [s.to_dict() for s in self.skills],
            "run_count": self.run_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CuratorState":
        state = cls(
            goals_since_last_run=d.get("goals_since_last_run", 0),
            total_goals_processed=d.get("total_goals_processed", 0),
            last_run_at=d.get("last_run_at", 0.0),
            last_run_summary=d.get("last_run_summary", ""),
            run_count=d.get("run_count", 0),
        )
        state.skills = [CuratedSkill.from_dict(s) for s in d.get("skills", [])]
        return state


# ── LLM prompts ───────────────────────────────────────────────────────────────

_PATTERN_SYSTEM = """You are Arix's Skill Pattern Extractor. Analyze a list of completed goals and identify 1-3 recurring patterns that could be packaged as reusable workflow skills.

For each pattern output a JSON object:
{
  "name": "Short Skill Name",
  "description": "One-sentence description",
  "pattern": "trigger phrase that would activate this skill",
  "category": "one of: Productivity, Research, Code, System, Communication, Creative, DevOps",
  "steps": ["step 1 command", "step 2 command", "step 3 command"]
}

Return a JSON array of 1-3 such objects. Return [] if no clear patterns exist.
Rules:
- Steps must be natural-language commands Arix can execute
- Pattern must be a short phrase (2-5 words) that captures the intent
- Minimum 2 steps, maximum 6 steps per skill
- Only extract patterns that appear in at least 2 different goals"""

_REFINE_SYSTEM = """You are Arix's Skill Refiner. You have a skill that is underperforming (low success rate or low usage). Improve it by rewriting its steps to be more reliable and effective.

Return ONLY a JSON object with updated fields:
{
  "name": "...",
  "description": "...",
  "steps": ["improved step 1", "improved step 2", ...]
}

Rules:
- Steps must be natural-language commands Arix can execute
- Make steps more specific and less likely to fail
- Add prerequisite steps if needed (e.g., check if file exists before reading)
- Keep 2-6 steps"""


# ── Curator ───────────────────────────────────────────────────────────────────

class SkillCurator:
    """Autonomous 4-stage skill improvement engine inspired by Hermes Agent."""

    def __init__(self, interval: int = _CURATOR_INTERVAL) -> None:
        self.interval = interval
        self._state: Optional[CuratorState] = None
        self._llm_client: Any = None
        self._task_history: Any = None   # TaskHistory reference

    def set_llm_client(self, client: Any) -> None:
        self._llm_client = client

    def set_task_history(self, history: Any) -> None:
        self._task_history = history

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self) -> CuratorState:
        if self._state is not None:
            return self._state
        try:
            if _CURATOR_FILE.exists():
                data = json.loads(_CURATOR_FILE.read_text(encoding="utf-8"))
                self._state = CuratorState.from_dict(data)
                return self._state
        except Exception as e:
            log.warning("Curator load error: %s", e)
        self._state = CuratorState()
        return self._state

    def _save(self) -> None:
        if self._state is None:
            return
        try:
            _CURATOR_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = _CURATOR_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._state.to_dict(), indent=2), encoding="utf-8")
            tmp.replace(_CURATOR_FILE)
        except Exception as e:
            log.warning("Curator save error: %s", e)

    # ── Public API ────────────────────────────────────────────────────────────

    def on_goal_completed(self, goal: str, steps_completed: int, success: bool) -> bool:
        """Call after each goal completes. Returns True if Curator loop should fire."""
        state = self._load()
        state.total_goals_processed += 1

        if success:
            state.goals_since_last_run += 1
            self._update_skill_usage(goal, success=True)
        else:
            self._update_skill_usage(goal, success=False)

        self._save()
        return state.goals_since_last_run >= self.interval

    def _update_skill_usage(self, goal: str, success: bool) -> None:
        state = self._state
        if state is None:
            return
        goal_lower = goal.lower()
        for skill in state.skills:
            if skill.pattern and skill.pattern.lower() in goal_lower:
                skill.uses += 1
                if success:
                    skill.successes += 1
                else:
                    skill.failures += 1
                skill.last_used = time.time()
                skill.update_score()

    async def run_loop(self) -> dict:
        """Execute the full 4-stage Curator loop."""
        state = self._load()
        state.goals_since_last_run = 0
        state.run_count += 1
        t0 = time.time()

        results = {
            "run_id": str(uuid.uuid4())[:8],
            "run_number": state.run_count,
            "stage_1_patterns": [],
            "stage_2_created": [],
            "stage_3_refined": [],
            "stage_4_pruned": [],
            "stage_4_promoted": [],
            "core_skills": [],
            "total_skills": 0,
            "duration_s": 0.0,
        }

        recent_goals = self._get_recent_goals(30)

        # ── Stage 1: Pattern Extraction ───────────────────────────────────
        patterns = await self._extract_patterns(recent_goals)
        results["stage_1_patterns"] = [p.get("name", "") for p in patterns]

        # ── Stage 2: Skill Creation ───────────────────────────────────────
        created = self._create_skills(patterns)
        results["stage_2_created"] = [s.name for s in created]

        # ── Stage 3: Skill Refinement ─────────────────────────────────────
        refined = await self._refine_skills()
        results["stage_3_refined"] = [s.name for s in refined]

        # ── Stage 4: Prune + Promote ──────────────────────────────────────
        pruned, promoted = self._prune_and_promote()
        results["stage_4_pruned"] = pruned
        results["stage_4_promoted"] = promoted

        # Enforce max skill limit
        if state is not None and len(state.skills) > _MAX_SKILLS:
            state.skills.sort(key=lambda s: s.score, reverse=True)
            state.skills = state.skills[:_MAX_SKILLS]

        if state is not None:
            results["core_skills"] = [s.name for s in state.skills if s.is_core]
            results["total_skills"] = len(state.skills)
        results["duration_s"] = round(time.time() - t0, 2)

        if state is not None:
            state.last_run_at = time.time()
            state.last_run_summary = (
                f"Created {len(created)}, refined {len(refined)}, "
                f"pruned {len(pruned)}, promoted {len(promoted)}"
            )

        self._save()
        log.info("Curator loop complete: %s", state.last_run_summary if state else "no state")
        return results

    def _get_recent_goals(self, limit: int) -> List[str]:
        if self._task_history is None:
            return []
        try:
            history = self._task_history.get_recent(limit)
            goals = []
            for entry in history:
                cmd = entry.get("command", "") or entry.get("goal", "")
                if cmd:
                    goals.append(cmd[:200])
            return goals
        except Exception:
            return []

    async def _extract_patterns(self, goals: List[str]) -> List[dict]:
        if not goals:
            return []
        if self._llm_client is None or not self._llm_client.is_available():
            return self._heuristic_patterns(goals)

        goal_text = "\n".join(f"- {g}" for g in goals[:25])
        try:
            raw = await self._llm_client._call(
                _PATTERN_SYSTEM,
                f"Recent completed goals:\n{goal_text}",
                max_tokens=800,
            )
            raw = raw.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(lines[1:])
                if "```" in raw:
                    raw = raw[:raw.rfind("```")].strip()
            patterns = json.loads(raw)
            if isinstance(patterns, list):
                return patterns[:3]
        except Exception as e:
            log.debug("Pattern extraction LLM error: %s", e)

        return self._heuristic_patterns(goals)

    def _heuristic_patterns(self, goals: List[str]) -> List[dict]:
        from collections import Counter
        prefixes = Counter()
        for g in goals:
            words = g.lower().split()[:3]
            if len(words) >= 2:
                prefixes[" ".join(words[:2])] += 1

        patterns = []
        for prefix, count in prefixes.most_common(3):
            if count >= 2:
                patterns.append({
                    "name": prefix.title(),
                    "description": f"Auto-detected pattern: {prefix}",
                    "pattern": prefix,
                    "category": "Productivity",
                    "steps": [g for g in goals if g.lower().startswith(prefix)][:3],
                })
        return patterns

    def _create_skills(self, patterns: List[dict]) -> List[CuratedSkill]:
        state = self._state
        if state is None:
            return []
        created = []
        existing_names = {s.name.lower() for s in state.skills}

        for p in patterns:
            name = p.get("name", "").strip()
            steps = p.get("steps", [])
            if not name or not steps or name.lower() in existing_names:
                continue

            skill = CuratedSkill(
                id=str(uuid.uuid4())[:8],
                name=name,
                description=p.get("description", ""),
                pattern=p.get("pattern", ""),
                steps=steps[:6],
                category=p.get("category", "General"),
                source="auto",
            )
            state.skills.append(skill)
            existing_names.add(name.lower())
            created.append(skill)

        return created

    async def _refine_skills(self) -> List[CuratedSkill]:
        if self._llm_client is None or not self._llm_client.is_available():
            return []

        state = self._state
        if state is None:
            return []
        underperforming = [
            s for s in state.skills
            if s.uses >= 3 and s.score < 2.5 and not s.is_core
        ]
        refined = []

        for skill in underperforming[:2]:  # refine at most 2 per cycle
            context = (
                f"Skill: {skill.name}\n"
                f"Description: {skill.description}\n"
                f"Current steps:\n" + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(skill.steps)) +
                f"\nPerformance: {skill.successes}/{skill.uses} success rate\n"
                f"Last failure may be due to overly-specific paths or missing prerequisites."
            )
            try:
                raw = await self._llm_client._call(_REFINE_SYSTEM, context, max_tokens=400)
                raw = raw.strip()
                if raw.startswith("```"):
                    lines = raw.split("\n")
                    raw = "\n".join(lines[1:])
                    if "```" in raw:
                        raw = raw[:raw.rfind("```")].strip()
                updated = json.loads(raw)
                if "steps" in updated and isinstance(updated["steps"], list):
                    skill.steps = updated["steps"][:6]
                    if "name" in updated:
                        skill.name = updated["name"]
                    if "description" in updated:
                        skill.description = updated["description"]
                    skill.refined_at = time.time()
                    refined.append(skill)
            except Exception as e:
                log.debug("Skill refine error for %s: %s", skill.name, e)

        return refined

    def _prune_and_promote(self) -> Tuple[List[str], List[str]]:
        state = self._state
        if state is None:
            return [], []
        pruned_names = []
        promoted_names = []

        to_keep = []
        for skill in state.skills:
            skill.update_score()
            if skill.uses >= 5 and skill.score <= _PRUNE_THRESHOLD:
                pruned_names.append(skill.name)
                continue
            if skill.uses >= 3 and skill.score >= _CORE_PROMOTE_THRESHOLD and not skill.is_core:
                skill.is_core = True
                promoted_names.append(skill.name)
            elif skill.uses < 2 and skill.is_core:
                skill.is_core = False
            to_keep.append(skill)

        state.skills = to_keep
        return pruned_names, promoted_names

    # ── Query API ─────────────────────────────────────────────────────────────

    def get_core_skills(self) -> List[CuratedSkill]:
        state = self._load()
        return [s for s in state.skills if s.is_core]

    def get_core_context(self) -> str:
        """Build a context string of core skills to inject into planning prompts."""
        core = self.get_core_skills()
        if not core:
            return ""
        lines = ["\n\nCORE SKILLS (high-value learned patterns — prefer these when relevant):"]
        for skill in core[:5]:
            lines.append(f"- {skill.name}: {skill.description}")
            for i, step in enumerate(skill.steps[:4], 1):
                lines.append(f"    {i}. {step}")
        return "\n".join(lines)

    def get_status(self) -> dict:
        state = self._load()
        return {
            "goals_since_last_run": state.goals_since_last_run,
            "goals_until_next_run": max(0, self.interval - state.goals_since_last_run),
            "total_goals_processed": state.total_goals_processed,
            "last_run_at": state.last_run_at,
            "last_run_summary": state.last_run_summary,
            "run_count": state.run_count,
            "total_skills": len(state.skills),
            "core_skills": len([s for s in state.skills if s.is_core]),
            "auto_skills": len([s for s in state.skills if s.source == "auto"]),
            "interval": self.interval,
        }

    def get_all_skills(self) -> List[dict]:
        state = self._load()
        skills = sorted(state.skills, key=lambda s: s.score, reverse=True)
        return [s.to_dict() for s in skills]

    def delete_skill(self, skill_id: str) -> bool:
        state = self._load()
        before = len(state.skills)
        state.skills = [s for s in state.skills if s.id != skill_id]
        changed = len(state.skills) < before
        if changed:
            self._save()
        return changed

    def toggle_core(self, skill_id: str) -> Optional[dict]:
        state = self._load()
        for skill in state.skills:
            if skill.id == skill_id:
                skill.is_core = not skill.is_core
                self._save()
                return skill.to_dict()
        return None


# ── Singleton ─────────────────────────────────────────────────────────────────

_curator: Optional[SkillCurator] = None


def get_curator() -> SkillCurator:
    global _curator
    if _curator is None:
        _curator = SkillCurator()
    return _curator
