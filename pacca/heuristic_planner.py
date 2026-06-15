"""HeuristicPlanner — generates multi-step plans without an LLM."""
from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Any

from pacca.models.task_scope import TaskScope


PATH_RE = re.compile(
    r'(?:(?:~/|\.{0,2}/|[A-Za-z]:\\)[^\s"\']+|'
    r'(?:"([^"]+)"|\'([^\']+)\'))',
    re.I,
)
URL_RE = re.compile(r'https?://[^\s]+', re.I)
PATTERN_RE = re.compile(r'\*\.[a-zA-Z0-9]{1,6}')
QUOTE_RE = re.compile(r'["\']([^"\']+)["\']')
TO_RE = re.compile(r'\bto\s+([~/\\.][^\s]+|\S+folder|\S+directory|\S+dir)\b', re.I)
FROM_RE = re.compile(r'\bfrom\s+([~/\\.][^\s]+)\b', re.I)
IN_RE = re.compile(r'\bin\s+([~/\\.][^\s]+)\b', re.I)
REPO_RE = re.compile(r'(?:repo|repository|git)\s+(?:at\s+)?([~/\\.][^\s]+)', re.I)
MSG_RE = re.compile(r'(?:message|msg|commit message|with message)\s+["\']([^"\']+)["\']', re.I)


def _extract_paths(command: str) -> list[str]:
    paths = []
    for m in PATH_RE.finditer(command):
        p = m.group(1) or m.group(2) or m.group(0)
        p = p.strip('"\'')
        if len(p) > 2 and not p.startswith("http"):
            paths.append(os.path.expanduser(p))
    for m in QUOTE_RE.finditer(command):
        val = m.group(1)
        if "/" in val or "\\" in val or val.startswith("~"):
            paths.append(os.path.expanduser(val))
    return list(dict.fromkeys(paths))


def _extract_urls(command: str) -> list[str]:
    return URL_RE.findall(command)


def _extract_patterns(command: str) -> list[str]:
    return PATTERN_RE.findall(command)


def _expand(path: str) -> str:
    return os.path.expanduser(os.path.expandvars(path))


def _cwd() -> str:
    return os.getcwd()


def _home() -> str:
    return str(Path.home())


class HeuristicPlanner:
    """
    Rule-based multi-step planner for when no LLM is available.
    Handles the most common command patterns across all 6 domains.
    """

    def plan(self, scope: TaskScope) -> list[dict]:
        cmd = scope.raw_command
        low = cmd.lower()
        domain = scope.intent_domain

        if domain == "system":
            return self._plan_system(low)
        if domain == "app":
            return self._plan_app(low, cmd)
        if domain == "git":
            return self._plan_git(low, cmd)
        if domain == "browser":
            return self._plan_browser(low, cmd)
        if domain == "document":
            return self._plan_document(low, cmd)
        if domain == "messaging":
            return self._plan_messaging(low, cmd)
        if domain == "calendar":
            return self._plan_calendar(low, cmd)
        if domain in ("vision", "coding", "research"):
            # These require LLM; heuristic mode produces a clear no-op notice
            return self._plan_llm_required(domain, cmd)
        # "file", "mixed", or unknown — use file planner with system keyword override
        return self._plan_file(low, cmd)

    def _plan_llm_required(self, domain: str, cmd: str) -> list[dict]:
        """Return the real domain tool — it will fail fast with a clear API-key error."""
        quotes = QUOTE_RE.findall(cmd)
        paths = _extract_paths(cmd)
        if domain == "vision":
            # capture_and_analyze needs no image path; it uses the active browser page
            return [{"tool": "capture_and_analyze",
                     "args": {"question": cmd[:200]},
                     "description": f"Analyze: {cmd[:60]}"}]
        if domain == "coding":
            lang = "python"
            for w in ("javascript", "typescript", "go", "rust", "java", "sql", "bash"):
                if w in cmd.lower():
                    lang = w
                    break
            out = paths[0] if paths else None
            return [{"tool": "generate_code",
                     "args": {"description": cmd, "language": lang,
                               **({"output_path": out} if out else {})},
                     "description": f"Generate {lang} code: {cmd[:50]}"}]
        if domain == "research":
            topic = quotes[0] if quotes else cmd[:120]
            return [{"tool": "research_topic",
                     "args": {"topic": topic, "depth": 2},
                     "description": f"Research: {topic[:60]}"}]
        return [{"tool": "list_directory", "args": {"path": _cwd()},
                 "description": "List current directory"}]

    def _plan_system(self, low: str) -> list[dict]:
        include_procs = "process" in low or "top" in low or "running" in low
        return [{
            "tool": "system_monitor",
            "args": {"include_processes": include_procs, "top_n_processes": 10},
            "description": "Show system CPU, memory, disk, and uptime",
        }]

    def _plan_calendar(self, low: str, cmd: str) -> list[dict]:
        quotes = QUOTE_RE.findall(cmd)
        # Create event
        if any(w in low for w in ("create", "add", "schedule", "new", "book", "set up")):
            title = quotes[0] if quotes else cmd[:60]
            # Try to extract start/end from command (best-effort; LLM handles complex NL dates)
            import re as _re
            dt_re = _re.compile(
                r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?)',
            )
            times = dt_re.findall(cmd.replace(" ", "T") if re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', cmd) else cmd)
            start = times[0].replace(" ", "T") if times else ""
            end   = times[1].replace(" ", "T") if len(times) > 1 else ""
            if not start:
                # No datetime found — return a user-friendly error step
                return [{
                    "tool": "create_calendar_event",
                    "args": {"title": title, "start": "", "end": ""},
                    "description": f"Create calendar event: {title[:50]} (provide start/end in ISO format)",
                }]
            return [{
                "tool": "create_calendar_event",
                "args": {"title": title, "start": start, "end": end or start},
                "description": f"Create calendar event: {title[:50]} at {start}",
            }]
        # Delete event
        if any(w in low for w in ("delete", "remove", "cancel")):
            ev_id = quotes[0] if quotes else ""
            return [{
                "tool": "delete_calendar_event",
                "args": {"event_id": ev_id},
                "description": f"Delete calendar event{': ' + ev_id if ev_id else ''}",
            }]
        # Default: list events
        days = 7
        _days_re = re.compile(r'\b(\d+)\s*days?\b', re.I)
        m = _days_re.search(low)
        if m:
            days = min(int(m.group(1)), 90)
        elif "today" in low:
            days = 1
        elif "week" in low:
            days = 7
        elif "month" in low:
            days = 30
        return [{
            "tool": "list_calendar_events",
            "args": {"days_ahead": days},
            "description": f"List upcoming calendar events (next {days} days)",
        }]

    def _plan_app(self, low: str, cmd: str) -> list[dict]:
        if "list" in low or "running" in low:
            return [{"tool": "list_running_apps", "args": {},
                     "description": "List all running applications"}]
        if "close" in low or "quit" in low or "kill" in low:
            names = QUOTE_RE.findall(cmd)
            name = names[0] if names else "unknown"
            return [{"tool": "close_app", "args": {"name": name},
                     "description": f"Close {name}"}]
        names = QUOTE_RE.findall(cmd)
        name = names[0] if names else "Calculator"
        return [{"tool": "open_known_app", "args": {"name": name},
                 "description": f"Open {name}"}]

    def _plan_git(self, low: str, cmd: str) -> list[dict]:
        repo = _cwd()
        m = REPO_RE.search(cmd)
        if m:
            repo = _expand(m.group(1))

        steps = []
        if "status" in low:
            steps.append({"tool": "git_status", "args": {"repo_path": repo},
                          "description": "Show git status"})
        if "diff" in low:
            staged = "--cached" in low or "staged" in low
            steps.append({"tool": "git_diff",
                          "args": {"repo_path": repo, "staged": staged},
                          "description": f"Show {'staged ' if staged else ''}diff"})
        if "add" in low:
            steps.append({"tool": "git_add",
                          "args": {"repo_path": repo, "all_changes": True},
                          "description": "Stage all changes"})
        if "commit" in low:
            m2 = MSG_RE.search(cmd)
            msg = m2.group(1) if m2 else "Update"
            steps.append({"tool": "git_commit",
                          "args": {"repo_path": repo, "message": msg},
                          "description": f"Commit: {msg}"})

        if not steps:
            steps.append({"tool": "git_status", "args": {"repo_path": repo},
                          "description": "Show git status"})
        return steps

    def _plan_browser(self, low: str, cmd: str) -> list[dict]:
        urls = _extract_urls(cmd)
        if urls:
            steps = [{"tool": "browser_open_url", "args": {"url": urls[0]},
                      "description": f"Open {urls[0]}"}]
            if "text" in low or "extract" in low or "read" in low:
                steps.append({"tool": "browser_extract_page_text", "args": {},
                              "description": "Extract page text"})
            return steps

        quotes = QUOTE_RE.findall(cmd)
        query = quotes[0] if quotes else cmd.replace("search", "").replace("google", "").strip()[:80]
        return [{"tool": "browser_web_search",
                 "args": {"query": query, "engine": "duckduckgo"},
                 "description": f"Web search: {query}"}]

    def _plan_document(self, low: str, cmd: str) -> list[dict]:
        paths = _extract_paths(cmd)
        quotes = QUOTE_RE.findall(cmd)
        if "read" in low or "open" in low:
            path = paths[0] if paths else (quotes[0] if quotes else "document.docx")
            if path.endswith(".xlsx") or "excel" in low or "spreadsheet" in low:
                return [{"tool": "read_xlsx", "args": {"path": path},
                         "description": f"Read spreadsheet {path}"}]
            return [{"tool": "read_docx", "args": {"path": path},
                     "description": f"Read document {path}"}]
        if "create" in low or "make" in low or "new" in low:
            title = quotes[0] if quotes else "New Document"
            content = quotes[1] if len(quotes) > 1 else ""
            if "xlsx" in low or "excel" in low or "spreadsheet" in low:
                dest = paths[0] if paths else os.path.join(_cwd(), "spreadsheet.xlsx")
                return [{"tool": "create_xlsx", "args": {"path": dest,
                         "sheet_name": title, "headers": [], "rows": []},
                         "description": f"Create spreadsheet {dest}"}]
            dest = paths[0] if paths else os.path.join(_cwd(), "document.docx")
            return [{"tool": "create_docx", "args": {"path": dest,
                     "title": title, "content": content},
                     "description": f"Create document {dest}"}]
        path = paths[0] if paths else ""
        if path.endswith(".xlsx"):
            return [{"tool": "read_xlsx", "args": {"path": path},
                     "description": f"Read {path}"}]
        return [{"tool": "read_docx", "args": {"path": path or "document.docx"},
                 "description": "Read document"}]

    def _plan_file(self, low: str, cmd: str) -> list[dict]:
        # Safety net: detect system-monitor intent even when domain was misclassified
        _SYS_KW = ("cpu", "ram", "memory usage", "disk usage", "uptime",
                   "system resources", "system stats", "resource usage",
                   "performance", "hardware", "system info", "sysmon",
                   "system status", "process list")
        if any(kw in low for kw in _SYS_KW):
            return self._plan_system(low)

        paths = _extract_paths(cmd)
        patterns = _extract_patterns(cmd)
        quotes = QUOTE_RE.findall(cmd)

        if "list" in low or "ls" in low or "show" in low or "what" in low:
            # Resolve well-known directory aliases even when no explicit path is given
            if paths:
                target = paths[0]
            elif any(w in low for w in ("home", "~", "home folder", "home directory")):
                target = _home()
            elif any(w in low for w in ("download", "downloads")):
                target = os.path.join(_home(), "Downloads")
            elif any(w in low for w in ("desktop",)):
                target = os.path.join(_home(), "Desktop")
            elif any(w in low for w in ("document", "documents")):
                target = os.path.join(_home(), "Documents")
            elif any(w in low for w in ("picture", "pictures", "photo", "photos")):
                target = os.path.join(_home(), "Pictures")
            elif any(w in low for w in ("music",)):
                target = os.path.join(_home(), "Music")
            elif any(w in low for w in ("video", "videos", "movies")):
                target = os.path.join(_home(), "Videos")
            elif any(w in low for w in ("tmp", "temp", "/tmp")):
                target = "/tmp"
            elif any(w in low for w in ("current", "here", "this", "working")):
                target = _cwd()
            else:
                target = _cwd()
            return [{"tool": "list_directory",
                     "args": {"path": target, "show_hidden": "hidden" in low or "-a" in low},
                     "description": f"List {target}"}]

        if "search" in low or "find" in low:
            base = paths[0] if paths else _home()
            pattern = patterns[0] if patterns else "*.txt"
            query = ""
            for q in QUOTE_RE.findall(cmd):
                if q not in str(paths):
                    query = q
                    break
            return [{"tool": "search_files",
                     "args": {"path": base, "pattern": pattern,
                              "content_query": query, "max_results": 50},
                     "description": f"Search {base} for {pattern}"}]

        if "read" in low or "open" in low or "show" in low or "cat" in low or "view" in low:
            path = paths[0] if paths else (quotes[0] if quotes else "")
            if not path:
                return [{"tool": "list_directory", "args": {"path": _cwd()},
                         "description": "List current directory (no path specified)"}]
            return [{"tool": "read_file", "args": {"path": path},
                     "description": f"Read {path}"}]

        if "create" in low or "make" in low or "new" in low or "write" in low or "touch" in low:
            if "folder" in low or "directory" in low or "dir" in low:
                path = paths[0] if paths else (quotes[0] if quotes else os.path.join(_cwd(), "new_folder"))
                return [{"tool": "create_folder", "args": {"path": path},
                         "description": f"Create folder {path}"}]
            content_match = [q for q in quotes if "/" not in q and "\\" not in q]
            path = paths[0] if paths else os.path.join(_cwd(), quotes[0] if quotes else "new_file.txt")
            content = content_match[0] if content_match else ""
            return [{"tool": "create_file",
                     "args": {"path": path, "content": content},
                     "description": f"Create file {path}"}]

        if "move" in low or "mv" in low or "rename" in low:
            src = paths[0] if len(paths) >= 1 else (quotes[0] if quotes else "")
            dst_m = TO_RE.search(cmd)
            dst = _expand(dst_m.group(1)) if dst_m else (paths[1] if len(paths) >= 2 else "")
            if src and dst:
                return [{"tool": "move_file",
                         "args": {"source": src, "destination": dst},
                         "description": f"Move {src} → {dst}"}]
            return [{"tool": "list_directory", "args": {"path": _cwd()},
                     "description": "List current directory (move needs src and dst)"}]

        if "copy" in low or "cp" in low or "duplicate" in low:
            src = paths[0] if len(paths) >= 1 else ""
            dst_m = TO_RE.search(cmd)
            dst = _expand(dst_m.group(1)) if dst_m else (paths[1] if len(paths) >= 2 else "")
            if src and dst:
                return [{"tool": "copy_file",
                         "args": {"source": src, "destination": dst},
                         "description": f"Copy {src} → {dst}"}]

        if "trash" in low or "delete" in low or "remove" in low:
            # Try explicit paths first; then fall back to quoted names or bare tokens
            if not paths:
                quoted = QUOTE_RE.findall(cmd)
                if quoted:
                    paths = [os.path.join(_cwd(), q) for q in quoted]
                else:
                    # Extract a bare filename token after "delete"/"trash"/"remove"
                    m = re.search(
                        r'\b(?:delete|trash|remove)\s+(?:this\s+)?(?:file\s+)?([^\s]+)',
                        cmd, re.I)
                    if m:
                        token = m.group(1)
                        if not token.startswith(("~/", "/", ".")):
                            token = os.path.join(_cwd(), token)
                        paths = [os.path.expanduser(token)]
            if paths:
                return [{"tool": "move_to_trash",
                         "args": {"paths": paths},
                         "description": f"Move {len(paths)} item(s) to trash"}]

        if "unzip" in low or "extract" in low:
            archive = paths[0] if paths else ""
            dest_m = TO_RE.search(cmd)
            dest = _expand(dest_m.group(1)) if dest_m else _cwd()
            if archive:
                return [{"tool": "unzip_archive",
                         "args": {"archive_path": archive, "destination": dest},
                         "description": f"Extract {archive} to {dest}"}]

        if "zip" in low or "compress" in low:
            dest = paths[-1] if paths else os.path.join(_cwd(), "archive.zip")
            sources = paths[:-1] if len(paths) > 1 else paths
            if sources:
                return [{"tool": "zip_files",
                         "args": {"source_paths": sources, "output_path": dest},
                         "description": f"Create {dest}"}]

        return [{"tool": "list_directory", "args": {"path": _cwd()},
                 "description": "List current directory"}]

    def _plan_messaging(self, low: str, cmd: str) -> list[dict]:
        quotes = QUOTE_RE.findall(cmd)
        msg = quotes[0] if quotes else cmd
        return [{"tool": "send_whatsapp_message",
                 "args": {"message": msg},
                 "description": f"Send WhatsApp message: {msg[:40]}"}]
