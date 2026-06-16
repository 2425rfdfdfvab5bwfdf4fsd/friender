"""Enhanced project management — projects with tasks, milestones, priorities."""
from __future__ import annotations
import json
import sqlite3
import time
from pathlib import Path

Arix_DIR = Path.home() / ".arix"
MEMORY_DB = Arix_DIR / "memory.db"

STATUS_PROJECT = ("active", "paused", "completed", "archived")
STATUS_TASK = ("todo", "in_progress", "done", "blocked")
PRIORITY = ("low", "medium", "high", "urgent")
COLORS = ["#4f8ef7", "#10b981", "#f59e0b", "#f04b4b", "#8b5cf6", "#06b6d4", "#ec4899"]


class ProjectsManager:
    def __init__(self) -> None:
        Arix_DIR.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(MEMORY_DB), check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                color TEXT DEFAULT '#4f8ef7',
                due_date TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS project_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT DEFAULT 'todo',
                priority TEXT DEFAULT 'medium',
                due_date TEXT DEFAULT '',
                time_estimate INTEGER DEFAULT 0,
                tags TEXT DEFAULT '[]',
                completed_at REAL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
            CREATE INDEX IF NOT EXISTS idx_ptasks_project ON project_tasks(project_id);
            CREATE INDEX IF NOT EXISTS idx_ptasks_status ON project_tasks(status);
        """)
        self._conn.commit()

    # ── Projects ──────────────────────────────────────────────────────────────

    def create_project(self, name: str, description: str = "", color: str = "",
                       due_date: str = "", tags: list[str] | None = None) -> dict:
        now = time.time()
        if not color:
            idx = self._conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            color = COLORS[idx % len(COLORS)]
        cur = self._conn.execute(
            "INSERT INTO projects (name, description, status, color, due_date, tags, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (name[:200], description, "active", color, due_date, json.dumps(tags or []), now, now)
        )
        self._conn.commit()
        return self.get_project(cur.lastrowid)  # type: ignore[arg-type]

    def get_project(self, project_id: int) -> dict | None:
        row = self._conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            return None
        p = self._proj_row(row)
        p["tasks"] = self.list_tasks(project_id)
        p["task_counts"] = self._task_counts(project_id)
        return p

    def list_projects(self, status: str = "") -> list[dict]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM projects WHERE status=? ORDER BY updated_at DESC", (status,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM projects ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'paused' THEN 1 "
                "WHEN 'completed' THEN 2 ELSE 3 END, updated_at DESC"
            ).fetchall()
        result = []
        for row in rows:
            p = self._proj_row(row)
            p["task_counts"] = self._task_counts(p["id"])
            result.append(p)
        return result

    def update_project(self, project_id: int, **kwargs) -> dict | None:
        proj = self.get_project(project_id)
        if not proj:
            return None
        allowed = {"name", "description", "status", "color", "due_date", "tags"}
        sets = []
        vals = []
        for k, v in kwargs.items():
            if k in allowed:
                sets.append(f"{k}=?")
                vals.append(json.dumps(v) if k == "tags" else v)
        if not sets:
            return proj
        vals.extend([time.time(), project_id])
        self._conn.execute(f"UPDATE projects SET {', '.join(sets)}, updated_at=? WHERE id=?", vals)
        self._conn.commit()
        return self.get_project(project_id)

    def delete_project(self, project_id: int) -> bool:
        rows = self._conn.execute("DELETE FROM projects WHERE id=?", (project_id,)).rowcount
        self._conn.commit()
        return rows > 0

    # ── Tasks ─────────────────────────────────────────────────────────────────

    def add_task(self, project_id: int, title: str, description: str = "",
                 priority: str = "medium", due_date: str = "",
                 time_estimate: int = 0, tags: list[str] | None = None) -> dict | None:
        if not self._conn.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone():
            return None
        now = time.time()
        cur = self._conn.execute(
            "INSERT INTO project_tasks (project_id, title, description, status, priority, "
            "due_date, time_estimate, tags, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (project_id, title[:300], description, "todo", priority, due_date,
             time_estimate, json.dumps(tags or []), now, now)
        )
        self._conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (now, project_id))
        self._conn.commit()
        row = self._conn.execute("SELECT * FROM project_tasks WHERE id=?", (cur.lastrowid,)).fetchone()
        return self._task_row(row) if row else None

    def update_task(self, task_id: int, **kwargs) -> dict | None:
        row = self._conn.execute("SELECT * FROM project_tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return None
        allowed = {"title", "description", "status", "priority", "due_date", "time_estimate", "tags"}
        sets = []
        vals = []
        for k, v in kwargs.items():
            if k in allowed:
                sets.append(f"{k}=?")
                vals.append(json.dumps(v) if k == "tags" else v)
        if not sets:
            return self._task_row(row)
        now = time.time()
        completed_at = now if kwargs.get("status") == "done" else None
        if "status" in kwargs:
            sets.append("completed_at=?")
            vals.append(completed_at)
        vals.extend([now, task_id])
        self._conn.execute(f"UPDATE project_tasks SET {', '.join(sets)}, updated_at=? WHERE id=?", vals)
        pid = row["project_id"]
        self._conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (now, pid))
        self._conn.commit()
        row2 = self._conn.execute("SELECT * FROM project_tasks WHERE id=?", (task_id,)).fetchone()
        return self._task_row(row2) if row2 else None

    def delete_task(self, task_id: int) -> bool:
        rows = self._conn.execute("DELETE FROM project_tasks WHERE id=?", (task_id,)).rowcount
        self._conn.commit()
        return rows > 0

    def list_tasks(self, project_id: int, status: str = "") -> list[dict]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM project_tasks WHERE project_id=? AND status=? ORDER BY "
                "CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, created_at",
                (project_id, status)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM project_tasks WHERE project_id=? ORDER BY "
                "CASE status WHEN 'in_progress' THEN 0 WHEN 'todo' THEN 1 WHEN 'blocked' THEN 2 ELSE 3 END, "
                "CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, created_at",
                (project_id,)
            ).fetchall()
        return [self._task_row(r) for r in rows]

    def all_overdue_tasks(self) -> list[dict]:
        today = __import__('datetime').date.today().isoformat()
        rows = self._conn.execute(
            "SELECT pt.*, p.name as project_name, p.color as project_color FROM project_tasks pt "
            "JOIN projects p ON pt.project_id=p.id "
            "WHERE pt.status NOT IN ('done') AND pt.due_date != '' AND pt.due_date < ? "
            "ORDER BY pt.due_date",
            (today,)
        ).fetchall()
        return [dict(r) for r in rows]

    def all_due_today(self) -> list[dict]:
        today = __import__('datetime').date.today().isoformat()
        rows = self._conn.execute(
            "SELECT pt.*, p.name as project_name, p.color as project_color FROM project_tasks pt "
            "JOIN projects p ON pt.project_id=p.id "
            "WHERE pt.status NOT IN ('done') AND pt.due_date = ? ORDER BY pt.priority",
            (today,)
        ).fetchall()
        return [dict(r) for r in rows]

    def project_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM projects WHERE status='active'").fetchone()[0]

    def _task_counts(self, project_id: int) -> dict:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) as n FROM project_tasks WHERE project_id=? GROUP BY status",
            (project_id,)
        ).fetchall()
        counts = {s: 0 for s in STATUS_TASK}
        for r in rows:
            counts[r["status"]] = r["n"]
        counts["total"] = sum(counts.values())
        return counts

    def _proj_row(self, row) -> dict:
        d = dict(row)
        try:
            d["tags"] = json.loads(d.get("tags") or "[]")
        except Exception:
            d["tags"] = []
        return d

    def _task_row(self, row) -> dict:
        d = dict(row)
        try:
            d["tags"] = json.loads(d.get("tags") or "[]")
        except Exception:
            d["tags"] = []
        return d
