"""Knowledge Base / Notes — SQLite-backed markdown notes with tags and full-text search."""
from __future__ import annotations
import json
import sqlite3
import time
from pathlib import Path

Arix_DIR = Path.home() / ".arix"
MEMORY_DB = Arix_DIR / "memory.db"


class NotesManager:
    def __init__(self) -> None:
        Arix_DIR.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(MEMORY_DB), check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                tags TEXT DEFAULT '[]',
                pinned INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_notes_updated ON notes(updated_at);
        """)
        self._conn.commit()

    def create_note(self, title: str, content: str = "",
                    tags: list[str] | None = None, pinned: bool = False) -> dict:
        now = time.time()
        cur = self._conn.execute(
            "INSERT INTO notes (title, content, tags, pinned, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (title[:500], content, json.dumps(tags or []), int(pinned), now, now)
        )
        self._conn.commit()
        return self.get_note(cur.lastrowid)  # type: ignore[arg-type]

    def update_note(self, note_id: int, title: str | None = None,
                    content: str | None = None, tags: list[str] | None = None,
                    pinned: bool | None = None) -> dict | None:
        note = self.get_note(note_id)
        if not note:
            return None
        t = title if title is not None else note["title"]
        c = content if content is not None else note["content"]
        tg = json.dumps(tags) if tags is not None else json.dumps(note.get("tags", []))
        pn = int(pinned) if pinned is not None else int(note.get("pinned", False))
        self._conn.execute(
            "UPDATE notes SET title=?, content=?, tags=?, pinned=?, updated_at=? WHERE id=?",
            (t[:500], c, tg, pn, time.time(), note_id)
        )
        self._conn.commit()
        return self.get_note(note_id)

    def delete_note(self, note_id: int) -> bool:
        rows = self._conn.execute("DELETE FROM notes WHERE id=?", (note_id,)).rowcount
        self._conn.commit()
        return rows > 0

    def get_note(self, note_id: int) -> dict | None:
        row = self._conn.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
        return self._row(row) if row else None

    def list_notes(self, limit: int = 100, search: str = "", tag: str = "") -> list[dict]:
        if search:
            rows = self._conn.execute(
                "SELECT * FROM notes WHERE title LIKE ? OR content LIKE ? "
                "ORDER BY pinned DESC, updated_at DESC LIMIT ?",
                (f"%{search}%", f"%{search}%", limit)
            ).fetchall()
        elif tag:
            rows = self._conn.execute(
                'SELECT * FROM notes WHERE tags LIKE ? ORDER BY pinned DESC, updated_at DESC LIMIT ?',
                (f'%"{tag}"%', limit)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM notes ORDER BY pinned DESC, updated_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [self._row(r) for r in rows]

    def note_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]

    def all_tags(self) -> list[str]:
        rows = self._conn.execute("SELECT tags FROM notes").fetchall()
        seen: set[str] = set()
        for row in rows:
            try:
                for t in json.loads(row[0] or "[]"):
                    if t:
                        seen.add(t)
            except Exception:
                pass
        return sorted(seen)

    def _row(self, row) -> dict:
        d = dict(row)
        try:
            d["tags"] = json.loads(d.get("tags") or "[]")
        except Exception:
            d["tags"] = []
        d["pinned"] = bool(d.get("pinned", 0))
        return d
