"""UsedGrantRegistry — prevents Capability Grant replay.

v8.0: Grant IDs are persisted to SQLite so replay protection survives server restarts.
Non-expired grants are loaded on startup; expired entries are pruned on load and every 10 min.
"""
from __future__ import annotations
import sqlite3
import threading
import time
from pathlib import Path

from arix.models.capability_grant import CapabilityGrant, CapabilityViolation

Arix_DIR = Path.home() / ".arix"
_GRANTS_DB = Arix_DIR / "used_grants.db"


def _open_db() -> sqlite3.Connection:
    Arix_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_GRANTS_DB), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS used_grants (
            grant_id TEXT PRIMARY KEY,
            consumed_at REAL NOT NULL,
            expires_at REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


class UsedGrantRegistry:
    """
    Tracks consumed grant IDs across process restarts via SQLite.
    In-memory set provides O(1) lookup; SQLite provides persistence.
    Background cleanup removes expired rows every 10 minutes.
    """

    def __init__(self) -> None:
        self._consumed: set[str] = set()
        self._lock = threading.Lock()
        self._db: sqlite3.Connection | None = None
        self._last_prune: float = 0.0
        self._load_from_db()

    def _get_db(self) -> sqlite3.Connection:
        if self._db is None:
            self._db = _open_db()
        return self._db

    def _load_from_db(self) -> None:
        """Load non-expired grant IDs from SQLite into the in-memory set."""
        try:
            db = self._get_db()
            now = time.time()
            rows = db.execute(
                "SELECT grant_id FROM used_grants WHERE expires_at > ?", (now,)
            ).fetchall()
            with self._lock:
                for row in rows:
                    self._consumed.add(row[0])
            # Prune already-expired entries on startup
            db.execute("DELETE FROM used_grants WHERE expires_at <= ?", (now,))
            db.commit()
        except Exception:
            pass  # SQLite unavailable — fall back to in-memory only

    def _maybe_prune(self) -> None:
        """Prune expired entries every 10 minutes."""
        now = time.time()
        if now - self._last_prune < 600:
            return
        self._last_prune = now
        try:
            db = self._get_db()
            db.execute("DELETE FROM used_grants WHERE expires_at <= ?", (now,))
            db.commit()
            # Also clean up the in-memory set (rough: expired means TTL > 300s ago)
            with self._lock:
                # We can't know exactly which in-memory entries are expired without
                # querying the DB, so just reload from DB to stay in sync.
                rows = db.execute(
                    "SELECT grant_id FROM used_grants WHERE expires_at > ?", (now,)
                ).fetchall()
                self._consumed = {row[0] for row in rows}
        except Exception:
            pass

    def consume(self, grant: CapabilityGrant) -> None:
        self._maybe_prune()
        with self._lock:
            if grant.grant_id in self._consumed:
                raise CapabilityViolation(
                    f"Grant {grant.grant_id} already consumed — replay prevented"
                )
            self._consumed.add(grant.grant_id)

        try:
            db = self._get_db()
            db.execute(
                "INSERT OR IGNORE INTO used_grants (grant_id, consumed_at, expires_at) VALUES (?, ?, ?)",
                (grant.grant_id, time.time(), grant.expires_at),
            )
            db.commit()
        except Exception:
            pass  # Persistence failed; in-memory set still prevents replay in this session

    def is_consumed(self, grant_id: str) -> bool:
        with self._lock:
            return grant_id in self._consumed

    def clear(self) -> None:
        with self._lock:
            self._consumed.clear()
        try:
            db = self._get_db()
            db.execute("DELETE FROM used_grants")
            db.commit()
        except Exception:
            pass

    def count(self) -> int:
        with self._lock:
            return len(self._consumed)
