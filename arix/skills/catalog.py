"""SkillHub catalog — curated installable workflow templates.

Each Skill maps to a set of workflow steps (natural-language commands) that
get saved as a named Arix workflow when the user clicks "Install".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
import json
import logging

log = logging.getLogger(__name__)

INSTALLED_FILE = Path.home() / ".arix" / "installed_skills.json"


@dataclass
class Skill:
    id: str
    name: str
    description: str
    category: str
    icon: str
    author: str
    version: str
    steps: List[str]
    tags: List[str] = field(default_factory=list)
    rating: float = 0.0
    installs: int = 0


CATALOG: List[Skill] = [
    Skill(
        id="daily-brief",
        name="Daily Morning Brief",
        description="Every morning at 8 AM: summarise unread Gmail, upcoming calendar events, top news, and weather. Sends a digest to your terminal.",
        category="Productivity",
        icon="☀️",
        author="Arix Team",
        version="1.0.0",
        steps=["check unread emails", "list calendar events for today", "research today's top tech news"],
        tags=["daily", "email", "calendar", "brief"],
        rating=4.9,
        installs=8420,
    ),
    Skill(
        id="github-digest",
        name="GitHub PR Digest",
        description="Every weekday at 9 AM: search GitHub for open PRs in your pinned repos and summarise key discussions.",
        category="Developer",
        icon="🐙",
        author="Arix Team",
        version="1.2.0",
        steps=["research open pull requests on my GitHub repos", "summarise PR descriptions and review comments"],
        tags=["github", "developer", "pr", "code review"],
        rating=4.7,
        installs=5100,
    ),
    Skill(
        id="auto-file-cleaner",
        name="Auto File Cleaner",
        description="Every Sunday at 11 PM: move files older than 30 days from Downloads to Archive, then empty trash.",
        category="System",
        icon="🗑️",
        author="Arix Team",
        version="1.1.0",
        steps=["move files older than 30 days from Downloads to Archive", "cleanup temp files"],
        tags=["files", "cleanup", "automation"],
        rating=4.8,
        installs=12800,
    ),
    Skill(
        id="research-saver",
        name="Research & Save",
        description="Research a topic, write a markdown report, and save it to ~/Documents/Research/.",
        category="Research",
        icon="🔬",
        author="Arix Team",
        version="1.0.0",
        steps=["research the given topic in depth", "create a markdown report in ~/Documents/Research/"],
        tags=["research", "markdown", "documents"],
        rating=4.6,
        installs=3900,
    ),
    Skill(
        id="slack-standup",
        name="Slack Standup Poster",
        description="Every weekday at 9:30 AM: read your recent git commits, compose a standup update, and post it to your Slack #standup channel.",
        category="Productivity",
        icon="💬",
        author="Arix Team",
        version="1.0.0",
        steps=["git status", "git diff HEAD~5 HEAD --stat", "send to slack channel #standup: summarise yesterday's work from git history"],
        tags=["slack", "standup", "git", "team"],
        rating=4.8,
        installs=6700,
    ),
    Skill(
        id="drive-backup",
        name="Drive Backup",
        description="Every Friday at 6 PM: zip the ~/Documents folder and upload the archive to Google Drive/Backups/.",
        category="Backup",
        icon="📦",
        author="Arix Team",
        version="1.0.0",
        steps=["zip files in ~/Documents to ~/backups/docs-backup.zip", "upload ~/backups/docs-backup.zip to Google Drive"],
        tags=["backup", "drive", "files"],
        rating=4.5,
        installs=4200,
    ),
    Skill(
        id="notion-journal",
        name="Daily Notion Journal",
        description="Every evening at 9 PM: prompt for today's highlights, wins, and blockers, then create a Notion journal entry.",
        category="Productivity",
        icon="📒",
        author="Arix Team",
        version="1.0.0",
        steps=["create a daily journal entry in Notion with today's date"],
        tags=["notion", "journal", "daily", "reflection"],
        rating=4.7,
        installs=3300,
    ),
    Skill(
        id="competitor-watch",
        name="Competitor Monitor",
        description="Every Monday: research the latest news and product updates from a list of competitors and summarise changes.",
        category="Research",
        icon="🕵️",
        author="Arix Team",
        version="1.0.0",
        steps=["research competitor product updates and news from the past week", "summarise key changes and opportunities"],
        tags=["research", "competitor", "market intelligence"],
        rating=4.4,
        installs=2800,
    ),
    Skill(
        id="code-quality-check",
        name="Code Quality Check",
        description="Analyse code quality, run lint, detect issues, and write a report to code-quality.md.",
        category="Developer",
        icon="🧪",
        author="Arix Team",
        version="1.0.0",
        steps=["analyze code quality in the current directory", "create file code-quality.md with findings"],
        tags=["code", "quality", "lint", "developer"],
        rating=4.6,
        installs=5800,
    ),
    Skill(
        id="youtube-digest",
        name="YouTube Channel Digest",
        description="Every Saturday: search YouTube for new videos from your favourite channels and email yourself a summary.",
        category="Media",
        icon="▶️",
        author="Arix Team",
        version="1.0.0",
        steps=["search YouTube for latest videos from my favourite tech channels", "summarise new video titles and descriptions"],
        tags=["youtube", "video", "digest", "media"],
        rating=4.3,
        installs=2100,
    ),
    Skill(
        id="trello-review",
        name="Weekly Trello Review",
        description="Every Friday at 5 PM: list all Trello cards due this week, count completed vs overdue, and post a summary.",
        category="Productivity",
        icon="📋",
        author="Arix Team",
        version="1.0.0",
        steps=["list trello boards and cards due this week", "summarise completed and overdue tasks"],
        tags=["trello", "tasks", "weekly", "review"],
        rating=4.5,
        installs=3600,
    ),
    Skill(
        id="portfolio-tracker",
        name="Market Snapshot",
        description="Every weekday morning: research the current prices and sentiment for a set of assets and write a markdown snapshot.",
        category="Finance",
        icon="📈",
        author="Arix Team",
        version="1.0.0",
        steps=["research current market prices and financial news", "create a markdown market snapshot report"],
        tags=["finance", "market", "research", "daily"],
        rating=4.2,
        installs=4700,
    ),
]


def _load_installed() -> Dict[str, bool]:
    try:
        if INSTALLED_FILE.exists():
            return json.loads(INSTALLED_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_installed(data: Dict[str, bool]) -> None:
    INSTALLED_FILE.parent.mkdir(parents=True, exist_ok=True)
    INSTALLED_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_skills(category: Optional[str] = None, query: Optional[str] = None) -> List[dict]:
    installed = _load_installed()
    out = []
    for s in CATALOG:
        if category and s.category.lower() != category.lower():
            continue
        if query:
            q = query.lower()
            if q not in s.name.lower() and q not in s.description.lower() and not any(q in t for t in s.tags):
                continue
        out.append({
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "category": s.category,
            "icon": s.icon,
            "author": s.author,
            "version": s.version,
            "tags": s.tags,
            "rating": s.rating,
            "installs": s.installs,
            "installed": installed.get(s.id, False),
        })
    return out


def install_skill(skill_id: str) -> Optional[dict]:
    """Mark a skill as installed and return its workflow data."""
    skill = next((s for s in CATALOG if s.id == skill_id), None)
    if not skill:
        return None
    installed = _load_installed()
    installed[skill_id] = True
    _save_installed(installed)
    return {
        "id": skill.id,
        "name": skill.name,
        "steps": skill.steps,
        "category": skill.category,
    }


def uninstall_skill(skill_id: str) -> bool:
    installed = _load_installed()
    if skill_id not in installed:
        return False
    installed.pop(skill_id, None)
    _save_installed(installed)
    return True


def get_categories() -> List[str]:
    return sorted(set(s.category for s in CATALOG))
