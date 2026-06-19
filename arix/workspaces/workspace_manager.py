"""Agent Workspaces — OpenFang + Moxxy style per-agent isolated work directories.

Each agent task gets its own isolated workspace at ~/arix-workspaces/{workspace_id}/
with a private journal, artifact directory, and lifecycle management.
The workspace is scoped to a single task session and cleaned up after a TTL.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

_BASE_DIR = Path.home() / "arix-workspaces"
_STATE_FILE = Path.home() / ".arix" / "workspaces_state.json"
_DEFAULT_TTL_HOURS = 48


@dataclass
class Workspace:
    workspace_id: str
    agent_role: str          # "researcher" | "coder" | "ops" | "planner" | "hand:<id>"
    task_summary: str
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)
    ttl_hours: int = _DEFAULT_TTL_HOURS
    status: str = "active"   # "active" | "idle" | "archived"
    artifact_count: int = 0
    journal_lines: int = 0

    @property
    def path(self) -> Path:
        return _BASE_DIR / self.workspace_id

    @property
    def journal_path(self) -> Path:
        return self.path / "journal.md"

    @property
    def artifacts_path(self) -> Path:
        return self.path / "artifacts"

    def is_expired(self) -> bool:
        age_hours = (time.time() - self.last_active_at) / 3600
        return age_hours > self.ttl_hours

    def to_dict(self) -> dict:
        artifacts = []
        if self.artifacts_path.exists():
            for f in sorted(self.artifacts_path.iterdir()):
                if f.is_file():
                    artifacts.append({
                        "name": f.name,
                        "size": f.stat().st_size,
                        "modified_at": f.stat().st_mtime,
                    })
        journal_preview = ""
        if self.journal_path.exists():
            lines = self.journal_path.read_text(errors="replace").splitlines()
            journal_preview = "\n".join(lines[-20:])  # last 20 lines

        return {
            "workspace_id": self.workspace_id,
            "agent_role": self.agent_role,
            "task_summary": self.task_summary,
            "created_at": self.created_at,
            "last_active_at": self.last_active_at,
            "ttl_hours": self.ttl_hours,
            "status": self.status,
            "path": str(self.path),
            "artifact_count": len(artifacts),
            "artifacts": artifacts[:20],
            "journal_lines": self.journal_lines,
            "journal_preview": journal_preview,
            "expired": self.is_expired(),
        }


class WorkspaceManager:
    """Manages per-agent isolated workspaces — create, journal, archive, gc."""

    def __init__(self) -> None:
        self._workspaces: Dict[str, Workspace] = {}
        _BASE_DIR.mkdir(parents=True, exist_ok=True)
        self._load_state()

    def _load_state(self) -> None:
        try:
            if _STATE_FILE.exists():
                data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
                for wid, wd in data.get("workspaces", {}).items():
                    ws = Workspace(
                        workspace_id=wd["workspace_id"],
                        agent_role=wd.get("agent_role", "general"),
                        task_summary=wd.get("task_summary", ""),
                        created_at=wd.get("created_at", time.time()),
                        last_active_at=wd.get("last_active_at", time.time()),
                        ttl_hours=wd.get("ttl_hours", _DEFAULT_TTL_HOURS),
                        status=wd.get("status", "active"),
                    )
                    if ws.path.exists():
                        self._workspaces[wid] = ws
        except Exception as e:
            log.debug("Workspace state load error: %s", e)

    def _save_state(self) -> None:
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {"workspaces": {
                wid: {
                    "workspace_id": ws.workspace_id,
                    "agent_role": ws.agent_role,
                    "task_summary": ws.task_summary,
                    "created_at": ws.created_at,
                    "last_active_at": ws.last_active_at,
                    "ttl_hours": ws.ttl_hours,
                    "status": ws.status,
                }
                for wid, ws in self._workspaces.items()
            }}
            _STATE_FILE.write_text(json.dumps(data, indent=2))
        except Exception as e:
            log.debug("Workspace state save error: %s", e)

    def create(
        self,
        agent_role: str = "general",
        task_summary: str = "",
        ttl_hours: int = _DEFAULT_TTL_HOURS,
    ) -> Workspace:
        wid = str(uuid.uuid4())[:12]
        ws = Workspace(
            workspace_id=wid,
            agent_role=agent_role,
            task_summary=task_summary[:120],
            ttl_hours=ttl_hours,
        )
        ws.path.mkdir(parents=True, exist_ok=True)
        ws.artifacts_path.mkdir(exist_ok=True)

        # Write initial journal header
        ws.journal_path.write_text(
            f"# Workspace Journal\n"
            f"**Agent:** {agent_role}  \n"
            f"**Task:** {task_summary[:80]}  \n"
            f"**Created:** {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}  \n\n"
            f"---\n\n"
        )
        self._workspaces[wid] = ws
        self._save_state()
        log.info("Workspace created: %s (%s)", wid, agent_role)
        return ws

    def append_journal(self, workspace_id: str, entry: str) -> bool:
        ws = self._workspaces.get(workspace_id)
        if not ws:
            return False
        try:
            timestamp = time.strftime("%H:%M:%S", time.gmtime())
            line = f"**{timestamp}** — {entry.strip()}\n\n"
            with open(ws.journal_path, "a") as f:
                f.write(line)
            ws.last_active_at = time.time()
            ws.journal_lines += 1
            self._save_state()
            return True
        except Exception as e:
            log.debug("Journal append error: %s", e)
            return False

    def save_artifact(
        self,
        workspace_id: str,
        filename: str,
        content: str,
    ) -> Optional[str]:
        ws = self._workspaces.get(workspace_id)
        if not ws:
            return None
        try:
            # Sanitize filename
            safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ")
            safe_name = safe_name.strip() or f"artifact_{int(time.time())}.txt"
            dest = ws.artifacts_path / safe_name
            dest.write_text(content)
            ws.last_active_at = time.time()
            ws.artifact_count += 1
            self._save_state()
            return str(dest)
        except Exception as e:
            log.debug("Artifact save error: %s", e)
            return None

    def archive(self, workspace_id: str) -> bool:
        ws = self._workspaces.get(workspace_id)
        if not ws:
            return False
        ws.status = "archived"
        self._save_state()
        return True

    def delete(self, workspace_id: str) -> bool:
        ws = self._workspaces.get(workspace_id)
        if not ws:
            return False
        try:
            if ws.path.exists():
                shutil.rmtree(ws.path)
            del self._workspaces[workspace_id]
            self._save_state()
            return True
        except Exception as e:
            log.debug("Workspace delete error: %s", e)
            return False

    def garbage_collect(self) -> int:
        """Delete all expired workspaces. Returns count deleted."""
        expired = [wid for wid, ws in self._workspaces.items() if ws.is_expired()]
        for wid in expired:
            self.delete(wid)
        log.info("Workspace GC: removed %d expired workspaces", len(expired))
        return len(expired)

    def list_workspaces(
        self,
        status: Optional[str] = None,
        agent_role: Optional[str] = None,
        limit: int = 50,
    ) -> List[dict]:
        items = list(self._workspaces.values())
        if status:
            items = [w for w in items if w.status == status]
        if agent_role:
            items = [w for w in items if w.agent_role == agent_role]
        items.sort(key=lambda w: -w.last_active_at)
        return [w.to_dict() for w in items[:limit]]

    def get(self, workspace_id: str) -> Optional[dict]:
        ws = self._workspaces.get(workspace_id)
        return ws.to_dict() if ws else None

    def stats(self) -> dict:
        total = len(self._workspaces)
        active = sum(1 for w in self._workspaces.values() if w.status == "active")
        archived = sum(1 for w in self._workspaces.values() if w.status == "archived")
        expired = sum(1 for w in self._workspaces.values() if w.is_expired())
        total_artifacts = sum(
            len(list(w.artifacts_path.iterdir()))
            for w in self._workspaces.values()
            if w.artifacts_path.exists()
        )
        return {
            "total": total,
            "active": active,
            "archived": archived,
            "expired": expired,
            "total_artifacts": total_artifacts,
            "base_dir": str(_BASE_DIR),
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

_manager: Optional[WorkspaceManager] = None


def get_workspace_manager() -> WorkspaceManager:
    global _manager
    if _manager is None:
        _manager = WorkspaceManager()
    return _manager
