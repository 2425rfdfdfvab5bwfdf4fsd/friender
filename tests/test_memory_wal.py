"""Tests for MemoryManager WAL mode (REL-01)."""
import pytest
from arix.memory.memory_manager import MemoryManager


def test_wal_mode_enabled():
    """SQLite connection should be in WAL journal mode."""
    mm = MemoryManager()
    row = mm._conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0].lower() == "wal", f"Expected WAL mode, got {row[0]!r}"


def test_memory_manager_task_count():
    """task_count() should return an integer >= 0."""
    mm = MemoryManager()
    count = mm.task_count()
    assert isinstance(count, int)
    assert count >= 0
