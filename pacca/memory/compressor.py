"""MemoryCompressor — thin façade over MemoryManager.compress_old_sessions().

Groups episodic records older than a given threshold into compact semantic
summaries, then deletes the originals to keep the database lean.
"""
from __future__ import annotations

from typing import Callable, Optional


class MemoryCompressor:
    """Wraps the compression logic exposed by MemoryManager.

    Usage::

        from pacca.memory.memory_manager import MemoryManager
        from pacca.memory.compressor import MemoryCompressor

        mm = MemoryManager()
        compressor = MemoryCompressor(mm)
        result = compressor.compress(days=7)
        # {"compressed": 12, "groups": 4, "skipped": 0}
    """

    def __init__(self, memory_manager) -> None:
        self._mm = memory_manager

    def compress(
        self,
        days: int = 7,
        llm_summary_fn: Optional[Callable] = None,
    ) -> dict:
        """Summarize episodic records older than *days* into semantic memory.

        Args:
            days: Age threshold in days.  Records older than this are eligible.
            llm_summary_fn: Optional callable(text) -> str that produces a
                narrative summary.  Pass ``None`` to use deterministic templates.

        Returns:
            ``{"compressed": int, "groups": int, "skipped": int}``
        """
        return self._mm.compress_old_sessions(
            days=days,
            llm_summary_fn=llm_summary_fn,
        )
