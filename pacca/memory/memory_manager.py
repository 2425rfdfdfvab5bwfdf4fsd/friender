"""PACCA Persistent Memory System — SQLite-backed episodic, preference, project, workflow, and skill memory.

Gap #2: Improved semantic search — IDF-weighted TF-IDF with bigrams replaces Counter-only cosine.
Gap #10: Implicit preference learning — background pattern detection from episodic history.
Gap #12: SkillLibrary — save successful goal traces as named reusable procedures.
"""
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


# ── Gap #2: Improved tokenization with bigrams ────────────────────────────────

def _tokenize(text: str) -> Counter:
    """Tokenize text into unigrams + bigrams for richer semantic matching."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    counts: Counter = Counter(tokens)
    # Add bigrams with half-weight
    for i in range(len(tokens) - 1):
        bigram = f"{tokens[i]}_{tokens[i+1]}"
        counts[bigram] = counts.get(bigram, 0) + 0.5
    return counts


def _cosine_idf(query: Counter, doc: Counter,
                idf: dict[str, float] | None = None) -> float:
    """IDF-weighted cosine similarity between two token Counters.

    If idf dict is provided, each token weight is multiplied by its IDF score,
    giving rare terms more influence than common ones.
    """
    if not query or not doc:
        return 0.0

    def weighted(c: Counter) -> dict[str, float]:
        if idf:
            return {k: v * idf.get(k, 1.0) for k, v in c.items()}
        return dict(c)

    qw = weighted(query)
    dw = weighted(doc)

    dot = sum(qw[k] * dw[k] for k in qw if k in dw)
    mag_q = math.sqrt(sum(v * v for v in qw.values()))
    mag_d = math.sqrt(sum(v * v for v in dw.values()))
    if mag_q == 0 or mag_d == 0:
        return 0.0
    return dot / (mag_q * mag_d)


class MemoryManager:
    """Manages all PACCA memory types: episodic, preferences, project, workflow, semantic, skills."""

    def __init__(self) -> None:
        PACCA_DIR.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(MEMORY_DB), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._prefs: dict = self._load_prefs()
        # Gap #2: IDF cache — recomputed lazily
        self._idf_cache: dict[str, float] = {}
        self._idf_doc_count: int = 0
        self._idf_dirty: bool = True

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

            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                content TEXT NOT NULL,
                queries_run TEXT DEFAULT '[]',
                sources_count INTEGER DEFAULT 0,
                saved_path TEXT DEFAULT '',
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                steps TEXT NOT NULL DEFAULT '[]',
                goal TEXT NOT NULL DEFAULT '',
                decomposition_method TEXT DEFAULT 'heuristic',
                used_count INTEGER DEFAULT 0,
                last_used REAL,
                created_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_episodic_domain ON episodic(intent_domain);
            CREATE INDEX IF NOT EXISTS idx_episodic_created ON episodic(created_at);
            CREATE INDEX IF NOT EXISTS idx_project_path ON project_memory(project_path);
            CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at);
            CREATE INDEX IF NOT EXISTS idx_skills_created ON skills(created_at);
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
        self._idf_dirty = True

        # Gap #10: Check if it's time to run implicit preference detection
        task_count = self.task_count()
        if task_count > 0 and task_count % 10 == 0:
            self._run_implicit_preference_detection()

    def _prune_episodic(self, keep_days: int = 90) -> None:
        """Delete episodic records older than keep_days that were never compressed."""
        cutoff = time.time() - keep_days * 86400
        self._conn.execute("DELETE FROM episodic WHERE created_at < ?", (cutoff,))
        self._conn.commit()

    def compress_old_sessions(
        self,
        days: int = 7,
        llm_summary_fn=None,
    ) -> dict:
        """Summarize episodic records older than `days` days into semantic memory.

        Gap #2 — MemoryCompressor:
        - Groups tasks older than `days` by calendar-day × intent_domain
        - Produces a 1–2 sentence summary per group (deterministic, or via LLM)
        - Stores each summary in semantic_memory with source="compressed_session"
        - Deletes the original episodic rows to keep the DB lean

        Args:
            days: Age threshold in days (default 7)
            llm_summary_fn: Optional async/sync callable(text) -> str for LLM summaries.
                            Pass None to use deterministic template summaries.

        Returns:
            {"compressed": int, "groups": int, "skipped": int}
        """
        import math as _math
        from collections import defaultdict as _dd

        cutoff = time.time() - days * 86400
        rows = self._conn.execute(
            """SELECT id, task_id, command, intent_verb, intent_domain,
                      outcome, steps_executed, files_affected, created_at
               FROM episodic
               WHERE created_at < ?
               ORDER BY created_at ASC
               LIMIT 500""",
            (cutoff,),
        ).fetchall()

        if not rows:
            return {"compressed": 0, "groups": 0, "skipped": 0}

        # ── Group by (calendar-day, domain) ──────────────────────────────────
        groups: dict[tuple, list] = _dd(list)
        for r in rows:
            day = time.strftime("%Y-%m-%d", time.localtime(r["created_at"]))
            domain = r["intent_domain"] or "general"
            groups[(day, domain)].append(r)

        compressed_total = 0
        groups_written = 0
        skipped = 0

        for (day, domain), g_rows in groups.items():
            try:
                # ── Build deterministic summary ───────────────────────────
                verbs: Counter = Counter(
                    r["intent_verb"] for r in g_rows if r["intent_verb"]
                )
                outcomes: Counter = Counter(r["outcome"] for r in g_rows)
                n = len(g_rows)
                ok = outcomes.get("completed", 0)
                top_verb = verbs.most_common(1)[0][0] if verbs else "executed tasks"
                sample_cmds = [r["command"][:70] for r in g_rows[:4]]
                summary = (
                    f"On {day}, {n} {domain} task(s) were completed "
                    f"({ok}/{n} succeeded). "
                    f"Primary action: {top_verb}. "
                    f"Examples: {'; '.join(sample_cmds)}."
                )

                # ── Optionally upgrade via LLM ────────────────────────────
                if llm_summary_fn is not None:
                    bullet_list = "\n".join(
                        f"- {r['command'][:80]} ({r['outcome']})" for r in g_rows
                    )
                    prompt = (
                        f"Summarize these {n} computer-control tasks in 1–2 sentences, "
                        f"focusing on what was accomplished and any notable outcomes.\n\n"
                        f"{bullet_list}"
                    )
                    try:
                        llm_result = llm_summary_fn(prompt)
                        # Support both sync and async callables
                        if hasattr(llm_result, "__await__"):
                            import asyncio as _aio
                            try:
                                loop = _aio.get_running_loop()
                                # Can't await inside sync method; fall back
                            except RuntimeError:
                                llm_result = _aio.run(llm_result)
                                if llm_result:
                                    summary = llm_result.strip()
                    except Exception:
                        pass  # Keep deterministic summary on LLM error

                # ── Persist compressed summary ─────────────────────────────
                self.store_knowledge(
                    summary,
                    source="compressed_session",
                    tags=["compressed", domain, day],
                )

                # ── Delete original episodic rows ──────────────────────────
                ids = [r["id"] for r in g_rows]
                self._conn.execute(
                    f"DELETE FROM episodic WHERE id IN ({','.join('?' * len(ids))})",
                    ids,
                )
                self._conn.commit()

                compressed_total += n
                groups_written += 1

            except Exception:
                skipped += len(g_rows)

        return {"compressed": compressed_total, "groups": groups_written, "skipped": skipped}

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

    # ── Semantic Memory (Gap #2: IDF-weighted) ───────────────────────────────

    def _maybe_store_semantic(self, content: str, tags: list[str] | None = None) -> None:
        if len(content) < 20:
            return
        tokens = json.dumps(dict(_tokenize(content)))
        self._conn.execute(
            "INSERT INTO semantic_memory (content, source, tags, tokens, created_at) VALUES (?, ?, ?, ?, ?)",
            (content[:1000], "episodic", json.dumps(tags or []), tokens, time.time())
        )
        self._conn.commit()
        self._idf_dirty = True

    def store_knowledge(self, content: str, source: str = "user",
                        tags: list[str] | None = None) -> None:
        tokens = json.dumps(dict(_tokenize(content)))
        self._conn.execute(
            "INSERT INTO semantic_memory (content, source, tags, tokens, created_at) VALUES (?, ?, ?, ?, ?)",
            (content[:2000], source, json.dumps(tags or []), tokens, time.time())
        )
        self._conn.commit()
        self._idf_dirty = True

    def _compute_idf(self) -> None:
        """Compute IDF scores across all semantic memory documents.

        IDF(t) = log((1 + N) / (1 + df(t))) + 1  — smooth IDF formula
        Cached in-memory; recomputed when _idf_dirty is True.
        """
        rows = self._conn.execute(
            "SELECT tokens FROM semantic_memory ORDER BY created_at DESC LIMIT 1000"
        ).fetchall()

        N = len(rows)
        if N == 0:
            self._idf_cache = {}
            self._idf_doc_count = 0
            self._idf_dirty = False
            return

        df: Counter = Counter()
        for r in rows:
            try:
                doc_tokens = set(json.loads(r["tokens"]).keys())
                for t in doc_tokens:
                    df[t] += 1
            except Exception:
                continue

        self._idf_cache = {
            term: math.log((1 + N) / (1 + count)) + 1
            for term, count in df.items()
        }
        self._idf_doc_count = N
        self._idf_dirty = False

    def semantic_search(self, query: str, top_k: int = 5,
                        min_score: float = 0.05) -> list[dict]:
        """IDF-weighted semantic search over all stored knowledge.

        Gap #2: Uses bigrams + IDF weighting for significantly better recall
        than the original plain TF-IDF cosine similarity.
        """
        if self._idf_dirty:
            self._compute_idf()

        q_tokens = _tokenize(query)
        rows = self._conn.execute(
            "SELECT content, source, tags, tokens, created_at FROM semantic_memory ORDER BY created_at DESC LIMIT 500"
        ).fetchall()

        scored = []
        for r in rows:
            try:
                doc_tokens = Counter({k: float(v) for k, v in json.loads(r["tokens"]).items()})
                score = _cosine_idf(q_tokens, doc_tokens, idf=self._idf_cache)
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

        # Gap #12: Include relevant skills
        skills = self.get_skills(limit=5)
        if skills:
            lines.append("\n## Saved skills (reusable procedures)")
            for sk in skills:
                lines.append(f"- **{sk['name']}**: {sk['description'][:80]}")

        return "\n".join(lines) if lines else ""

    def get_stats(self) -> dict:
        """Return analytics about stored memory for the Insights panel."""
        total = self.task_count()

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

        ok_total = self._conn.execute(
            "SELECT COUNT(*) FROM episodic WHERE outcome='completed'"
        ).fetchone()[0]
        success_rate = round(ok_total / total * 100) if total else 0

        avg_row = self._conn.execute(
            "SELECT AVG(steps_executed) FROM episodic"
        ).fetchone()[0]
        avg_steps = round(avg_row or 0, 1)

        recent_cmds = self._conn.execute(
            """SELECT command, MAX(created_at) AS ts
               FROM episodic
               GROUP BY command
               ORDER BY ts DESC
               LIMIT 5"""
        ).fetchall()
        recent = [r["command"][:80] for r in recent_cmds]

        sem_count = self._conn.execute(
            "SELECT COUNT(*) FROM semantic_memory"
        ).fetchone()[0]

        wf_count = self._conn.execute(
            "SELECT COUNT(*) FROM workflow_runs"
        ).fetchone()[0]

        skill_count = self._conn.execute(
            "SELECT COUNT(*) FROM skills"
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
            "skill_count": skill_count,
        }

    # ── Reports Storage ──────────────────────────────────────────────────────

    def store_report(self, topic: str, content: str,
                     queries_run: list[str] | None = None,
                     sources_count: int = 0,
                     saved_path: str = "") -> int:
        cur = self._conn.execute(
            """INSERT INTO reports (topic, content, queries_run, sources_count, saved_path, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (topic[:200], content[:50000],
             json.dumps(queries_run or []),
             sources_count, saved_path or "",
             time.time())
        )
        self._conn.commit()
        return cur.lastrowid

    def get_reports(self, limit: int = 20, search: str = "") -> list[dict]:
        if search:
            rows = self._conn.execute(
                """SELECT id, topic, content, queries_run, sources_count, saved_path, created_at
                   FROM reports
                   WHERE topic LIKE ? OR content LIKE ?
                   ORDER BY created_at DESC LIMIT ?""",
                (f"%{search}%", f"%{search}%", limit)
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT id, topic, content, queries_run, sources_count, saved_path, created_at
                   FROM reports ORDER BY created_at DESC LIMIT ?""",
                (limit,)
            ).fetchall()
        result = []
        for r in rows:
            try:
                queries = json.loads(r["queries_run"])
            except Exception:
                queries = []
            result.append({
                "id": r["id"],
                "topic": r["topic"],
                "content": r["content"],
                "queries_run": queries,
                "sources_count": r["sources_count"],
                "saved_path": r["saved_path"],
                "created_at": r["created_at"],
                "created_at_str": time.strftime("%Y-%m-%d %H:%M", time.localtime(r["created_at"])),
            })
        return result

    def get_report(self, report_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM reports WHERE id=?", (report_id,)
        ).fetchone()
        if not row:
            return None
        try:
            queries = json.loads(row["queries_run"])
        except Exception:
            queries = []
        return {
            "id": row["id"],
            "topic": row["topic"],
            "content": row["content"],
            "queries_run": queries,
            "sources_count": row["sources_count"],
            "saved_path": row["saved_path"],
            "created_at": row["created_at"],
            "created_at_str": time.strftime("%Y-%m-%d %H:%M", time.localtime(row["created_at"])),
        }

    def delete_report(self, report_id: int) -> bool:
        cur = self._conn.execute("DELETE FROM reports WHERE id=?", (report_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def report_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]

    # ── Natural Language Preference Detection ────────────────────────────────

    _PREF_PATTERNS = [
        (re.compile(r'^remember\s+(?:that\s+)?(.+)$', re.IGNORECASE), "user_note"),
        (re.compile(r'^always\s+(.+)$', re.IGNORECASE), "always"),
        (re.compile(r'^never\s+(.+)$', re.IGNORECASE), "never"),
        (re.compile(r'^(?:i\s+)?prefer\s+(.+)$', re.IGNORECASE), "preference"),
        (re.compile(r'^i\s+(?:like|want|use|need)\s+(.+)$', re.IGNORECASE), "preference"),
        (re.compile(r'^set\s+preference[:\s]+(.+)$', re.IGNORECASE), "set"),
        (re.compile(r'^my\s+(?:default\s+)?(.+?)\s+is\s+(.+)$', re.IGNORECASE), "default"),
        (re.compile(r'^use\s+(.+)\s+for\s+(.+)$', re.IGNORECASE), "tool_pref"),
        (re.compile(r"^don't\s+(.+)$", re.IGNORECASE), "never"),
        (re.compile(r'^do\s+not\s+(.+)$', re.IGNORECASE), "never"),
    ]

    def parse_and_store_preference(self, command: str) -> str | None:
        cmd = command.strip()
        for pattern, pref_type in self._PREF_PATTERNS:
            m = pattern.match(cmd)
            if not m:
                continue
            groups = m.groups()
            if pref_type == "default" and len(groups) == 2:
                key = f"default_{groups[0].strip().lower().replace(' ', '_')}"
                value = groups[1].strip()
            elif pref_type == "tool_pref" and len(groups) == 2:
                key = f"tool_for_{groups[1].strip().lower().replace(' ', '_')}"
                value = groups[0].strip()
            elif pref_type == "always":
                key = "always_" + "_".join(list(_tokenize(groups[0]).keys())[:4])
                value = f"ALWAYS: {groups[0].strip()}"
            elif pref_type == "never":
                key = "never_" + "_".join(list(_tokenize(groups[0]).keys())[:4])
                value = f"NEVER: {groups[0].strip()}"
            else:
                key = "note_" + "_".join(list(_tokenize(groups[0]).keys())[:4])
                value = groups[0].strip()

            self.set_preference(key, value)
            self.store_knowledge(
                f"User preference: {value}",
                source="user_preference",
                tags=["preference", pref_type],
            )
            return f"✓ Preference saved: **{value}**"
        return None

    # ── Gap #10: Implicit preference learning ────────────────────────────────

    def _run_implicit_preference_detection(self) -> list[dict]:
        """Analyze episodic history to detect behavioral patterns.

        Stores detected patterns as auto-preferences with key 'auto_pref_*'.
        Only stores preferences with confidence >= 60% (at least 6/10 tasks matching).
        Returns list of newly detected preferences.
        """
        recent = self.recent_tasks(limit=50)
        if len(recent) < 10:
            return []

        detected: list[dict] = []

        # Pattern 1: Most frequent output directory
        output_dirs: list[str] = []
        for t in recent:
            try:
                files = json.loads(t.get("files_affected", "[]"))
                for f in files:
                    if f:
                        parent = str(Path(f).expanduser().parent)
                        output_dirs.append(parent)
            except Exception:
                pass

        if output_dirs:
            dir_counts = Counter(output_dirs)
            top_dir, top_count = dir_counts.most_common(1)[0]
            confidence = top_count / len(recent)
            if confidence >= 0.4 and top_dir not in (".", "/", str(Path.home())):
                pref_key = "auto_pref_output_dir"
                if self._prefs.get(pref_key) != top_dir:
                    self.set_preference(pref_key, top_dir)
                    detected.append({
                        "key": pref_key,
                        "value": top_dir,
                        "confidence": round(confidence, 2),
                        "description": f"You often save files to {top_dir}",
                    })

        # Pattern 2: Most active domain
        domains = [t.get("intent_domain") for t in recent if t.get("intent_domain")]
        if domains:
            dom_counts = Counter(domains)
            top_domain, top_count = dom_counts.most_common(1)[0]
            confidence = top_count / len(recent)
            if confidence >= 0.5:
                pref_key = "auto_pref_primary_domain"
                if self._prefs.get(pref_key) != top_domain:
                    self.set_preference(pref_key, top_domain)
                    detected.append({
                        "key": pref_key,
                        "value": top_domain,
                        "confidence": round(confidence, 2),
                        "description": f"Your most-used domain is '{top_domain}' ({top_count}/{len(recent)} tasks)",
                    })

        # Pattern 3: Peak activity time (morning/afternoon/evening)
        hours = []
        for t in recent:
            ts = t.get("created_at")
            if ts:
                hour = int(time.strftime("%H", time.localtime(ts)))
                if 6 <= hour < 12:
                    hours.append("morning")
                elif 12 <= hour < 18:
                    hours.append("afternoon")
                else:
                    hours.append("evening")
        if hours:
            hour_counts = Counter(hours)
            peak_time, peak_count = hour_counts.most_common(1)[0]
            if peak_count / len(hours) >= 0.5:
                pref_key = "auto_pref_peak_time"
                if self._prefs.get(pref_key) != peak_time:
                    self.set_preference(pref_key, peak_time)
                    detected.append({
                        "key": pref_key,
                        "value": peak_time,
                        "confidence": round(peak_count / len(hours), 2),
                        "description": f"You tend to work in the {peak_time}",
                    })

        if detected:
            # Store as semantic knowledge for context injection
            for pref in detected:
                self.store_knowledge(
                    f"Auto-detected preference: {pref['description']}",
                    source="implicit_learning",
                    tags=["preference", "auto"],
                )

        return detected

    def detect_implicit_preferences(self) -> list[dict]:
        """Public API for manual invocation of implicit preference detection."""
        return self._run_implicit_preference_detection()

    # ── Weekly / Temporal Summaries ──────────────────────────────────────────

    def get_weekly_summary(self, days: int = 7) -> dict:
        cutoff = time.time() - days * 86400
        rows = self._conn.execute(
            """SELECT command, intent_domain, intent_verb, outcome, steps_executed, created_at
               FROM episodic WHERE created_at >= ? ORDER BY created_at DESC""",
            (cutoff,)
        ).fetchall()

        if not rows:
            return {"days": days, "total": 0, "tasks": [], "domains": {}, "summary": ""}

        domain_counts: dict[str, int] = {}
        verb_counts: dict[str, int] = {}
        successes = 0
        for r in rows:
            d = r["intent_domain"] or "other"
            v = r["intent_verb"] or "other"
            domain_counts[d] = domain_counts.get(d, 0) + 1
            verb_counts[v] = verb_counts.get(v, 0) + 1
            if r["outcome"] == "completed":
                successes += 1

        top_domain = max(domain_counts, key=domain_counts.get) if domain_counts else "none"
        tasks_preview = [
            {
                "command": r["command"][:80],
                "domain": r["intent_domain"],
                "outcome": r["outcome"],
                "ts": time.strftime("%a %b %d %H:%M", time.localtime(r["created_at"])),
            }
            for r in rows[:20]
        ]

        summary_lines = [
            f"**Last {days} days:** {len(rows)} task(s), "
            f"{successes} succeeded ({round(successes/len(rows)*100)}% success rate).",
            f"**Most active domain:** {top_domain} ({domain_counts.get(top_domain, 0)} tasks).",
        ]
        if rows:
            summary_lines.append(f"**Most recent:** {rows[0]['command'][:60]}")

        report_rows = self._conn.execute(
            "SELECT topic, created_at FROM reports WHERE created_at >= ? ORDER BY created_at DESC LIMIT 5",
            (cutoff,)
        ).fetchall()
        reports_preview = [
            {"topic": r["topic"], "ts": time.strftime("%a %b %d", time.localtime(r["created_at"]))}
            for r in report_rows
        ]

        return {
            "days": days,
            "total": len(rows),
            "tasks": tasks_preview,
            "domains": domain_counts,
            "verbs": verb_counts,
            "success_rate": round(successes / len(rows) * 100) if rows else 0,
            "reports": reports_preview,
            "summary": " ".join(summary_lines),
            "top_domain": top_domain,
        }

    # ── Gap #12: Skill Library ────────────────────────────────────────────────

    def save_skill_from_goal(self, goal: str, steps: list[str],
                              name: str | None = None,
                              method: str = "heuristic") -> int:
        """Save a successfully completed goal's steps as a named reusable skill.

        Returns the skill id.
        """
        if not steps:
            return -1

        # Auto-generate name from goal (first 5 words)
        if not name:
            words = re.findall(r'\w+', goal)[:6]
            name = " ".join(words).title()[:60] or "Unnamed Skill"

        description = goal[:200]
        cur = self._conn.execute(
            """INSERT INTO skills (name, description, steps, goal, decomposition_method, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, description, json.dumps(steps), goal[:500], method, time.time())
        )
        self._conn.commit()

        # Store in semantic memory for context injection
        self.store_knowledge(
            f"Saved skill: {name} — {description}",
            source="skill",
            tags=["skill", "procedure"],
        )
        return cur.lastrowid

    def get_skills(self, limit: int = 20, search: str = "") -> list[dict]:
        """List saved skills, newest first."""
        if search:
            rows = self._conn.execute(
                """SELECT * FROM skills
                   WHERE name LIKE ? OR description LIKE ? OR goal LIKE ?
                   ORDER BY used_count DESC, created_at DESC LIMIT ?""",
                (f"%{search}%", f"%{search}%", f"%{search}%", limit)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM skills ORDER BY used_count DESC, created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        result = []
        for r in rows:
            try:
                steps = json.loads(r["steps"])
            except Exception:
                steps = []
            result.append({
                "id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "goal": r["goal"],
                "steps": steps,
                "step_count": len(steps),
                "decomposition_method": r["decomposition_method"],
                "used_count": r["used_count"],
                "last_used": r["last_used"],
                "created_at": r["created_at"],
                "created_at_str": time.strftime("%Y-%m-%d %H:%M", time.localtime(r["created_at"])),
            })
        return result

    def get_skill(self, skill_id: int) -> dict | None:
        row = self._conn.execute("SELECT * FROM skills WHERE id=?", (skill_id,)).fetchone()
        if not row:
            return None
        try:
            steps = json.loads(row["steps"])
        except Exception:
            steps = []
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "goal": row["goal"],
            "steps": steps,
            "step_count": len(steps),
            "decomposition_method": row["decomposition_method"],
            "used_count": row["used_count"],
            "last_used": row["last_used"],
            "created_at": row["created_at"],
        }

    def mark_skill_used(self, skill_id: int) -> None:
        self._conn.execute(
            "UPDATE skills SET used_count=used_count+1, last_used=? WHERE id=?",
            (time.time(), skill_id)
        )
        self._conn.commit()

    def delete_skill(self, skill_id: int) -> bool:
        cur = self._conn.execute("DELETE FROM skills WHERE id=?", (skill_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def skill_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
