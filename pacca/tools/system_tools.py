"""System tools — system_monitor, cleanup_temp_files."""
from __future__ import annotations
import os
import platform
import shutil
import time
from pathlib import Path

import psutil


def system_monitor(include_processes: bool = True,
                   top_n_processes: int = 10) -> dict:
    cpu_percent = psutil.cpu_percent(interval=0.5)
    cpu_count = psutil.cpu_count()
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    uptime_seconds = time.time() - psutil.boot_time()
    uptime_hours = uptime_seconds / 3600

    result = {
        "platform": platform.system(),
        "platform_version": platform.version()[:80],
        "cpu": {
            "percent": cpu_percent,
            "count": cpu_count,
        },
        "memory": {
            "total_mb": round(mem.total / 1024 / 1024),
            "available_mb": round(mem.available / 1024 / 1024),
            "used_percent": mem.percent,
        },
        "disk": {
            "total_gb": round(disk.total / 1024 / 1024 / 1024, 1),
            "free_gb": round(disk.free / 1024 / 1024 / 1024, 1),
            "used_percent": disk.percent,
        },
        "uptime_hours": round(uptime_hours, 1),
    }

    if include_processes:
        processes = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent",
                                          "memory_percent", "status"]):
            try:
                processes.append({
                    "pid": proc.info["pid"],
                    "name": proc.info["name"],
                    "cpu_percent": proc.info["cpu_percent"],
                    "memory_percent": round(proc.info["memory_percent"] or 0, 2),
                    "status": proc.info["status"],
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        processes.sort(key=lambda x: x.get("cpu_percent", 0) or 0, reverse=True)
        result["top_processes"] = processes[:top_n_processes]
        result["total_processes"] = len(processes)

    return result


# ── Temporary file cleanup ────────────────────────────────────────────────────

# Well-known temp directories per platform (safe to clean)
_TEMP_DIRS_LINUX = [
    "/tmp",
    str(Path.home() / ".cache"),
    str(Path.home() / ".local/share/Trash/files"),
]
_TEMP_DIRS_MAC = [
    "/tmp",
    str(Path.home() / "Library/Caches"),
    str(Path.home() / ".Trash"),
]
_TEMP_DIRS_WIN = [
    os.path.expandvars("%TEMP%"),
    os.path.expandvars("%TMP%"),
    os.path.expandvars(r"%LOCALAPPDATA%\Temp"),
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\INetCache"),
]

# File/directory name patterns that are always safe to delete
_ALWAYS_SAFE_PATTERNS = [
    "*.pyc", "*.pyo", "__pycache__", "*.tmp", "*.temp",
    "Thumbs.db", ".DS_Store", "desktop.ini",
    "*.log.1", "*.log.2", "*.bak",
]

# Browser cache subdirectories (excluded from normal scan; opt-in via include_browser_cache)
_BROWSER_CACHE_PATHS = [
    str(Path.home() / ".cache/google-chrome"),
    str(Path.home() / ".cache/chromium"),
    str(Path.home() / ".mozilla/firefox"),
    str(Path.home() / "Library/Caches/Google/Chrome"),
    str(Path.home() / "Library/Caches/Firefox"),
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\Cache"),
]

# Directories that are always protected even if found inside a temp path
_PROTECTED_NAMES = frozenset({
    "home", "root", "etc", "usr", "bin", "sbin", "lib",
    "Applications", "System", "Library", "Windows",
})


def _safe_size(path: Path) -> int:
    """Return file/dir size in bytes without raising."""
    try:
        if path.is_file():
            return path.stat().st_size
        total = 0
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
        return total
    except OSError:
        return 0


def _is_protected(path: Path) -> bool:
    """Return True if deleting this path would be dangerous."""
    parts = {p for p in path.parts}
    return bool(parts & _PROTECTED_NAMES)


def _scan_temp_dirs(
    dirs: list[str],
    max_age_days: int,
    dry_run: bool,
) -> tuple[list[dict], int, int]:
    """Scan dirs for old files, optionally deleting them.

    Returns (items_found, files_deleted, bytes_freed).
    """
    cutoff = time.time() - max_age_days * 86400
    found: list[dict] = []
    bytes_freed = 0
    files_deleted = 0

    for dir_str in dirs:
        base = Path(dir_str)
        if not base.exists() or not base.is_dir():
            continue
        if _is_protected(base):
            continue

        try:
            for item in base.iterdir():
                if _is_protected(item):
                    continue
                try:
                    mtime = item.stat().st_mtime
                except OSError:
                    continue
                if mtime > cutoff:
                    continue

                size = _safe_size(item)
                entry = {
                    "path": str(item),
                    "type": "file" if item.is_file() else "dir",
                    "size_kb": round(size / 1024, 1),
                    "age_days": round((time.time() - mtime) / 86400, 1),
                    "deleted": False,
                }

                if not dry_run:
                    try:
                        if item.is_file():
                            item.unlink()
                        else:
                            shutil.rmtree(str(item))
                        entry["deleted"] = True
                        bytes_freed += size
                        files_deleted += 1
                    except OSError as e:
                        entry["error"] = str(e)

                found.append(entry)
        except PermissionError:
            continue

    return found, files_deleted, bytes_freed


def _scan_pyc(base: Path, dry_run: bool) -> tuple[list[dict], int, int]:
    """Find and optionally remove .pyc files and __pycache__ dirs."""
    found: list[dict] = []
    bytes_freed = 0
    deleted = 0
    try:
        for cache_dir in base.rglob("__pycache__"):
            if not cache_dir.is_dir():
                continue
            size = _safe_size(cache_dir)
            entry = {"path": str(cache_dir), "type": "dir",
                     "size_kb": round(size / 1024, 1), "deleted": False}
            if not dry_run:
                try:
                    shutil.rmtree(str(cache_dir))
                    entry["deleted"] = True
                    bytes_freed += size
                    deleted += 1
                except OSError as e:
                    entry["error"] = str(e)
            found.append(entry)
    except (PermissionError, OSError):
        pass
    return found, deleted, bytes_freed


def cleanup_temp_files(
    dry_run: bool = False,
    max_age_days: int = 7,
    include_browser_cache: bool = False,
    include_pyc: bool = True,
    custom_paths: list[str] | None = None,
) -> dict:
    """Find and optionally remove temporary files to free disk space.

    Args:
        dry_run: If True, only report what would be deleted — nothing is removed.
        max_age_days: Only target files older than this many days (default 7).
        include_browser_cache: Also scan browser cache directories (slower).
        include_pyc: Remove Python __pycache__ dirs and .pyc files.
        custom_paths: Extra directories to scan in addition to system defaults.

    Returns a dict with:
        found: list of found items (path, size_kb, age_days, deleted)
        total_found: total item count
        total_deleted: items actually deleted (0 if dry_run)
        space_freed_mb: megabytes freed (0 if dry_run)
        dry_run: whether this was a preview-only scan
    """
    sys_platform = platform.system().lower()
    if sys_platform == "darwin":
        temp_dirs = _TEMP_DIRS_MAC.copy()
    elif sys_platform == "windows":
        temp_dirs = _TEMP_DIRS_WIN.copy()
    else:
        temp_dirs = _TEMP_DIRS_LINUX.copy()

    if include_browser_cache:
        temp_dirs.extend(_BROWSER_CACHE_PATHS)
    if custom_paths:
        temp_dirs.extend(custom_paths)

    all_found: list[dict] = []
    total_deleted = 0
    total_bytes = 0

    items, deleted, freed = _scan_temp_dirs(temp_dirs, max_age_days, dry_run)
    all_found.extend(items)
    total_deleted += deleted
    total_bytes += freed

    if include_pyc:
        pyc_items, pyc_deleted, pyc_freed = _scan_pyc(Path.home(), dry_run)
        all_found.extend(pyc_items)
        total_deleted += pyc_deleted
        total_bytes += pyc_freed

    # Sort by size descending so largest items appear first
    all_found.sort(key=lambda x: x.get("size_kb", 0), reverse=True)

    action = "Would remove" if dry_run else "Removed"
    summary = (
        f"{action} {total_deleted} item(s) "
        f"({round(total_bytes / 1024 / 1024, 1)} MB freed)"
        if not dry_run else
        f"Found {len(all_found)} item(s) totalling "
        f"{round(sum(x.get('size_kb', 0) for x in all_found) / 1024, 1)} MB "
        f"(older than {max_age_days} days)"
    )

    return {
        "found": all_found[:100],     # cap list to avoid huge payloads
        "total_found": len(all_found),
        "total_deleted": total_deleted,
        "space_freed_mb": round(total_bytes / 1024 / 1024, 2),
        "dry_run": dry_run,
        "max_age_days": max_age_days,
        "summary": summary,
    }
