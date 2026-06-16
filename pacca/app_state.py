"""Shared application singletons.

All FastAPI routers import from here so state is never duplicated across modules.
Lazy-initialised objects (agent, workflow manager) are created on first access.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from pacca.config import PACCAConfig
from pacca.personal import ReminderManager, TodoManager
from pacca.personal.profile import UserProfile
from pacca.personal.notes import NotesManager
from pacca.personal.projects import ProjectsManager
from pacca.intelligence.notifications import NotificationManager

if TYPE_CHECKING:
    from pacca.agent import PACCAAgent
    from pacca.workflows.workflow_manager import WorkflowManager

# ── Eagerly-initialised singletons ───────────────────────────────────────────
reminders: ReminderManager = ReminderManager()
todos: TodoManager = TodoManager()
profile: UserProfile = UserProfile.load()
notes: NotesManager = NotesManager()
projects: ProjectsManager = ProjectsManager()
notifications: NotificationManager = NotificationManager()

# ── Lazily-initialised singletons ────────────────────────────────────────────
_agent: PACCAAgent | None = None
_config: PACCAConfig | None = None
_workflow_manager: WorkflowManager | None = None


def get_agent() -> "PACCAAgent":
    """Return (or create) the singleton PACCAAgent."""
    global _agent, _config
    if _agent is None:
        _config = PACCAConfig.load()
        from pacca.agent import PACCAAgent  # avoid circular import at module level
        _agent = PACCAAgent(config=_config)
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
