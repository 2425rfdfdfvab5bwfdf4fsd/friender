"""To-do manager — simple, persistent task list."""
from __future__ import annotations
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

_Arix_DIR = Path.home() / ".arix"
_TODOS_FILE = _Arix_DIR / "todos.json"

PRIORITIES = ("low", "medium", "high")


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _load() -> list[dict]:
    if not _TODOS_FILE.exists():
        return []
    try:
        return json.loads(_TODOS_FILE.read_text())
    except Exception:
        return []


def _save(data: list[dict]) -> None:
    _Arix_DIR.mkdir(parents=True, exist_ok=True)
    _TODOS_FILE.write_text(json.dumps(data, indent=2))


def _priority_order(p: str) -> int:
    try:
        return {"high": 0, "medium": 1, "low": 2}[p]
    except KeyError:
        return 1


def parse_todo_command(command: str) -> Optional[tuple[str, str]]:
    """
    Parse 'add todo [!priority] [task]' or 'todo: [task]'.
    Returns (text, priority) or None.
    """
    low = command.strip().lower()
    m = re.match(r"(?:add\s+todo|todo:?)\s+(.+)", low, re.IGNORECASE)
    if not m:
        return None

    body = m.group(1).strip()
    priority = "medium"

    # Priority markers: !high, !medium, !low or #high etc.
    pm = re.search(r"[!#](high|medium|low)\b", body, re.IGNORECASE)
    if pm:
        priority = pm.group(1).lower()
        body = body[:pm.start()].strip() + body[pm.end():].strip()
        body = body.strip()

    return (body, priority) if body else None


class TodoManager:
    """CRUD for personal to-do items."""

    def add(self, text: str, priority: str = "medium") -> dict:
        if priority not in PRIORITIES:
            priority = "medium"
        item = {
            "id": str(uuid.uuid4())[:8],
            "text": text,
            "priority": priority,
            "done": False,
            "created": _now_iso(),
            "completed_at": None,
        }
        data = _load()
        data.append(item)
        _save(data)
        return item

    def list_all(self, include_done: bool = False) -> list[dict]:
        data = _load()
        if not include_done:
            data = [t for t in data if not t.get("done")]
        data.sort(key=lambda t: (_priority_order(t.get("priority", "medium")), t.get("created", "")))
        return data

    def mark_done(self, todo_id: str) -> bool:
        data = _load()
        for t in data:
            if t["id"] == todo_id:
                t["done"] = True
                t["completed_at"] = _now_iso()
                _save(data)
                return True
        return False

    def delete(self, todo_id: str) -> bool:
        data = _load()
        new_data = [t for t in data if t["id"] != todo_id]
        if len(new_data) == len(data):
            return False
        _save(new_data)
        return True

    def update(self, todo_id: str, text: str | None = None, priority: str | None = None) -> Optional[dict]:
        data = _load()
        for t in data:
            if t["id"] == todo_id:
                if text is not None:
                    t["text"] = text
                if priority is not None and priority in PRIORITIES:
                    t["priority"] = priority
                _save(data)
                return t
        return None

    def get(self, todo_id: str) -> Optional[dict]:
        for t in _load():
            if t["id"] == todo_id:
                return t
        return None

    def count(self) -> int:
        return len([t for t in _load() if not t.get("done")])
