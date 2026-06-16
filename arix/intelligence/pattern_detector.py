"""Proactive intelligence — detect patterns and generate actionable nudges."""
from __future__ import annotations
import time
from datetime import datetime, date, timedelta


def get_nudges(
    todos: list[dict] | None = None,
    reminders: list[dict] | None = None,
    projects_manager=None,
    memory=None,
) -> list[dict]:
    """Return a list of actionable nudge dicts: {type, icon, title, message, action}."""
    nudges: list[dict] = []
    now = datetime.now()
    today_str = date.today().isoformat()

    # ── Todo nudges ───────────────────────────────────────────────────────────
    if todos:
        pending = [t for t in todos if not t.get("done")]
        overdue_todos = []
        urgent = []
        for t in pending:
            due = t.get("due_date") or ""
            if due and due < today_str:
                overdue_todos.append(t)
            if t.get("priority") in ("high", "urgent"):
                urgent.append(t)

        if overdue_todos:
            nudges.append({
                "type": "overdue",
                "icon": "⚠️",
                "title": f"{len(overdue_todos)} overdue task{'s' if len(overdue_todos) > 1 else ''}",
                "message": f"'{overdue_todos[0]['text'][:60]}'" + (
                    f" and {len(overdue_todos)-1} more" if len(overdue_todos) > 1 else ""
                ),
                "action": "open_tasks",
            })
        if urgent and not overdue_todos:
            nudges.append({
                "type": "urgent",
                "icon": "🔴",
                "title": f"{len(urgent)} urgent/high priority task{'s' if len(urgent) > 1 else ''}",
                "message": f"'{urgent[0]['text'][:60]}'",
                "action": "open_tasks",
            })
        if len(pending) >= 10:
            nudges.append({
                "type": "backlog",
                "icon": "📋",
                "title": f"You have {len(pending)} pending tasks",
                "message": "Consider reviewing and prioritizing your task list.",
                "action": "open_tasks",
            })

    # ── Reminder nudges ───────────────────────────────────────────────────────
    if reminders:
        overdue_rems = []
        due_soon = []
        for r in reminders:
            if r.get("done"):
                continue
            try:
                due = datetime.fromisoformat(r["due"]) if isinstance(r.get("due"), str) else None
                if due:
                    if due < now:
                        overdue_rems.append(r)
                    elif (due - now).total_seconds() < 3600:
                        due_soon.append(r)
            except Exception:
                pass

        if overdue_rems:
            nudges.append({
                "type": "reminder_overdue",
                "icon": "🔔",
                "title": f"{len(overdue_rems)} overdue reminder{'s' if len(overdue_rems) > 1 else ''}",
                "message": f"'{overdue_rems[0]['text'][:60]}'",
                "action": "open_reminders",
            })
        if due_soon:
            nudges.append({
                "type": "reminder_soon",
                "icon": "⏰",
                "title": f"Reminder due soon",
                "message": f"'{due_soon[0]['text'][:60]}' in less than 1 hour",
                "action": "open_reminders",
            })

    # ── Project nudges ────────────────────────────────────────────────────────
    if projects_manager:
        try:
            overdue_tasks = projects_manager.all_overdue_tasks()
            if overdue_tasks:
                nudges.append({
                    "type": "project_overdue",
                    "icon": "🎯",
                    "title": f"{len(overdue_tasks)} overdue project task{'s' if len(overdue_tasks) > 1 else ''}",
                    "message": f"'{overdue_tasks[0]['title'][:60]}' in {overdue_tasks[0].get('project_name', 'project')}",
                    "action": "open_projects",
                })
            due_today = projects_manager.all_due_today()
            if due_today:
                nudges.append({
                    "type": "project_due_today",
                    "icon": "📅",
                    "title": f"{len(due_today)} project task{'s' if len(due_today) > 1 else ''} due today",
                    "message": f"'{due_today[0]['title'][:60]}'",
                    "action": "open_projects",
                })
        except Exception:
            pass

    # ── Memory-based nudges ───────────────────────────────────────────────────
    if memory:
        try:
            count = memory.task_count()
            recent = memory.recent_tasks(limit=5)
            if count > 0 and recent:
                last_task_ts = recent[0].get("created_at", 0)
                days_idle = (time.time() - last_task_ts) / 86400
                if days_idle > 3:
                    nudges.append({
                        "type": "idle",
                        "icon": "💤",
                        "title": f"No tasks in {int(days_idle)} days",
                        "message": "Ready to help when you are. What should we work on?",
                        "action": "focus_input",
                    })
        except Exception:
            pass

    return nudges[:6]


def get_daily_activity_summary(memory) -> dict:
    """Return a brief text summary of recent activity."""
    try:
        stats = memory.get_stats()
        total = stats.get("total_tasks", 0)
        rate = stats.get("success_rate", 0)
        domains = stats.get("domains", [])
        top_domain = domains[0]["domain"] if domains else "general"
        return {
            "total_tasks": total,
            "success_rate": rate,
            "top_domain": top_domain,
            "weekly_tasks": stats.get("weekly_tasks", 0),
        }
    except Exception:
        return {"total_tasks": 0, "success_rate": 0, "top_domain": "", "weekly_tasks": 0}
