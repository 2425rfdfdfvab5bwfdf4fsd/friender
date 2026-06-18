"""ToolCache — short-TTL cache for read-only tool results.

Prevents redundant filesystem, system, git, and integration API calls when
the same tool is invoked multiple times within a short window — e.g. the LLM
calls list_directory twice in one task, or the user re-runs the same command.

Only idempotent, read-only tools are cached. Write/mutating tools
(create_file, move_file, git_commit, etc.) are intentionally excluded.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any


# tool_name → TTL in seconds
_CACHEABLE: dict[str, float] = {
    # Filesystem reads
    "list_directory":           30.0,
    "search_files":             30.0,
    "read_file":                20.0,
    # System / process
    "system_monitor":           10.0,
    "list_running_apps":        20.0,
    "find_installed_apps":     120.0,
    "list_available_web_apps": 600.0,
    # Git reads
    "git_status":               15.0,
    "git_diff":                 15.0,
    # Google services reads
    "list_calendar_events":     60.0,
    "drive_list_files":         60.0,
    "drive_search_files":       60.0,
    # Integration reads
    "slack_list_channels":     120.0,
    "trello_list_boards":      120.0,
    "trello_get_lists":         60.0,
    "spotify_current_track":    10.0,
    "youtube_search":          300.0,
    "gmail_list_emails":        30.0,
}

_store: dict[str, tuple[Any, float]] = {}
_hits: int = 0
_misses: int = 0


def get(tool: str, args: dict) -> Any | None:
    """Return cached result for (tool, args), or None if absent / expired."""
    global _hits, _misses
    if tool not in _CACHEABLE:
        _misses += 1
        return None
    key = _make_key(tool, args)
    entry = _store.get(key)
    if entry is None:
        _misses += 1
        return None
    value, expires_at = entry
    if time.monotonic() > expires_at:
        del _store[key]
        _misses += 1
        return None
    _hits += 1
    return value


def put(tool: str, args: dict, result: Any) -> None:
    """Cache a successful tool result. Silently skips errors and non-cacheable tools."""
    if tool not in _CACHEABLE:
        return
    if isinstance(result, dict) and "error" in result:
        return
    _store[_make_key(tool, args)] = (result, time.monotonic() + _CACHEABLE[tool])


def invalidate(tool: str | None = None) -> None:
    """Clear cache — all tools, or just the given tool name."""
    if tool is None:
        _store.clear()
        return
    prefix = f"{tool}:"
    for k in [k for k in _store if k.startswith(prefix)]:
        del _store[k]


def stats() -> dict:
    total = _hits + _misses
    return {
        "hits":     _hits,
        "misses":   _misses,
        "hit_rate": round(_hits / total, 3) if total else 0.0,
        "size":     len(_store),
        "cached_tools": list(_CACHEABLE.keys()),
    }


def _make_key(tool: str, args: dict) -> str:
    clean = {k: v for k, v in args.items() if not k.startswith("_")}
    payload = f"{tool}:" + json.dumps(clean, sort_keys=True, default=str)
    return hashlib.md5(payload.encode()).hexdigest()
