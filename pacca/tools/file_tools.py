"""File tools — list_directory, create_folder, create_file, read_file,
move_file, copy_file, search_files, unzip_archive, move_to_trash."""
from __future__ import annotations
import fnmatch
import os
import platform
import shutil
import stat
import zipfile
from pathlib import Path
from typing import Any

from pacca.security.archive_safety import ArchiveSafetyValidator

PACCA_DOWNLOADS = Path.home() / ".pacca" / "downloads"


def _size_str(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n/1024:.1f} KB"
    if n < 1024 ** 3:
        return f"{n/1024**2:.1f} MB"
    return f"{n/1024**3:.1f} GB"


def list_directory(path: str, show_hidden: bool = False) -> dict:
    p = Path(path)
    if not p.exists():
        return {"error": f"Path does not exist: {path}"}
    if not p.is_dir():
        return {"error": f"Not a directory: {path}"}
    try:
        entries = []
        for item in sorted(p.iterdir()):
            if not show_hidden and item.name.startswith("."):
                continue
            try:
                st = item.stat()
                entries.append({
                    "name": item.name,
                    "type": "dir" if item.is_dir() else "file",
                    "size": st.st_size if item.is_file() else None,
                    "size_human": _size_str(st.st_size) if item.is_file() else None,
                    "modified": st.st_mtime,
                })
            except OSError:
                entries.append({"name": item.name, "type": "unknown", "error": "stat failed"})
        return {"path": str(p.resolve()), "entries": entries, "count": len(entries)}
    except PermissionError as e:
        return {"error": f"Permission denied: {e}"}


def create_folder(path: str, dry_run: bool = False) -> dict:
    p = Path(path)
    if p.exists():
        return {"error": f"Directory already exists: {path}"}
    if dry_run:
        return {"dry_run": True, "would_create": str(p.resolve())}
    try:
        p.mkdir(parents=True, exist_ok=False)
        return {"created": str(p.resolve())}
    except Exception as e:
        return {"error": str(e)}


def create_file(path: str, content: str = "", dry_run: bool = False,
                overwrite: bool = False) -> dict:
    p = Path(path)
    if p.exists() and not overwrite:
        st = p.stat()
        return {
            "error": "File exists — confirmation required",
            "existing_size": st.st_size,
            "existing_mtime": st.st_mtime,
            "path": str(p.resolve()),
            "requires_confirmation": True,
        }
    if dry_run:
        return {"dry_run": True, "would_create": str(p.resolve()),
                "content_length": len(content)}
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"created": str(p.resolve()), "bytes_written": len(content.encode())}
    except Exception as e:
        return {"error": str(e)}


def read_file(path: str, max_bytes: int = 104_857_600) -> dict:
    p = Path(path)
    if not p.exists():
        return {"error": f"File not found: {path}"}
    if not p.is_file():
        return {"error": f"Not a file: {path}"}
    size = p.stat().st_size
    if size > max_bytes:
        return {"error": f"File too large ({_size_str(size)}); max {_size_str(max_bytes)}"}
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        return {"path": str(p.resolve()), "content": content, "size": size}
    except Exception as e:
        return {"error": str(e)}


def move_file(source: str, destination: str, dry_run: bool = False) -> dict:
    src = Path(source)
    dst = Path(destination)
    if not src.exists():
        return {"error": f"Source not found: {source}"}
    if dst.exists():
        return {
            "warning": f"Destination exists: {destination}",
            "requires_confirmation": True,
        }
    if dry_run:
        return {"dry_run": True, "would_move": str(src.resolve()),
                "to": str(dst.resolve())}
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return {"moved": str(src.resolve()), "to": str(dst.resolve())}
    except Exception as e:
        return {"error": str(e)}


def copy_file(source: str, destination: str, dry_run: bool = False) -> dict:
    src = Path(source)
    dst = Path(destination)
    if not src.exists():
        return {"error": f"Source not found: {source}"}
    if dry_run:
        return {"dry_run": True, "would_copy": str(src.resolve()),
                "to": str(dst.resolve())}
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        return {"copied": str(src.resolve()), "to": str(dst.resolve())}
    except Exception as e:
        return {"error": str(e)}


def search_files(path: str, pattern: str = "*",
                 content_query: str = "", max_results: int = 100) -> dict:
    base = Path(path)
    if not base.exists():
        return {"error": f"Search path not found: {path}"}
    results = []
    try:
        for root, dirs, files in os.walk(str(base)):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in files:
                if fnmatch.fnmatch(name.lower(), pattern.lower()):
                    filepath = Path(root) / name
                    matched_content = False
                    if content_query:
                        try:
                            text = filepath.read_text(encoding="utf-8", errors="ignore")
                            matched_content = content_query.lower() in text.lower()
                        except Exception:
                            matched_content = False
                    if not content_query or matched_content:
                        try:
                            st = filepath.stat()
                            results.append({
                                "path": str(filepath.resolve()),
                                "name": name,
                                "size": st.st_size,
                                "modified": st.st_mtime,
                            })
                        except OSError:
                            results.append({"path": str(filepath), "name": name})
                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break
    except PermissionError:
        pass
    return {"results": results, "count": len(results),
            "truncated": len(results) >= max_results}


def _has_trash() -> bool:
    system = platform.system()
    if system == "Windows":
        return True
    if system == "Darwin":
        return True
    xdg_data = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    trash_dir = os.path.join(xdg_data, "Trash", "files")
    return os.path.exists(trash_dir)


def move_to_trash(paths: list[str], dry_run: bool = False) -> dict:
    if not _has_trash():
        return {
            "error": "No trash facility available on this system (headless Linux). "
                     "PACCA will not permanently delete files. Aborting for safety.",
            "halted": True,
        }
    if dry_run:
        total_size = 0
        for p in paths:
            try:
                st = Path(p).stat()
                total_size += st.st_size
            except OSError:
                pass
        return {
            "dry_run": True,
            "would_trash": paths,
            "count": len(paths),
            "total_size": _size_str(total_size),
        }
    results = []
    errors = []
    for path_str in paths:
        p = Path(path_str)
        if not p.exists():
            errors.append(f"Not found: {path_str}")
            continue
        try:
            system = platform.system()
            if system == "Darwin":
                trash_dir = Path.home() / ".Trash"
                dest = trash_dir / p.name
                i = 1
                while dest.exists():
                    dest = trash_dir / f"{p.stem}_{i}{p.suffix}"
                    i += 1
                shutil.move(str(p), str(dest))
                results.append(str(p.resolve()))
            elif system == "Windows":
                try:
                    import winshell
                    winshell.delete_file(str(p), no_confirm=True, allow_undo=True)
                    results.append(str(p.resolve()))
                except ImportError:
                    trash_dir = Path.home() / ".pacca" / "_trash"
                    trash_dir.mkdir(parents=True, exist_ok=True)
                    dest = trash_dir / p.name
                    shutil.move(str(p), str(dest))
                    results.append(str(p.resolve()))
            else:
                xdg = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
                trash_files = Path(xdg) / "Trash" / "files"
                trash_files.mkdir(parents=True, exist_ok=True)
                dest = trash_files / p.name
                i = 1
                while dest.exists():
                    dest = trash_files / f"{p.stem}_{i}{p.suffix}"
                    i += 1
                shutil.move(str(p), str(dest))
                results.append(str(p.resolve()))
        except Exception as e:
            errors.append(f"Failed to trash {path_str}: {e}")

    return {"trashed": results, "errors": errors,
            "count": len(results), "failed": len(errors)}


def unzip_archive(archive_path: str, destination: str,
                  dry_run: bool = False) -> dict:
    validator = ArchiveSafetyValidator()
    report = validator.validate(archive_path, destination)

    if report.blocked:
        return {"error": f"Archive blocked: {report.block_reason}", "blocked": True}

    if report.needs_confirmation:
        return {
            "requires_confirmation": True,
            "confirmation_reason": report.confirmation_reason,
            "archive": archive_path,
            "destination": destination,
        }

    if dry_run:
        return {
            "dry_run": True,
            "archive": archive_path,
            "destination": destination,
            "entry_count": report.entry_count,
            "total_bytes": report.total_uncompressed_bytes,
        }

    try:
        dest = Path(destination)
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(str(dest))
        return {
            "extracted": archive_path,
            "to": destination,
            "entry_count": report.entry_count,
            "total_bytes": report.total_uncompressed_bytes,
        }
    except Exception as e:
        return {"error": str(e)}
