"""PACCA Persistent Memory System — SQLite-backed episodic, preference, project, and workflow memory."""
from __future__ import annotations
import json
import math
import os
import re
import sqlite3
import time
from collections import Counter
from pathlib import Path
from typing import Any

PACCA_DIR = Path.home() / ".pacca"
MEMORY_DB = PACCA_DIR / "memory.db"
PREFS_FILE = PACCA_DIR / "user_prefs.json"


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[k] * b[k] for k in a if k in b)
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _tokenize(text: str) -> Counter:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return Counter(tokens)


class MemoryManager:
    """Manages all PACCA memory types: episodic, preferences, project, workflow, semantic."""

    def __init__(self) -> None:
        PACCA_DIR.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(MEMORY_DB), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._prefs: dict = self._load_prefs()

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS episodic (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                command TEXT NOT NULL,
                intent_verb TEXT,
                intent_domain TEXT,
                outcome TEXT,
                steps_executed INTEGER DEFAULT 0,
                risk_score REAL DEFAULT 0,
                files_affected TEXT DEFAULT '[]',
                tags TEXT DEFAULT '[]',
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS project_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_path TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL,
                UNIQUE(project_path, key)
            );

            CREATE TABLE IF NOT EXISTS semantic_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                source TEXT,
                tags TEXT DEFAULT '[]',
                tokens TEXT NOT NULL,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS workflow_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_name TEXT NOT NULL,
                outcome TEXT NOT NULL,
                details TEXT,
                ran_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_episodic_domain ON episodic(intent_domain);
            CREATE INDEX IF NOT EXISTS idx_episodic_created ON episodic(created_at);
            CREATE INDEX IF NOT EXISTS idx_project_path ON project_memory(project_path);
        """)
        self._conn.commit()

    def _load_prefs(self) -> dict:
        if PREFS_FILE.exists():
            try:
                return json.loads(PREFS_FILE.read_text())
            except Exception:
                pass
        return {}

    def _save_prefs(self) -> None:
        PREFS_FILE.write_text(json.dumps(self._prefs, indent=2))
        os.chmod(PREFS_FILE, 0o600)

    # ── Episodic Memory ──────────────────────────────────────────────────────

    def record_task(self, task_id: str, command: str, intent_verb: str,
                    intent_domain: str, outcome: str, steps_executed: int = 0,
                    risk_score: float = 0.0, files_affected: list[str] | None = None,
                    tags: list[str] | None = None) -> None:
        self._conn.execute(
            """INSERT INTO episodic
               (task_id, command, intent_verb, intent_domain, outcome,
                steps_executed, risk_score, files_affected, tags, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, command[:500], intent_verb, intent_domain, outcome,
             steps_executed, risk_score,
             json.dumps(files_affected or []),
             json.dumps(tags or [intent_domain, intent_verb]),
             time.time())
        )
        self._conn.commit()
        self._maybe_store_semantic(command, tags=[intent_domain, intent_verb])
        self._prune_episodic()

    def _prune_episodic(self, keep_days: int = 90) -> None:
        cutoff = time.time() - keep_days * 86400
        self._conn.execute("DELETE FROM episodic WHERE created_at < ?", (cutoff,))
        self._conn.commit()

    def recent_tasks(self, limit: int = 20, domain: str | None = None) -> list[dict]:
        if domain:
            rows = self._conn.execute(
                "SELECT * FROM episodic WHERE intent_domain=? ORDER BY created_at DESC LIMIT ?",
                (domain, limit)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM episodic ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def task_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM episodic").fetchone()[0]

    # ── User Preferences ─────────────────────────────────────────────────────

    def set_preference(self, key: str, value: Any) -> None:
        self._prefs[key] = value
        self._save_prefs()

    def get_preference(self, key: str, default: Any = None) -> Any:
        return self._prefs.get(key, default)

    def get_all_preferences(self) -> dict:
        return dict(self._prefs)

    def update_preferences(self, updates: dict) -> None:
        self._prefs.update(updates)
        self._save_prefs()

    # ── Project Memory ───────────────────────────────────────────────────────

    def set_project(self, project_path: str, key: str, value: Any) -> None:
        self._conn.execute(
            """INSERT INTO project_memory (project_path, key, value, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(project_path, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
            (project_path, key, json.dumps(value), time.time())
        )
        self._conn.commit()

    def get_project(self, project_path: str, key: str, default: Any = None) -> Any:
        row = self._conn.execute(
            "SELECT value FROM project_memory WHERE project_path=? AND key=?",
            (project_path, key)
        ).fetchone()
        if row:
            try:
                return json.loads(row["value"])
            except Exception:
                return row["value"]
        return default

    def get_all_project(self, project_path: str) -> dict:
        rows = self._conn.execute(
            "SELECT key, value FROM project_memory WHERE project_path=?",
            (project_path,)
        ).fetchall()
        result = {}
        for r in rows:
            try:
                result[r["key"]] = json.loads(r["value"])
            except Exception:
                result[r["key"]] = r["value"]
        return result

    # ── Semantic Memory ──────────────────────────────────────────────────────

    def _maybe_store_semantic(self, content: str, tags: list[str] | None = None) -> None:
        if len(content) < 20:
            return
        tokens = json.dumps(dict(_tokenize(content)))
        self._conn.execute(
            "INSERT INTO semantic_memory (content, source, tags, tokens, created_at) VALUES (?, ?, ?, ?, ?)",
            (content[:1000], "episodic", json.dumps(tags or []), tokens, time.time())
        )
        self._conn.commit()

    def store_knowledge(self, content: str, source: str = "user",
                        tags: list[str] | None = None) -> None:
        tokens = json.dumps(dict(_tokenize(content)))
        self._conn.execute(
            "INSERT INTO semantic_memory (content, source, tags, tokens, created_at) VALUES (?, ?, ?, ?, ?)",
            (content[:2000], source, json.dumps(tags or []), tokens, time.time())
        )
        self._conn.commit()

    def semantic_search(self, query: str, top_k: int = 5,
                        min_score: float = 0.1) -> list[dict]:
        q_tokens = _tokenize(query)
        rows = self._conn.execute(
            "SELECT content, source, tags, tokens, created_at FROM semantic_memory ORDER BY created_at DESC LIMIT 500"
        ).fetchall()
        scored = []
        for r in rows:
            try:
                doc_tokens = Counter(json.loads(r["tokens"]))
                score = _cosine(q_tokens, doc_tokens)
                if score >= min_score:
                    scored.append({
                        "content": r["content"],
                        "source": r["source"],
                        "tags": json.loads(r["tags"]),
                        "score": round(score, 4),
                        "created_at": r["created_at"],
                    })
            except Exception:
                continue
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    # ── Workflow Run History ─────────────────────────────────────────────────

    def record_workflow_run(self, name: str, outcome: str, details: str = "") -> None:
        self._conn.execute(
            "INSERT INTO workflow_runs (workflow_name, outcome, details, ran_at) VALUES (?, ?, ?, ?)",
            (name, outcome, details[:500], time.time())
        )
        self._conn.commit()

    def workflow_run_history(self, name: str, limit: int = 10) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM workflow_runs WHERE workflow_name=? ORDER BY ran_at DESC LIMIT ?",
            (name, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Context Building for Agent ───────────────────────────────────────────

    def build_context_for_command(self, command: str, domain: str | None = None,
                                   top_k: int = 5) -> str:
        lines = []
        recent = self.recent_tasks(limit=5, domain=domain)
        if recent:
            lines.append("## Recent similar tasks")
            for t in recent:
                ts = time.strftime("%Y-%m-%d", time.localtime(t["created_at"]))
                lines.append(f"- [{ts}] {t['command'][:80]} → {t['outcome']}")

        semantic = self.semantic_search(command, top_k=top_k)
        if semantic:
            lines.append("\n## Related knowledge")
            for s in semantic:
                lines.append(f"- {s['content'][:120]}")

        prefs = self.get_all_preferences()
        if prefs:
            lines.append("\n## User preferences")
            for k, v in list(prefs.items())[:10]:
                lines.append(f"- {k}: {v}")

        return "\n".join(lines) if lines else ""

    def get_stats(self) -> dict:
        """Return analytics about the stored memory for the Insights panel."""
        total = self.task_count()

        # Domain breakdown with success rates
        domain_rows = self._conn.execute(
            """SELECT intent_domain,
                      COUNT(*) AS n,
                      SUM(CASE WHEN outcome='completed' THEN 1 ELSE 0 END) AS ok
               FROM episodic
               GROUP BY intent_domain
               ORDER BY n DESC"""
        ).fetchall()
        domains = [
            {
                "domain": r["intent_domain"] or "unknown",
                "count": r["n"],
                "success": r["ok"],
                "success_rate": round(r["ok"] / r["n"] * 100) if r["n"] else 0,
            }
            for r in domain_rows
        ]

        # Daily activity for the last 14 days
        cutoff = time.time() - 14 * 86400
        daily_rows = self._conn.execute(
            """SELECT date(created_at, 'unixepoch') AS day, COUNT(*) AS n
               FROM episodic
               WHERE created_at >= ?
               GROUP BY day
               ORDER BY day DESC""",
            (cutoff,)
        ).fetchall()
        daily = [{"day": r["day"], "count": r["n"]} for r in daily_rows]

        # Overall success rate
        ok_total = self._conn.execute(
            "SELECT COUNT(*) FROM episodic WHERE outcome='completed'"
        ).fetchone()[0]
        success_rate = round(ok_total / total * 100) if total else 0

        # Average steps per task
        avg_row = self._conn.execute(
            "SELECT AVG(steps_executed) FROM episodic"
        ).fetchone()[0]
        avg_steps = round(avg_row or 0, 1)

        # Most recent commands (top 5 unique)
        recent_cmds = self._conn.execute(
            """SELECT command, MAX(created_at) AS ts
               FROM episodic
               GROUP BY command
               ORDER BY ts DESC
               LIMIT 5"""
        ).fetchall()
        recent = [r["command"][:80] for r in recent_cmds]

        # Semantic memory count
        sem_count = self._conn.execute(
            "SELECT COUNT(*) FROM semantic_memory"
        ).fetchone()[0]

        # Workflow run count
        wf_count = self._conn.execute(
            "SELECT COUNT(*) FROM workflow_runs"
        ).fetchone()[0]

        return {
            "total_tasks": total,
            "success_rate": success_rate,
            "avg_steps": avg_steps,
            "domains": domains,
            "daily_activity": daily,
            "recent_commands": recent,
            "semantic_memory_count": sem_count,
            "workflow_runs": wf_count,
        }

    def close(self) -> None:
        self._conn.close()
