"""ClawHub Marketplace — OpenClaw ClawHub + OpenFang FangHub inspired.

A curated registry of community Hands and Skills that users can browse,
install, and rate. Ships with 20+ built-in catalog entries across 7 categories.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

_STATE_FILE = Path.home() / ".arix" / "marketplace_state.json"


# ── Catalog entry types ────────────────────────────────────────────────────────

@dataclass
class MarketplaceItem:
    item_id: str
    name: str
    item_type: str          # "hand" | "skill"
    category: str
    author: str
    description: str
    icon: str
    stars: int
    installs: int
    version: str
    tags: List[str]
    featured: bool = False
    installed: bool = False
    rating: float = 0.0
    updated_at: str = ""
    tool_domains: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "name": self.name,
            "item_type": self.item_type,
            "category": self.category,
            "author": self.author,
            "description": self.description,
            "icon": self.icon,
            "stars": self.stars,
            "installs": self.installs,
            "version": self.version,
            "tags": self.tags,
            "featured": self.featured,
            "installed": self.installed,
            "rating": self.rating,
            "updated_at": self.updated_at,
            "tool_domains": self.tool_domains,
        }


# ── Built-in catalog ───────────────────────────────────────────────────────────

CATALOG: List[MarketplaceItem] = [

    # ── Featured / Editor's Picks ──────────────────────────────────────────────
    MarketplaceItem(
        item_id="hand-browser",
        name="Browser Hand",
        item_type="hand",
        category="Automation",
        author="arix-core",
        description="Full Playwright browser automation — click, fill forms, screenshot, extract data from any website. Handles SPAs, infinite scroll, and dynamic content.",
        icon="🌐",
        stars=2841,
        installs=18_420,
        version="2.1.0",
        tags=["browser", "automation", "playwright", "scraping"],
        featured=True,
        rating=4.8,
        updated_at="2026-06-01",
        tool_domains=["browser", "file", "research"],
    ),
    MarketplaceItem(
        item_id="hand-clip",
        name="Clip Hand",
        item_type="hand",
        category="Research",
        author="arix-core",
        description="Save, summarize, and tag content from any URL or text. Builds a personal knowledge library with full-text search. Inspired by OpenFang's Clip Hand.",
        icon="📎",
        stars=1_920,
        installs=12_700,
        version="1.4.0",
        tags=["clip", "bookmark", "research", "knowledge"],
        featured=True,
        rating=4.7,
        updated_at="2026-05-28",
        tool_domains=["browser", "file", "document", "research"],
    ),
    MarketplaceItem(
        item_id="hand-lead",
        name="Lead Hand",
        item_type="hand",
        category="Business",
        author="arix-core",
        description="Prospect research, lead enrichment, and outreach drafting. Researches companies and contacts, scores fit, and writes personalised first-touch emails.",
        icon="🎯",
        stars=1_340,
        installs=8_100,
        version="1.2.0",
        tags=["sales", "leads", "crm", "outreach"],
        featured=True,
        rating=4.5,
        updated_at="2026-05-15",
        tool_domains=["browser", "research", "file", "document"],
    ),

    # ── Productivity ───────────────────────────────────────────────────────────
    MarketplaceItem(
        item_id="skill-daily-brief",
        name="Daily Brief",
        item_type="skill",
        category="Productivity",
        author="community",
        description="Generates a personalised morning briefing: weather, calendar events, top news in your domains, pending tasks, and an AI-curated priority recommendation.",
        icon="☀️",
        stars=3_210,
        installs=24_500,
        version="3.0.1",
        tags=["brief", "morning", "news", "calendar", "productivity"],
        featured=True,
        rating=4.9,
        updated_at="2026-06-10",
        tool_domains=["calendar", "research", "file"],
    ),
    MarketplaceItem(
        item_id="skill-meeting-notes",
        name="Meeting Notes",
        item_type="skill",
        category="Productivity",
        author="community",
        description="Transcribes or summarises meeting content, extracts action items, assigns owners, and pushes formatted notes to your notes app or Google Drive.",
        icon="📝",
        stars=2_100,
        installs=16_800,
        version="2.2.0",
        tags=["meeting", "notes", "transcription", "action-items"],
        featured=False,
        rating=4.6,
        updated_at="2026-05-20",
        tool_domains=["document", "drive", "file"],
    ),
    MarketplaceItem(
        item_id="skill-email-triage",
        name="Email Triage",
        item_type="skill",
        category="Productivity",
        author="community",
        description="Scans your inbox, categorises emails by urgency and sender, drafts replies for routine messages, and flags anything requiring your attention.",
        icon="📬",
        stars=1_890,
        installs=14_200,
        version="1.5.0",
        tags=["email", "gmail", "triage", "productivity"],
        featured=False,
        rating=4.4,
        updated_at="2026-04-30",
        tool_domains=["gmail", "file"],
    ),
    MarketplaceItem(
        item_id="skill-focus-timer",
        name="Focus Timer",
        item_type="skill",
        category="Productivity",
        author="community",
        description="Pomodoro-style focus sessions with task tracking. Blocks distracting sites, logs focus time, and generates a weekly productivity report.",
        icon="⏱️",
        stars=980,
        installs=7_600,
        version="1.1.0",
        tags=["pomodoro", "focus", "timer", "productivity"],
        featured=False,
        rating=4.2,
        updated_at="2026-04-12",
        tool_domains=["system", "file"],
    ),

    # ── Development ────────────────────────────────────────────────────────────
    MarketplaceItem(
        item_id="skill-pr-reviewer",
        name="PR Reviewer",
        item_type="skill",
        category="Development",
        author="devtools-community",
        description="Reviews GitHub PRs: checks code style, spots bugs, suggests improvements, and writes a structured review comment. Supports Python, TypeScript, Go, Rust.",
        icon="🔍",
        stars=4_120,
        installs=31_000,
        version="2.0.0",
        tags=["github", "pr", "code-review", "git"],
        featured=True,
        rating=4.9,
        updated_at="2026-06-08",
        tool_domains=["coding", "git", "file", "browser"],
    ),
    MarketplaceItem(
        item_id="skill-debug-tracer",
        name="Debug Tracer",
        item_type="skill",
        category="Development",
        author="devtools-community",
        description="Analyzes stack traces and error logs, traces the call chain to the root cause, and proposes a fix with test cases.",
        icon="🐛",
        stars=2_780,
        installs=20_400,
        version="1.8.0",
        tags=["debug", "errors", "logs", "tracing"],
        featured=False,
        rating=4.7,
        updated_at="2026-05-25",
        tool_domains=["coding", "file"],
    ),
    MarketplaceItem(
        item_id="skill-docgen",
        name="DocGen",
        item_type="skill",
        category="Development",
        author="devtools-community",
        description="Reads your codebase and generates comprehensive documentation: API docs, README, architecture diagrams, and inline docstrings.",
        icon="📚",
        stars=1_560,
        installs=11_800,
        version="1.3.0",
        tags=["docs", "readme", "api", "docstrings"],
        featured=False,
        rating=4.5,
        updated_at="2026-05-01",
        tool_domains=["coding", "file", "document"],
    ),
    MarketplaceItem(
        item_id="skill-test-writer",
        name="Test Writer",
        item_type="skill",
        category="Development",
        author="devtools-community",
        description="Generates unit and integration tests for your code. Detects edge cases, mocks dependencies, and targets 80%+ line coverage.",
        icon="✅",
        stars=1_240,
        installs=9_300,
        version="1.0.0",
        tags=["tests", "testing", "pytest", "jest"],
        featured=False,
        rating=4.3,
        updated_at="2026-04-18",
        tool_domains=["coding", "file"],
    ),

    # ── Research ───────────────────────────────────────────────────────────────
    MarketplaceItem(
        item_id="skill-market-research",
        name="Market Research",
        item_type="skill",
        category="Research",
        author="research-community",
        description="Deep-dive market research reports: TAM/SAM/SOM analysis, competitor mapping, customer segments, and trend forecasting. Outputs structured markdown.",
        icon="📊",
        stars=2_340,
        installs=17_100,
        version="2.1.0",
        tags=["market", "research", "competitors", "strategy"],
        featured=True,
        rating=4.8,
        updated_at="2026-06-05",
        tool_domains=["browser", "research", "document", "file"],
    ),
    MarketplaceItem(
        item_id="skill-arxiv-digest",
        name="ArXiv Digest",
        item_type="skill",
        category="Research",
        author="research-community",
        description="Fetches the latest papers from ArXiv in your domains, summarises abstracts, ranks by relevance, and delivers a weekly digest to your notes.",
        icon="🔬",
        stars=1_080,
        installs=6_900,
        version="1.2.0",
        tags=["arxiv", "papers", "research", "ai"],
        featured=False,
        rating=4.6,
        updated_at="2026-05-14",
        tool_domains=["browser", "research", "file"],
    ),
    MarketplaceItem(
        item_id="skill-fact-checker",
        name="Fact Checker",
        item_type="skill",
        category="Research",
        author="research-community",
        description="Cross-references claims against multiple sources, rates confidence, and flags unsupported assertions. Outputs a structured verification report.",
        icon="✔️",
        stars=870,
        installs=5_400,
        version="1.0.0",
        tags=["fact-check", "verification", "research"],
        featured=False,
        rating=4.4,
        updated_at="2026-04-22",
        tool_domains=["browser", "research", "file"],
    ),

    # ── Writing ────────────────────────────────────────────────────────────────
    MarketplaceItem(
        item_id="skill-linkedin-post",
        name="LinkedIn Post Writer",
        item_type="skill",
        category="Writing",
        author="content-community",
        description="Writes engaging LinkedIn posts from a topic, article, or bullet points. Optimises for reach with hooks, storytelling, and platform-native formatting.",
        icon="💼",
        stars=3_800,
        installs=28_700,
        version="2.4.0",
        tags=["linkedin", "social", "writing", "content"],
        featured=True,
        rating=4.9,
        updated_at="2026-06-12",
        tool_domains=["file", "browser"],
    ),
    MarketplaceItem(
        item_id="skill-newsletter",
        name="Newsletter Builder",
        item_type="skill",
        category="Writing",
        author="content-community",
        description="Curates content, writes headlines, and assembles a polished newsletter from your topic list. Outputs HTML and plain-text versions.",
        icon="📧",
        stars=1_460,
        installs=10_200,
        version="1.3.0",
        tags=["newsletter", "email", "content", "writing"],
        featured=False,
        rating=4.5,
        updated_at="2026-05-08",
        tool_domains=["browser", "research", "file", "document"],
    ),

    # ── Finance ────────────────────────────────────────────────────────────────
    MarketplaceItem(
        item_id="skill-stock-analysis",
        name="Stock Analyser",
        item_type="skill",
        category="Finance",
        author="finance-community",
        description="Pulls public financial data, computes key ratios, reads recent earnings call sentiment, and generates a structured buy/hold/sell analysis.",
        icon="📈",
        stars=2_960,
        installs=21_300,
        version="1.6.0",
        tags=["stocks", "finance", "investing", "analysis"],
        featured=True,
        rating=4.7,
        updated_at="2026-06-03",
        tool_domains=["browser", "research", "file", "document"],
    ),
    MarketplaceItem(
        item_id="skill-expense-tracker",
        name="Expense Tracker",
        item_type="skill",
        category="Finance",
        author="finance-community",
        description="Parses receipts or transaction exports, categorises spend, detects anomalies, and generates a monthly budget summary with savings recommendations.",
        icon="💰",
        stars=1_180,
        installs=8_800,
        version="1.1.0",
        tags=["expense", "budget", "finance", "receipts"],
        featured=False,
        rating=4.3,
        updated_at="2026-04-28",
        tool_domains=["file", "document"],
    ),

    # ── Personal ───────────────────────────────────────────────────────────────
    MarketplaceItem(
        item_id="skill-habit-tracker",
        name="Habit Tracker",
        item_type="skill",
        category="Personal",
        author="wellness-community",
        description="Logs daily habits via natural language, tracks streaks, generates weekly progress charts, and sends gentle accountability check-ins.",
        icon="🌱",
        stars=1_620,
        installs=12_100,
        version="1.2.0",
        tags=["habits", "personal", "wellness", "tracking"],
        featured=False,
        rating=4.5,
        updated_at="2026-05-18",
        tool_domains=["file", "calendar"],
    ),
    MarketplaceItem(
        item_id="skill-travel-planner",
        name="Travel Planner",
        item_type="skill",
        category="Personal",
        author="wellness-community",
        description="Plans complete trips: researches destinations, books-of-note, itinerary day-by-day, packing list, and budget estimate — saved as a shareable markdown doc.",
        icon="✈️",
        stars=2_080,
        installs=15_600,
        version="1.5.0",
        tags=["travel", "planning", "itinerary", "personal"],
        featured=False,
        rating=4.6,
        updated_at="2026-05-22",
        tool_domains=["browser", "research", "document", "file"],
    ),
]

_CATEGORIES = sorted({item.category for item in CATALOG})
_ITEM_MAP: Dict[str, MarketplaceItem] = {item.item_id: item for item in CATALOG}


# ── Marketplace manager ────────────────────────────────────────────────────────

class MarketplaceHub:
    """ClawHub/FangHub-inspired marketplace for community Hands and Skills."""

    def __init__(self) -> None:
        self._installed: Dict[str, dict] = {}   # item_id → install metadata
        self._ratings: Dict[str, float] = {}    # item_id → user rating
        self._load_state()

    def _load_state(self) -> None:
        try:
            if _STATE_FILE.exists():
                data = json.loads(_STATE_FILE.read_text())
                self._installed = data.get("installed", {})
                self._ratings = data.get("ratings", {})
                for item_id in self._installed:
                    if item_id in _ITEM_MAP:
                        _ITEM_MAP[item_id].installed = True
        except Exception as e:
            log.debug("Marketplace state load error: %s", e)

    def _save_state(self) -> None:
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _STATE_FILE.write_text(json.dumps(
                {"installed": self._installed, "ratings": self._ratings}, indent=2
            ))
        except Exception as e:
            log.debug("Marketplace state save error: %s", e)

    def browse(
        self,
        query: str = "",
        category: str = "",
        item_type: str = "",
        sort: str = "stars",      # "stars" | "installs" | "rating" | "updated"
        featured_only: bool = False,
        limit: int = 50,
    ) -> dict:
        items = list(CATALOG)

        if query:
            q = query.lower()
            items = [
                i for i in items
                if q in i.name.lower()
                or q in i.description.lower()
                or any(q in t for t in i.tags)
            ]
        if category:
            items = [i for i in items if i.category.lower() == category.lower()]
        if item_type:
            items = [i for i in items if i.item_type == item_type]
        if featured_only:
            items = [i for i in items if i.featured]

        sort_keys = {
            "stars": lambda x: -x.stars,
            "installs": lambda x: -x.installs,
            "rating": lambda x: -x.rating,
            "updated": lambda x: x.updated_at,
        }
        items.sort(key=sort_keys.get(sort, sort_keys["stars"]))

        return {
            "items": [self._enrich(i).to_dict() for i in items[:limit]],
            "total": len(items),
            "categories": _CATEGORIES,
            "featured": [self._enrich(i).to_dict() for i in CATALOG if i.featured],
        }

    def _enrich(self, item: MarketplaceItem) -> MarketplaceItem:
        if item.item_id in self._ratings:
            item.rating = self._ratings[item.item_id]
        item.installed = item.item_id in self._installed
        return item

    def install(self, item_id: str) -> dict:
        item = _ITEM_MAP.get(item_id)
        if not item:
            return {"ok": False, "error": f"Item '{item_id}' not found"}
        self._installed[item_id] = {
            "installed_at": time.time(),
            "version": item.version,
        }
        item.installed = True
        item.installs += 1
        self._save_state()
        log.info("Marketplace: installed '%s' (%s)", item.name, item_id)
        return {"ok": True, "item": item.to_dict()}

    def uninstall(self, item_id: str) -> dict:
        if item_id not in self._installed:
            return {"ok": False, "error": "Not installed"}
        del self._installed[item_id]
        if item_id in _ITEM_MAP:
            _ITEM_MAP[item_id].installed = False
        self._save_state()
        return {"ok": True}

    def rate(self, item_id: str, rating: float) -> dict:
        if item_id not in _ITEM_MAP:
            return {"ok": False, "error": "Item not found"}
        rating = max(1.0, min(5.0, rating))
        self._ratings[item_id] = rating
        self._save_state()
        return {"ok": True, "rating": rating}

    def get_installed(self) -> list:
        result = []
        for item_id, meta in self._installed.items():
            if item_id in _ITEM_MAP:
                item = self._enrich(_ITEM_MAP[item_id])
                d = item.to_dict()
                d["installed_at"] = meta.get("installed_at", 0)
                result.append(d)
        result.sort(key=lambda x: -x.get("installed_at", 0))
        return result

    def stats(self) -> dict:
        total_installs = sum(len(self._installed) > 0 for _ in [1])
        return {
            "total_catalog": len(CATALOG),
            "installed_count": len(self._installed),
            "categories": _CATEGORIES,
            "hands_count": sum(1 for i in CATALOG if i.item_type == "hand"),
            "skills_count": sum(1 for i in CATALOG if i.item_type == "skill"),
            "featured_count": sum(1 for i in CATALOG if i.featured),
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

_hub: Optional[MarketplaceHub] = None


def get_marketplace_hub() -> MarketplaceHub:
    global _hub
    if _hub is None:
        _hub = MarketplaceHub()
    return _hub
