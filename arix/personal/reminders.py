"""Reminder manager — store, retrieve, and check due reminders."""
from __future__ import annotations
import json
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


_Arix_DIR = Path.home() / ".arix"
_REMINDERS_FILE = _Arix_DIR / "reminders.json"


def _now() -> datetime:
    return datetime.now().astimezone()


def _load() -> list[dict]:
    if not _REMINDERS_FILE.exists():
        return []
    try:
        return json.loads(_REMINDERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(data: list[dict]) -> None:
    _Arix_DIR.mkdir(parents=True, exist_ok=True)
    _REMINDERS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _parse_natural_time(text: str) -> Optional[datetime]:
    """
    Parse natural-language time expressions into a datetime.
    Returns None if unparseable.
    """
    text = text.strip().lower()
    now = _now()

    # "in X minutes/hours/days"
    m = re.match(r"in\s+(\d+)\s+(minute|hour|day|week)s?", text)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if unit == "minute":
            return now + timedelta(minutes=n)
        if unit == "hour":
            return now + timedelta(hours=n)
        if unit == "day":
            return now + timedelta(days=n)
        if unit == "week":
            return now + timedelta(weeks=n)

    # "tomorrow at HH[:MM] [am/pm]"
    m = re.match(r"tomorrow(?:\s+at\s+(.+))?", text)
    if m:
        base = now + timedelta(days=1)
        if m.group(1):
            t = _parse_time_of_day(m.group(1).strip())
            if t:
                return base.replace(hour=t[0], minute=t[1], second=0, microsecond=0)
        return base.replace(hour=9, minute=0, second=0, microsecond=0)

    # "today at HH[:MM] [am/pm]"
    m = re.match(r"today\s+at\s+(.+)", text)
    if m:
        t = _parse_time_of_day(m.group(1).strip())
        if t:
            return now.replace(hour=t[0], minute=t[1], second=0, microsecond=0)

    # "next week"
    if re.match(r"next\s+week", text):
        return now + timedelta(weeks=1)

    # "next monday/tuesday/..." at optional time
    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    m = re.match(r"(?:next\s+)?(" + "|".join(day_names) + r")(?:\s+at\s+(.+))?", text)
    if m:
        target_day = day_names.index(m.group(1))
        days_ahead = (target_day - now.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        base = now + timedelta(days=days_ahead)
        if m.group(2):
            t = _parse_time_of_day(m.group(2).strip())
            if t:
                return base.replace(hour=t[0], minute=t[1], second=0, microsecond=0)
        return base.replace(hour=9, minute=0, second=0, microsecond=0)

    # "at HH[:MM] [am/pm]" — today, or tomorrow if time already passed
    m = re.match(r"at\s+(.+)", text)
    if m:
        t = _parse_time_of_day(m.group(1).strip())
        if t:
            candidate = now.replace(hour=t[0], minute=t[1], second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            return candidate

    # Try ISO datetime fallback
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass

    return None


def _parse_time_of_day(text: str) -> Optional[tuple[int, int]]:
    """Return (hour24, minute) or None."""
    text = text.strip().lower()
    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    meridiem = m.group(3)
    if meridiem == "pm" and hour != 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return (hour, minute)
    return None


def parse_reminder_command(command: str) -> Optional[tuple[str, str]]:
    """
    Try to parse 'remind me [when] to [what]' or 'remind me to [what] [when]'.
    Returns (text, when_str) or None.
    """
    low = command.strip().lower()

    # "remind me [when] to [what]"
    m = re.match(
        r"remind\s+me\s+(.+?)\s+to\s+(.+)",
        low, re.IGNORECASE
    )
    if m:
        when_str = m.group(1).strip()
        what = m.group(2).strip()
        # if the when_str is actually just "to", it's "remind me to X"
        if when_str in ("", "to"):
            return None
        return (what, when_str)

    # "remind me to [what] [when]"
    m = re.match(
        r"remind\s+me\s+to\s+(.+?)\s+(tomorrow|today|in\s+\d+|next\s+\w+|at\s+\d+|on\s+\w+)(.*)$",
        low, re.IGNORECASE
    )
    if m:
        what = m.group(1).strip()
        when_str = (m.group(2) + m.group(3)).strip()
        return (what, when_str)

    return None


class ReminderManager:
    """CRUD for personal reminders."""

    def add(self, text: str, due_str: str) -> dict:
        """Add a reminder. due_str is a natural language time expression."""
        due_dt = _parse_natural_time(due_str)
        if due_dt is None:
            # Default: 1 hour from now
            due_dt = _now() + timedelta(hours=1)

        reminder = {
            "id": str(uuid.uuid4())[:8],
            "text": text,
            "due": due_dt.isoformat(),
            "created": _now().isoformat(),
            "done": False,
        }
        data = _load()
        data.append(reminder)
        _save(data)
        return reminder

    def list_all(self, include_done: bool = False) -> list[dict]:
        data = _load()
        if not include_done:
            data = [r for r in data if not r.get("done")]
        data.sort(key=lambda r: r.get("due", ""))
        return data

    def list_due(self) -> list[dict]:
        """Return reminders that are due (past their due time) and not done."""
        now_str = _now().isoformat()
        return [r for r in _load() if not r.get("done") and r.get("due", "") <= now_str]

    def mark_done(self, reminder_id: str) -> bool:
        data = _load()
        for r in data:
            if r["id"] == reminder_id:
                r["done"] = True
                _save(data)
                return True
        return False

    def delete(self, reminder_id: str) -> bool:
        data = _load()
        new_data = [r for r in data if r["id"] != reminder_id]
        if len(new_data) == len(data):
            return False
        _save(new_data)
        return True

    def get(self, reminder_id: str) -> Optional[dict]:
        for r in _load():
            if r["id"] == reminder_id:
                return r
        return None

    def count(self) -> int:
        return len([r for r in _load() if not r.get("done")])
