"""Notification center — in-app notification storage and retrieval."""
from __future__ import annotations
import json
import sqlite3
import time
from pathlib import Path

PACCA_DIR = Path.home() / ".pacca"
MEMORY_DB = PACCA_DIR / "memory.db"

NOTIF_TYPES = ("reminder_due", "task_complete", "nudge", "briefing", "workflow_run",
               "goal_complete", "error", "info", "system")


class NotificationManager:
    def __init__(self) -> None:
        PACCA_DIR.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(MEMORY_DB), check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL DEFAULT 'info',
                title TEXT NOT NULL,
                message TEXT DEFAULT '',
                action_label TEXT DEFAULT '',
                action_data TEXT DEFAULT '{}',
                read INTEGER DEFAULT 0,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_notif_read ON notifications(read);
            CREATE INDEX IF NOT EXISTS idx_notif_created ON notifications(created_at);
        """)
        self._conn.commit()

    def add(self, type_: str, title: str, message: str = "",
            action_label: str = "", action_data: dict | None = None) -> dict:
        now = time.time()
        cur = self._conn.execute(
            "INSERT INTO notifications (type, title, message, action_label, action_data, read, created_at) "
            "VALUES (?,?,?,?,?,0,?)",
            (type_, title[:200], message[:1000], action_label, json.dumps(action_data or {}), now)
        )
        self._conn.commit()
        row = self._conn.execute("SELECT * FROM notifications WHERE id=?", (cur.lastrowid,)).fetchone()
        return self._row(row)

    def list_notifications(self, limit: int = 50, unread_only: bool = False) -> list[dict]:
        if unread_only:
            rows = self._conn.execute(
                "SELECT * FROM notifications WHERE read=0 ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM notifications ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row(r) for r in rows]

    def unread_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM notifications WHERE read=0").fetchone()[0]

    def dismiss(self, notif_id: int) -> bool:
        rows = self._conn.execute(
            "UPDATE notifications SET read=1 WHERE id=?", (notif_id,)
        ).rowcount
        self._conn.commit()
        return rows > 0

    def dismiss_all(self) -> int:
        rows = self._conn.execute("UPDATE notifications SET read=1 WHERE read=0").rowcount
        self._conn.commit()
        return rows

    def delete_old(self, keep_days: int = 30) -> int:
        cutoff = time.time() - keep_days * 86400
        rows = self._conn.execute(
            "DELETE FROM notifications WHERE created_at < ? AND read=1", (cutoff,)
        ).rowcount
        self._conn.commit()
        return rows

    def _row(self, row) -> dict:
        d = dict(row)
        try:
            d["action_data"] = json.loads(d.get("action_data") or "{}")
        except Exception:
            d["action_data"] = {}
        d["read"] = bool(d.get("read", 0))
        return d
