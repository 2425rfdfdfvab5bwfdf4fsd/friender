"""TaskStateMachine — manages task lifecycle state transitions."""
from __future__ import annotations
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Callable, Any


class TaskState(str, Enum):
    PLANNED = "planned"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING = "executing"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    FAILED = "failed"
    COMPLETED = "completed"


VALID_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.PLANNED: {TaskState.AWAITING_CONFIRMATION, TaskState.EXECUTING, TaskState.CANCELLED},
    TaskState.AWAITING_CONFIRMATION: {TaskState.EXECUTING, TaskState.CANCELLED},
    TaskState.EXECUTING: {TaskState.PAUSED, TaskState.CANCELLED, TaskState.FAILED, TaskState.COMPLETED},
    TaskState.PAUSED: {TaskState.EXECUTING, TaskState.CANCELLED},
    TaskState.CANCELLED: set(),
    TaskState.FAILED: set(),
    TaskState.COMPLETED: set(),
}


@dataclass
class TaskExecution:
    task_id: str
    state: TaskState = TaskState.PLANNED
    current_step: int = 0
    total_steps: int = 0
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    error: str | None = None
    result_summary: str | None = None
    files_affected: list[str] = field(default_factory=list)
    egress_events: int = 0
    cancelled: bool = False


class TaskStateMachine:
    def __init__(self, on_transition: Callable[[str, TaskState, TaskState], None] | None = None):
        self._tasks: dict[str, TaskExecution] = {}
        self._on_transition = on_transition

    def create(self, task_id: str, total_steps: int) -> TaskExecution:
        task = TaskExecution(task_id=task_id, total_steps=total_steps)
        self._tasks[task_id] = task
        return task

    def get(self, task_id: str) -> TaskExecution | None:
        return self._tasks.get(task_id)

    def transition(self, task_id: str, new_state: TaskState,
                   error: str | None = None) -> TaskExecution:
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Unknown task: {task_id}")

        old_state = task.state
        allowed = VALID_TRANSITIONS.get(old_state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Invalid transition: {old_state} → {new_state} for task {task_id}"
            )

        task.state = new_state
        if error:
            task.error = error
        if new_state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
            task.end_time = time.time()

        if self._on_transition:
            self._on_transition(task_id, old_state, new_state)

        return task

    def cancel(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task and task.state in (TaskState.PLANNED, TaskState.AWAITING_CONFIRMATION,
                                    TaskState.EXECUTING, TaskState.PAUSED):
            task.cancelled = True
            try:
                self.transition(task_id, TaskState.CANCELLED)
            except ValueError:
                pass

    def is_cancelled(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        return bool(task and task.cancelled)
