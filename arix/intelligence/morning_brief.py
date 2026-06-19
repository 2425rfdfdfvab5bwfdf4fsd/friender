"""Morning brief generator — daily digest combining tasks, reminders, insights."""
from __future__ import annotations
import json
import os
import time
from datetime import datetime, date
from pathlib import Path

Arix_DIR = Path.home() / ".arix"
BRIEF_CACHE_FILE = Arix_DIR / "morning_brief_cache.json"

_BRIEF_SYSTEM = """You are Arix's morning briefing generator. Create a warm, concise daily briefing.

Given the user's data, write a short, friendly morning brief in markdown.

Rules:
- Keep it under 200 words
- Use a warm, professional tone
- Lead with the most important item
- Use bullet points for lists
- End with one motivating sentence
- Do NOT repeat information already shown in the structured data
- Add useful context or patterns you notice across the data"""


def _load_cache() -> dict | None:
    if not BRIEF_CACHE_FILE.exists():
        return None
    try:
        data = json.loads(BRIEF_CACHE_FILE.read_text(encoding="utf-8"))
        cached_date = data.get("date", "")
        if cached_date == date.today().isoformat():
            return data
    except Exception:
        pass
    return None


def _save_cache(brief: dict) -> None:
    Arix_DIR.mkdir(parents=True, exist_ok=True)
    BRIEF_CACHE_FILE.write_text(json.dumps(brief, indent=2))


async def generate_morning_brief(
    profile=None,
    todos_data: list[dict] | None = None,
    reminders_data: list[dict] | None = None,
    projects_manager=None,
    memory=None,
    nudges: list[dict] | None = None,
    llm_client=None,
    curator=None,
    researcher=None,
    force: bool = False,
) -> dict:
    """Generate (or return cached) morning brief."""

    if not force:
        cached = _load_cache()
        if cached:
            return cached

    now = datetime.now()
    today = date.today()
    hour = now.hour
    if hour < 12:
        greeting_time = "morning"
    elif hour < 17:
        greeting_time = "afternoon"
    else:
        greeting_time = "evening"

    name = profile.display_name() if profile else "there"
    greeting = f"Good {greeting_time}{', ' + name if name != 'User' else ''}!"
    date_str = today.strftime("%A, %B %-d, %Y")

    sections = []

    # Due today + overdue tasks (todos)
    today_str = today.isoformat()
    pending = [t for t in (todos_data or []) if not t.get("done")]
    overdue = [t for t in pending if t.get("due_date", "") and t.get("due_date", "") < today_str]
    due_today = [t for t in pending if t.get("due_date", "") == today_str]

    if overdue:
        sections.append({
            "type": "overdue",
            "title": "⚠️ Overdue",
            "items": [{"text": t["text"], "priority": t.get("priority", "medium")} for t in overdue[:5]],
            "count": len(overdue),
        })

    if due_today:
        sections.append({
            "type": "due_today",
            "title": "📅 Due Today",
            "items": [{"text": t["text"], "priority": t.get("priority", "medium")} for t in due_today[:5]],
            "count": len(due_today),
        })

    # Pending tasks summary
    other_pending = [t for t in pending if t not in overdue and t not in due_today]
    if other_pending:
        sections.append({
            "type": "tasks",
            "title": "✓ Open Tasks",
            "items": [{"text": t["text"], "priority": t.get("priority", "medium")} for t in other_pending[:5]],
            "count": len(other_pending),
        })

    # Due reminders
    due_rems = []
    for r in (reminders_data or []):
        if r.get("done"):
            continue
        try:
            due_dt = datetime.fromisoformat(r["due"])
            if due_dt.date() == today or due_dt < now:
                due_rems.append(r)
        except Exception:
            pass

    if due_rems:
        sections.append({
            "type": "reminders",
            "title": "🔔 Reminders",
            "items": [{"text": r["text"], "when": r.get("when_text", "")} for r in due_rems[:5]],
            "count": len(due_rems),
        })

    # Project due items
    if projects_manager:
        try:
            proj_overdue = projects_manager.all_overdue_tasks()
            proj_today = projects_manager.all_due_today()
            proj_items = (proj_today + proj_overdue)[:5]
            if proj_items:
                sections.append({
                    "type": "project_tasks",
                    "title": "🎯 Project Tasks",
                    "items": [
                        {"text": t["title"], "project": t.get("project_name", ""), "due": t.get("due_date", "")}
                        for t in proj_items
                    ],
                    "count": len(proj_items),
                })
        except Exception:
            pass

    # Curator stats — learned skills
    if curator:
        try:
            cur_status = curator.get_status()
            total_skills = cur_status.get("total_skills", 0)
            core_skills = cur_status.get("core_skills", 0)
            run_count = cur_status.get("run_count", 0)
            goals_until = cur_status.get("goals_until_next_run", 0)
            if total_skills > 0 or run_count > 0:
                sections.append({
                    "type": "curator",
                    "title": "🧬 Skill Curator",
                    "text": (
                        f"{total_skills} skills learned · {core_skills} core"
                        + (f" · next cycle in {goals_until} goals" if goals_until > 0 else "")
                    ),
                    "total_skills": total_skills,
                    "core_skills": core_skills,
                    "run_count": run_count,
                })
        except Exception:
            pass

    # Recent autonomous research
    if researcher:
        try:
            recent_findings = researcher.get_findings(limit=3)
            if recent_findings:
                sections.append({
                    "type": "research",
                    "title": "🔬 Recent Research",
                    "items": [
                        {"text": f.get("topic", ""), "when": f.get("timestamp", "")}
                        for f in recent_findings[:3]
                    ],
                    "count": len(recent_findings),
                })
        except Exception:
            pass

    # Activity stats
    if memory:
        try:
            stats = memory.get_stats()
            weekly = stats.get("weekly_tasks", 0)
            rate = stats.get("success_rate", 0)
            total = stats.get("total_tasks", 0)
            sections.append({
                "type": "activity",
                "title": "📈 Activity",
                "text": f"{weekly} tasks this week · {total} total · {rate}% success rate",
                "weekly": weekly,
                "total": total,
                "success_rate": rate,
            })
        except Exception:
            pass

    # LLM narrative summary
    llm_summary = ""
    if llm_client and llm_client.is_available():
        try:
            context_parts = [f"Date: {date_str}", f"User: {name}"]
            if overdue:
                context_parts.append(f"Overdue tasks: {len(overdue)} ({', '.join(t['text'][:40] for t in overdue[:3])})")
            if due_today:
                context_parts.append(f"Due today: {len(due_today)} tasks")
            if due_rems:
                context_parts.append(f"Reminders due: {len(due_rems)}")
            if other_pending:
                context_parts.append(f"Open tasks: {len(other_pending)}")
            # Include intelligence context
            for s in sections:
                if s.get("type") == "curator":
                    context_parts.append(f"AI skills learned: {s.get('total_skills',0)} ({s.get('core_skills',0)} core)")
                elif s.get("type") == "research":
                    topics = [i.get("text","") for i in s.get("items",[])]
                    context_parts.append(f"Recent auto-research: {', '.join(topics[:3])}")
            context = "\n".join(context_parts)
            resp = await llm_client.aask(
                system=_BRIEF_SYSTEM,
                user=f"Generate a morning brief for this data:\n{context}",
                max_tokens=350,
            )
            llm_summary = resp.strip() if resp else ""
        except Exception:
            pass

    brief = {
        "date": date_str,
        "date_iso": today.isoformat(),
        "time_of_day": greeting_time,
        "greeting": greeting,
        "sections": sections,
        "nudges": nudges or [],
        "llm_summary": llm_summary,
        "generated_at": time.time(),
        "total_items": sum(s.get("count", 1) for s in sections if s.get("type") != "activity"),
    }

    _save_cache(brief)
    return brief
