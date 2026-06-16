"""UndoManager — tracks reversible operations and executes undo actions."""
from __future__ import annotations
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class UndoRecord:
    task_id: str
    step_id: str
    tool_name: str
    description: str
    recorded_at: float
    undo_fn: Callable[[], dict]
    undo_description: str
    expired: bool = False


class UndoManager:
    """
    Tracks reversible operations during task execution.
    Supports 'undo last' to reverse the most recent reversible step.
    Stack is cleared on process restart (in-memory only).
    """

    def __init__(self, max_depth: int = 50):
        self._stack: list[UndoRecord] = []
        self._max_depth = max_depth

    def record(self, task_id: str, step_id: str, tool_name: str,
               description: str, undo_fn: Callable, undo_description: str) -> None:
        record = UndoRecord(
            task_id=task_id,
            step_id=step_id,
            tool_name=tool_name,
            description=description,
            recorded_at=time.time(),
            undo_fn=undo_fn,
            undo_description=undo_description,
        )
        self._stack.append(record)
        if len(self._stack) > self._max_depth:
            self._stack.pop(0)

    def can_undo(self) -> bool:
        return any(not r.expired for r in reversed(self._stack))

    def peek(self) -> UndoRecord | None:
        for r in reversed(self._stack):
            if not r.expired:
                return r
        return None

    def undo_last(self) -> dict:
        record = self.peek()
        if not record:
            return {"error": "Nothing to undo"}
        record.expired = True
        try:
            result = record.undo_fn()
            return {
                "undone": record.description,
                "action": record.undo_description,
                "result": result,
            }
        except Exception as e:
            record.expired = False
            return {"error": f"Undo failed: {e}"}

    def history(self, n: int = 10) -> list[dict]:
        items = []
        for r in reversed(self._stack[-n:]):
            items.append({
                "tool": r.tool_name,
                "description": r.description,
                "recorded_at": r.recorded_at,
                "expired": r.expired,
                "undo_description": r.undo_description,
            })
        return items

    def clear(self) -> None:
        self._stack.clear()


def make_move_undo(src_final: str, src_original: str) -> Callable:
    """Returns an undo function that moves a file back to its original location."""
    def undo() -> dict:
        if not os.path.exists(src_final):
            return {"error": f"Cannot undo: file no longer at {src_final}"}
        Path(src_original).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(src_final, src_original)
        return {"moved_back": src_original}
    return undo


def make_create_undo(created_path: str) -> Callable:
    """Returns an undo function that deletes a created file."""
    def undo() -> dict:
        p = Path(created_path)
        if not p.exists():
            return {"error": f"File no longer exists: {created_path}"}
        p.unlink()
        return {"deleted": created_path}
    return undo


def make_create_folder_undo(created_path: str) -> Callable:
    """Returns an undo function that removes an empty created folder."""
    def undo() -> dict:
        p = Path(created_path)
        if not p.exists():
            return {"error": f"Folder no longer exists: {created_path}"}
        try:
            p.rmdir()
            return {"removed_folder": created_path}
        except OSError as e:
            return {"error": f"Cannot undo — folder not empty: {e}"}
    return undo
