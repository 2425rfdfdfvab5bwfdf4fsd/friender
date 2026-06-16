"""Shared application singletons.

All FastAPI routers import from here so state is never duplicated across modules.
Lazy-initialised objects (agent, workflow manager) are created on first access.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from arix.config import ArixConfig
from arix.personal import ReminderManager, TodoManager
from arix.personal.profile import UserProfile
from arix.personal.notes import NotesManager
from arix.personal.projects import ProjectsManager
from arix.intelligence.notifications import NotificationManager

if TYPE_CHECKING:
    from arix.agent import ArixAgent
    from arix.workflows.workflow_manager import WorkflowManager

# ── Eagerly-initialised singletons ───────────────────────────────────────────
reminders: ReminderManager = ReminderManager()
todos: TodoManager = TodoManager()
profile: UserProfile = UserProfile.load()
notes: NotesManager = NotesManager()
projects: ProjectsManager = ProjectsManager()
notifications: NotificationManager = NotificationManager()

# ── Lazily-initialised singletons ────────────────────────────────────────────
_agent: ArixAgent | None = None
_config: ArixConfig | None = None
_workflow_manager: WorkflowManager | None = None


def get_agent() -> "ArixAgent":
    """Return (or create) the singleton ArixAgent."""
    global _agent, _config
    if _agent is None:
        _config = ArixConfig.load()
        from arix.agent import ArixAgent  # avoid circular import at module level
        _agent = ArixAgent(config=_config)
    return _agent


def get_workflow_manager() -> "WorkflowManager | None":
    return _workflow_manager


def set_workflow_manager(wm: "WorkflowManager") -> None:
    global _workflow_manager
    _workflow_manager = wm


def reset_agent() -> None:
    """Force the agent to reinitialise on next request (e.g. after settings change)."""
    global _agent, _config
    _agent = None
    _config = None
