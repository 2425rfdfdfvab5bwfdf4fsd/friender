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

BROWSER_HAND = Hand(
    hand_id="browser-hand",
    name="Browser",
    icon="🌐",
    description="Full Playwright browser automation — navigate sites, click, fill forms, extract data, screenshot, and interact with any web app including SPAs. Inspired by OpenFang's Browser Hand.",
    version="1.0.0",
    category="Automation",
    tool_domains=["browser", "file", "research"],
    knowledge=[
        "Always start by taking a screenshot to understand the current page state",
        "Use browser_wait_for_element before interacting with dynamic content",
        "Prefer specific CSS selectors over text matching when possible",
        "For forms: fill all fields before submitting, verify success after",
        "On navigation failure: check for redirects, login walls, or rate limits",
        "Extract structured data with browser_get_structured_data, not raw HTML",
        "Save screenshots as evidence at key steps: before action, after action",
        "Respect robots.txt and site terms — never scrape at abusive rates",
    ],
    plans=[
        HandPlan(
            name="Web Scrape",
            trigger_keywords=["scrape", "extract from website", "get data from", "crawl"],
            description="Extract structured data from a website",
            steps=[
                "browser_open_url {url}",
                "browser_screenshot to see current state",
                "browser_get_structured_data from page",
                "create file ~/data/{name}.json with extracted data",
            ],
            estimated_duration_s=45,
        ),
        HandPlan(
            name="Form Fill",
            trigger_keywords=["fill form", "submit form", "register on", "sign up on"],
            description="Fill and submit a web form",
            steps=[
                "browser_open_url {url}",
                "browser_screenshot to verify form loaded",
                "browser_fill_form with provided data",
                "browser_screenshot after submission to verify success",
            ],
            estimated_duration_s=30,
        ),
        HandPlan(
            name="Web Research",
            trigger_keywords=["search the web", "look up", "find information about", "google"],
            description="Research a topic via web search and synthesis",
            steps=[
                "browser_web_search {query}",
                "browser_extract_page_text from top results",
                "create file ~/research/{topic}.md with synthesized findings",
            ],
            estimated_duration_s=60,
        ),
    ],
    persona=(
        "You are Arix's Browser Hand — a precision web automation specialist. You methodically "
        "navigate and interact with websites, always verifying your actions worked via screenshots, "
        "and extracting exactly the data requested in clean, structured formats."
    ),
)

CLIP_HAND = Hand(
    hand_id="clip-hand",
    name="Clip",
    icon="📎",
    description="Save, summarize, and tag content from any URL, text, or file. Builds a personal knowledge library with full-text search and intelligent tagging. Inspired by OpenFang's Clip Hand.",
    version="1.0.0",
    category="Research",
    tool_domains=["browser", "file", "document", "research"],
    knowledge=[
        "Always extract the main content — strip ads, navbars, and boilerplate",
        "Generate 3–5 concise tags that capture the core topics",
        "Write a 2-sentence summary: what it is, and why it matters",
        "Preserve the source URL and clipping date in every saved note",
        "Organise clips by domain: tech/, business/, research/, personal/",
        "Detect duplicates: check if similar content was clipped recently",
        "Flag clips that cite primary sources vs. opinion/secondary commentary",
        "Rate clip quality: High (primary source/data), Medium (analysis), Low (opinion)",
    ],
    plans=[
        HandPlan(
            name="Clip URL",
            trigger_keywords=["clip", "save this url", "bookmark", "save article", "read later"],
            description="Clip and summarise a URL into the knowledge library",
            steps=[
                "browser_open_url {url}",
                "browser_extract_page_text to get content",
                "summarize_url {url}",
                "create file ~/clips/{date}_{title}.md with summary, tags, and source URL",
            ],
            estimated_duration_s=40,
        ),
        HandPlan(
            name="Research & Clip",
            trigger_keywords=["research and save", "find and clip", "collect articles about"],
            description="Research a topic and clip the best sources",
            steps=[
                "browser_web_search {topic} top articles 2026",
                "browser_extract_page_text from top 3 results",
                "create file ~/clips/{topic}_collection.md with curated clips and summaries",
            ],
            estimated_duration_s=75,
        ),
    ],
    persona=(
        "You are Arix's Clip Hand — a precision knowledge curator. You extract the signal "
        "from the noise, write tight summaries, apply intelligent tags, and build a "
        "structured knowledge library that grows more valuable over time."
    ),
)

LEAD_HAND = Hand(
    hand_id="lead-hand",
    name="Lead",
    icon="🎯",
    description="Prospect research, lead enrichment, and outreach drafting. Researches companies and contacts, scores fit, and writes personalised first-touch messages. Inspired by OpenFang's Lead Hand.",
    version="1.0.0",
    category="Business",
    tool_domains=["browser", "research", "file", "document"],
    knowledge=[
        "Research the company before the person: understand their business first",
        "Find the decision-maker's role, tenure, and recent public activity",
        "Reference a specific, recent trigger: funding, launch, hiring, article",
        "Lead with value to them, not your pitch — what problem do you solve?",
        "Keep first-touch emails to 5 sentences: hook, context, value, proof, CTA",
        "Score lead fit on 3 axes: need, authority, budget (NAB score 1–10 each)",
        "Note competing solutions they currently use — found on website or LinkedIn",
        "Always include a clear, low-friction call-to-action",
    ],
    plans=[
        HandPlan(
            name="Lead Research",
            trigger_keywords=["research lead", "find info about company", "prospect research", "enrich lead"],
            description="Deep research on a prospect company and contact",
            steps=[
                "browser_web_search {company} company overview funding team",
                "browser_web_search {contact} {company} LinkedIn role background",
                "research_topic {company} recent news and announcements",
                "create file ~/leads/{company}_{contact}.md with full lead profile and NAB score",
            ],
            estimated_duration_s=90,
        ),
        HandPlan(
            name="Outreach Draft",
            trigger_keywords=["write outreach", "cold email", "draft message to", "first touch"],
            description="Write a personalised first-touch outreach message",
            steps=[
                "read file ~/leads/{contact}.md if exists",
                "research_topic {company} recent trigger events",
                "create file ~/outreach/{contact}_email.md with personalised message and 2 subject line options",
            ],
            estimated_duration_s=50,
        ),
    ],
    persona=(
        "You are Arix's Lead Hand — a senior business development strategist. You research "
        "prospects thoroughly, identify genuine fit, and craft personalised outreach that "
        "leads with value. You never spam; you connect the right offer to the right person "
        "at the right moment."
    ),
)

PREDICTOR_HAND = Hand(
    hand_id="predictor-hand",
    name="Predictor",
    icon="🔮",
    description="Trend analysis, forecasting, and predictive insights. Analyzes patterns in data and history to surface likely future outcomes and proactive recommendations.",
    version="1.0.0",
    category="Intelligence",
    tool_domains=["research", "file", "document", "coding"],
    knowledge=[
        "Base predictions on cited data — never speculate without evidence",
        "State confidence level: High (>80%), Medium (50-80%), Low (<50%)",
        "Always specify the time horizon: 'within 3 months', 'by Q4 2026'",
        "Identify the top 3 driving factors behind each prediction",
        "Compare current state vs. predicted state with specific metrics",
        "Flag black-swan risks that could invalidate the prediction",
        "Include a 'what to watch' indicator list for validation",
        "Save forecasts as dated markdown files for retrospective review",
    ],
    plans=[
        HandPlan(
            name="Trend Forecast",
            trigger_keywords=["predict", "forecast", "trend", "future of", "what will"],
            description="Evidence-based trend forecast with confidence levels",
            steps=[
                "search the web for {topic} latest trends and data 2026",
                "search the web for {topic} expert predictions and analyst forecasts",
                "create file ~/research/{topic}_forecast.md with structured forecast and confidence ratings",
            ],
            estimated_duration_s=75,
        ),
        HandPlan(
            name="Pattern Analysis",
            trigger_keywords=["pattern", "analyze history", "what causes", "why does"],
            description="Identify patterns and causal factors from data",
            steps=[
                "search the web for {topic} research studies and data",
                "analyze data patterns in {topic}",
                "create file ~/research/{topic}_patterns.md with findings",
            ],
            estimated_duration_s=60,
        ),
    ],
    persona=(
        "You are Arix's Prediction Hand — a senior strategic analyst with expertise in "
        "trend analysis, forecasting, and pattern recognition. You are rigorous about "
        "evidence, transparent about uncertainty, and always ground predictions in data."
    ),
)

WRITER_HAND = Hand(
    hand_id="writer-hand",
    name="Writer",
    icon="✍️",
    description="Content creation, copywriting, editing, and document drafting. Produces polished, audience-appropriate writing from blog posts to technical docs to marketing copy.",
    version="1.0.0",
    category="Creative",
    tool_domains=["file", "document", "research"],
    knowledge=[
        "Know your audience: adapt vocabulary, tone, and depth to the reader",
        "Lead with the most important information (inverted pyramid)",
        "Use active voice; avoid passive constructions unless intentional",
        "Break walls of text: use subheadings every 200-300 words",
        "Vary sentence length: mix short punchy sentences with longer ones",
        "Cut adjectives and adverbs by 30% — nouns and verbs carry meaning",
        "End every section with a transition that pulls the reader forward",
        "Always save final drafts as markdown for maximum portability",
    ],
    plans=[
        HandPlan(
            name="Blog Post",
            trigger_keywords=["write a blog", "blog post", "article about", "write an article"],
            description="SEO-optimised blog post with engaging structure",
            steps=[
                "search the web for {topic} to gather supporting facts and examples",
                "create file ~/writing/{topic}_blog.md with a full blog post: hook, 3 sections, conclusion",
            ],
            estimated_duration_s=50,
        ),
        HandPlan(
            name="Technical Doc",
            trigger_keywords=["documentation", "write docs", "readme", "technical guide"],
            description="Clear technical documentation with examples",
            steps=[
                "read file {source_file} to understand what to document",
                "create file ~/docs/{name}.md with full technical documentation including examples",
            ],
            estimated_duration_s=40,
        ),
        HandPlan(
            name="Edit & Polish",
            trigger_keywords=["edit", "proofread", "improve writing", "polish", "rewrite"],
            description="Edit and polish existing text for clarity and impact",
            steps=[
                "read file {file_path}",
                "create file {file_path}_edited.md with improved version with tracked changes noted",
            ],
            estimated_duration_s=30,
        ),
    ],
    persona=(
        "You are Arix's Writing Hand — a senior content strategist and editor. You produce "
        "clear, engaging, audience-appropriate writing. You know when to be formal vs. casual, "
        "technical vs. accessible, and always prioritize clarity over cleverness."
    ),
)


# ── Registry of all built-in Hands ────────────────────────────────────────────

BUILTIN_HANDS: List[Hand] = [
    RESEARCHER_HAND,
    CODER_HAND,
    OPS_HAND,
    ANALYST_HAND,
    PREDICTOR_HAND,
    WRITER_HAND,
    BROWSER_HAND,
    CLIP_HAND,
    LEAD_HAND,
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

    def detect_hand(self, command: str) -> Optional[Hand]:
        """
        Returns the single best-matching active Hand for a command, or None.

        Scoring:
          +3  for each trigger keyword that appears in the command
          +1  bonus if a full HandPlan matches (trigger_keywords overlap)
        The highest-scoring active Hand wins; returns None if score == 0.
        """
        lower = command.lower()
        best: Optional[Hand] = None
        best_score = 0

        for hand in self.get_active_hands():
            score = 0
            # Check plan trigger keywords
            for plan in hand.plans:
                for kw in plan.trigger_keywords:
                    if kw in lower:
                        score += 3
            # Small bonus for domain keywords
            for domain in hand.tool_domains:
                if domain in lower:
                    score += 1

            # Extra keywords per hand type
            _HAND_KEYWORDS: dict[str, list[str]] = {
                "researcher-hand": ["research", "find", "look up", "search", "investigate",
                                    "what is", "how does", "summarize", "compare", "analyze"],
                "coder-hand":      ["code", "write code", "generate code", "debug", "function",
                                    "script", "program", "refactor", "test", "class"],
                "ops-hand":        ["deploy", "server", "docker", "k8s", "nginx", "process",
                                    "service", "monitor", "restart", "config"],
                "analyst-hand":    ["analyze", "visualize", "chart", "graph", "data",
                                    "csv", "excel", "spreadsheet", "statistics", "report"],
                "predictor-hand":  ["predict", "forecast", "trend", "model", "ml",
                                    "machine learning", "regression", "classify"],
                "writer-hand":     ["write", "draft", "blog", "email", "document", "article",
                                    "content", "post", "copy", "proofread", "edit"],
                "browser-hand":    ["scrape", "crawl", "website", "webpage", "click",
                                    "fill form", "automate browser", "web app"],
                "clip-hand":       ["clip", "save link", "bookmark", "archive url",
                                    "knowledge", "read later", "extract"],
                "lead-hand":       ["lead", "prospect", "outreach", "sales", "email campaign",
                                    "contact", "linkedin profile", "company research"],
            }
            for kw in _HAND_KEYWORDS.get(hand.hand_id, []):
                if kw in lower:
                    score += 2

            if score > best_score:
                best_score = score
                best = hand

        return best if best_score >= 2 else None

    def detect_relevant_hands(self, command: str) -> List[Hand]:
        """Returns active hands whose tool domains are relevant to this command."""
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
