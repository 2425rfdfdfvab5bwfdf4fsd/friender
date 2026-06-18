"""
A2UI — Agent-to-UI interactive card protocol.

Inspired by OpenClaw's Live Canvas / A2UI framework.
The LLM (or tool result post-processor) emits structured JSON cards that
the frontend renders as interactive UI components instead of plain text.

Card types:
  table    — data grid with sortable columns
  chart    — bar / line / pie chart (pure CSS bars, no external lib)
  kanban   — column-based task board
  list     — rich icon list (search results, file listings)
  metric   — single KPI tile with label + value + sparkline
  code     — syntax-highlighted code block
  timeline — chronological event list
  progress — multi-item progress bars
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

log = logging.getLogger(__name__)


# ── Card builders ─────────────────────────────────────────────────────────────

def table_card(title: str, columns: list[str], rows: list[list]) -> dict:
    return {"type": "table", "title": title, "columns": columns, "rows": rows}


def list_card(title: str, items: list[dict], icon: str = "•") -> dict:
    """items: [{"label": str, "sub": str, "icon": str, "badge": str}, ...]"""
    return {"type": "list", "title": title, "icon": icon, "items": items}


def metric_card(title: str, metrics: list[dict]) -> dict:
    """metrics: [{"label": str, "value": str, "unit": str, "trend": str}, ...]"""
    return {"type": "metric", "title": title, "metrics": metrics}


def chart_card(title: str, chart_type: str, labels: list[str], values: list[float], unit: str = "") -> dict:
    return {"type": "chart", "title": title, "chart_type": chart_type,
            "labels": labels, "values": values, "unit": unit}


def code_card(title: str, language: str, code: str) -> dict:
    return {"type": "code", "title": title, "language": language, "code": code}


def timeline_card(title: str, events: list[dict]) -> dict:
    """events: [{"time": str, "label": str, "sub": str, "icon": str}, ...]"""
    return {"type": "timeline", "title": title, "events": events}


def kanban_card(title: str, columns: list[dict]) -> dict:
    """columns: [{"name": str, "color": str, "items": [{"title": str, "sub": str}]}, ...]"""
    return {"type": "kanban", "title": title, "columns": columns}


def progress_card(title: str, items: list[dict]) -> dict:
    """items: [{"label": str, "value": float, "max": float, "unit": str, "color": str}, ...]"""
    return {"type": "progress", "title": title, "items": items}


# ── Tool result → card conversion ─────────────────────────────────────────────

def result_to_card(tool_name: str, args: dict, result: Any) -> dict | None:
    """
    Try to convert a tool result into an A2UI card.
    Returns None if no rich rendering is appropriate.
    """
    try:
        return _convert(tool_name, args, result)
    except Exception as e:
        log.debug("A2UI conversion failed for %s: %s", tool_name, e)
        return None


def _convert(tool_name: str, args: dict, result: Any) -> dict | None:  # noqa: C901
    if not isinstance(result, (dict, list, str)):
        return None

    # ── list_directory ────────────────────────────────────────────────────────
    if tool_name == "list_directory":
        items = _extract_file_list(result)
        if items:
            path = args.get("path", "~")
            return list_card(f"📁 {path}", items[:50])

    # ── search_files ──────────────────────────────────────────────────────────
    if tool_name == "search_files":
        items = _extract_file_list(result)
        if items:
            return list_card(f"🔍 Search: {args.get('pattern','')}", items[:30])

    # ── system_monitor ────────────────────────────────────────────────────────
    if tool_name == "system_monitor":
        return _system_monitor_card(result)

    # ── gmail_list_emails / gmail_search_emails ───────────────────────────────
    if tool_name in ("gmail_list_emails", "gmail_search_emails"):
        return _email_list_card(result, tool_name, args)

    # ── drive_list_files / drive_search_files ─────────────────────────────────
    if tool_name in ("drive_list_files", "drive_search_files"):
        return _drive_list_card(result, args)

    # ── list_calendar_events ──────────────────────────────────────────────────
    if tool_name == "list_calendar_events":
        return _calendar_card(result)

    # ── trello_list_boards / trello_list_cards ────────────────────────────────
    if tool_name == "trello_list_boards":
        return _trello_boards_card(result)
    if tool_name == "trello_list_cards":
        return _trello_cards_card(result, args)
    if tool_name == "trello_get_lists":
        return _trello_lists_card(result, args)

    # ── generate_code / refactor_code / explain_code ─────────────────────────
    if tool_name in ("generate_code", "refactor_code", "run_code"):
        return _code_card_from_result(result, args, tool_name)

    # ── research_topic ────────────────────────────────────────────────────────
    if tool_name == "research_topic":
        return _research_card(result, args)

    # ── git_status ────────────────────────────────────────────────────────────
    if tool_name == "git_status":
        return _git_status_card(result, args)

    # ── git_diff ─────────────────────────────────────────────────────────────
    if tool_name == "git_diff":
        return _git_diff_card(result, args)

    # ── slack_list_channels ───────────────────────────────────────────────────
    if tool_name == "slack_list_channels":
        return _slack_channels_card(result)

    # ── slack_get_messages ────────────────────────────────────────────────────
    if tool_name == "slack_get_messages":
        return _slack_messages_card(result, args)

    # ── spotify_search ────────────────────────────────────────────────────────
    if tool_name == "spotify_search":
        return _spotify_search_card(result, args)

    # ── youtube_search ────────────────────────────────────────────────────────
    if tool_name == "youtube_search":
        return _youtube_search_card(result, args)

    # ── notion_search ─────────────────────────────────────────────────────────
    if tool_name == "notion_search":
        return _notion_search_card(result, args)

    # ── list_running_apps / find_installed_apps ───────────────────────────────
    if tool_name in ("list_running_apps", "find_installed_apps", "list_available_web_apps"):
        return _apps_list_card(result, tool_name)

    # ── cleanup_temp_files ────────────────────────────────────────────────────
    if tool_name == "cleanup_temp_files":
        return _cleanup_card(result)

    return None


# ── Tool-specific converters ──────────────────────────────────────────────────

def _extract_file_list(result: Any) -> list[dict]:
    items = []
    if isinstance(result, dict):
        entries = result.get("files") or result.get("entries") or result.get("items") or []
        if not entries and "output" in result:
            lines = str(result["output"]).splitlines()
            for line in lines:
                line = line.strip()
                if line:
                    items.append({"label": line, "icon": "📄" if "." in line else "📁"})
            return items
        for e in entries[:50]:
            if isinstance(e, dict):
                name = e.get("name") or e.get("path") or str(e)
                size = e.get("size")
                sub = f"{size} bytes" if size else e.get("modified", "")
                icon = "📁" if e.get("is_dir") or str(name).endswith("/") else _file_icon(name)
                items.append({"label": name, "sub": sub, "icon": icon})
            elif isinstance(e, str):
                items.append({"label": e, "icon": _file_icon(e)})
    elif isinstance(result, list):
        for e in result[:50]:
            if isinstance(e, str):
                items.append({"label": e, "icon": _file_icon(e)})
            elif isinstance(e, dict):
                name = e.get("name") or e.get("path") or str(e)
                items.append({"label": name, "icon": _file_icon(name)})
    elif isinstance(result, str):
        for line in result.splitlines():
            line = line.strip()
            if line:
                items.append({"label": line, "icon": _file_icon(line)})
    return items


def _file_icon(name: str) -> str:
    ext = str(name).rsplit(".", 1)[-1].lower() if "." in str(name) else ""
    icons = {
        "py": "🐍", "js": "🟨", "ts": "🔷", "html": "🌐", "css": "🎨",
        "json": "📋", "md": "📝", "txt": "📄", "pdf": "📕", "docx": "📘",
        "xlsx": "📗", "csv": "📊", "zip": "🗜️", "tar": "🗜️", "gz": "🗜️",
        "png": "🖼️", "jpg": "🖼️", "jpeg": "🖼️", "gif": "🖼️", "svg": "🖼️",
        "mp4": "🎬", "mp3": "🎵", "sh": "⚙️", "rs": "🦀", "go": "🐹",
    }
    return icons.get(ext, "📄")


def _system_monitor_card(result: Any) -> dict | None:
    if not isinstance(result, dict):
        return None
    metrics = []

    cpu = result.get("cpu_percent") or result.get("cpu")
    if cpu is not None:
        metrics.append({"label": "CPU", "value": float(cpu), "max": 100, "unit": "%",
                         "color": "var(--danger)" if float(cpu) > 80 else "var(--accent)"})

    mem = result.get("memory") or {}
    if isinstance(mem, dict):
        used_pct = mem.get("percent")
        if used_pct is not None:
            metrics.append({"label": "Memory", "value": float(used_pct), "max": 100, "unit": "%",
                             "color": "var(--warning)" if float(used_pct) > 70 else "var(--success)"})

    disk = result.get("disk") or {}
    if isinstance(disk, dict):
        used_pct = disk.get("percent")
        if used_pct is not None:
            metrics.append({"label": "Disk", "value": float(used_pct), "max": 100, "unit": "%",
                             "color": "var(--danger)" if float(used_pct) > 90 else "var(--text-2)"})

    if not metrics:
        # Try flat structure
        for k, v in result.items():
            if isinstance(v, (int, float)):
                try:
                    metrics.append({"label": k.replace("_", " ").title(), "value": float(v),
                                     "max": 100, "unit": "", "color": "var(--accent)"})
                except Exception:
                    pass

    if metrics:
        return progress_card("📊 System Monitor", metrics)
    return None


def _email_list_card(result: Any, tool_name: str, args: dict) -> dict | None:
    emails = []
    if isinstance(result, dict):
        emails = result.get("emails") or result.get("messages") or result.get("items") or []
    elif isinstance(result, list):
        emails = result

    if not emails:
        return None

    columns = ["From", "Subject", "Date"]
    rows = []
    for e in emails[:20]:
        if isinstance(e, dict):
            rows.append([
                str(e.get("from") or e.get("sender") or "")[:40],
                str(e.get("subject") or e.get("snippet") or "")[:60],
                str(e.get("date") or e.get("timestamp") or "")[:20],
            ])

    if rows:
        query = args.get("query", "")
        title = f"📧 Search: {query}" if query else "📧 Inbox"
        return table_card(title, columns, rows)
    return None


def _drive_list_card(result: Any, args: dict) -> dict | None:
    files = []
    if isinstance(result, dict):
        files = result.get("files") or result.get("items") or []
    elif isinstance(result, list):
        files = result

    if not files:
        return None

    items = []
    for f in files[:30]:
        if isinstance(f, dict):
            name = f.get("name") or f.get("title") or str(f)
            mime = f.get("mimeType") or f.get("type") or ""
            icon = "📁" if "folder" in mime else _file_icon(name)
            size = f.get("size")
            sub = f"{int(size)//1024} KB" if size else f.get("modifiedTime", "")[:10]
            items.append({"label": name, "sub": sub, "icon": icon})

    if items:
        query = args.get("query", "")
        title = f"☁️ Drive: {query}" if query else "☁️ Google Drive"
        return list_card(title, items)
    return None


def _calendar_card(result: Any) -> dict | None:
    events = []
    if isinstance(result, dict):
        events = result.get("events") or result.get("items") or []
    elif isinstance(result, list):
        events = result

    if not events:
        return None

    timeline_events = []
    for e in events[:20]:
        if isinstance(e, dict):
            title = e.get("summary") or e.get("title") or "Event"
            start = e.get("start") or e.get("startTime") or ""
            if isinstance(start, dict):
                start = start.get("dateTime") or start.get("date") or ""
            start_str = str(start)[:16].replace("T", " ")
            loc = e.get("location") or e.get("description") or ""
            timeline_events.append({"time": start_str, "label": title,
                                     "sub": str(loc)[:60], "icon": "📅"})

    if timeline_events:
        return timeline_card("📅 Calendar Events", timeline_events)
    return None


def _trello_boards_card(result: Any) -> dict | None:
    boards = []
    if isinstance(result, dict):
        boards = result.get("boards") or result.get("items") or []
    elif isinstance(result, list):
        boards = result

    if not boards:
        return None

    items = [
        {"label": b.get("name", "Board"), "sub": b.get("desc", "")[:60], "icon": "📋"}
        for b in boards[:20] if isinstance(b, dict)
    ]
    return list_card("📋 Trello Boards", items) if items else None


def _trello_cards_card(result: Any, args: dict) -> dict | None:
    cards = []
    if isinstance(result, dict):
        cards = result.get("cards") or result.get("items") or []
    elif isinstance(result, list):
        cards = result

    if not cards:
        return None

    items = [
        {"label": c.get("name", "Card"), "sub": c.get("desc", "")[:60], "icon": "🗂️"}
        for c in cards[:30] if isinstance(c, dict)
    ]
    return list_card("🗂️ Trello Cards", items) if items else None


def _trello_lists_card(result: Any, args: dict) -> dict | None:
    lists = []
    if isinstance(result, dict):
        lists = result.get("lists") or result.get("items") or []
    elif isinstance(result, list):
        lists = result

    if not lists:
        return None

    colors = ["var(--accent)", "var(--success)", "var(--warning)", "var(--danger)"]
    columns = []
    for i, lst in enumerate(lists[:6]):
        if isinstance(lst, dict):
            columns.append({
                "name": lst.get("name", f"List {i+1}"),
                "color": colors[i % len(colors)],
                "items": [],
            })

    return kanban_card("📋 Trello Board", columns) if columns else None


def _code_card_from_result(result: Any, args: dict, tool_name: str) -> dict | None:
    code_str = ""
    lang = args.get("language", "python")

    if isinstance(result, dict):
        code_str = (result.get("code") or result.get("output") or
                    result.get("result") or result.get("generated") or "")
    elif isinstance(result, str):
        code_str = result

    if not code_str or len(code_str) < 10:
        return None

    titles = {
        "generate_code": f"Generated {lang} code",
        "refactor_code": f"Refactored {lang} code",
        "run_code": f"{lang} output",
    }
    return code_card(titles.get(tool_name, "Code"), lang, str(code_str)[:3000])


def _research_card(result: Any, args: dict) -> dict | None:
    topic = args.get("topic", "Research")

    if isinstance(result, dict):
        summary = result.get("summary") or result.get("answer") or result.get("result") or ""
        sources = result.get("sources") or result.get("references") or []

        if sources:
            items = []
            for s in sources[:10]:
                if isinstance(s, dict):
                    items.append({
                        "label": s.get("title") or s.get("url") or str(s),
                        "sub": s.get("url") or s.get("snippet") or "",
                        "icon": "🔗",
                    })
                elif isinstance(s, str):
                    items.append({"label": s[:80], "icon": "🔗"})
            if items:
                return list_card(f"🔬 Research: {topic}", items)

    return None


def _git_status_card(result: Any, args: dict) -> dict | None:
    if not isinstance(result, (dict, str)):
        return None

    status_str = ""
    if isinstance(result, dict):
        status_str = result.get("output") or result.get("status") or str(result)
    else:
        status_str = result

    lines = [l.strip() for l in str(status_str).splitlines() if l.strip()]
    if not lines:
        return None

    items = []
    for line in lines[:30]:
        icon = "✅" if line.startswith("nothing") else (
            "➕" if line.startswith("new file") else (
            "✏️" if line.startswith("modified") else (
            "🗑️" if line.startswith("deleted") else "📄")))
        items.append({"label": line, "icon": icon})

    repo = args.get("repo_path", "repo")
    return list_card(f"🔀 Git Status: {repo}", items) if items else None


def _git_diff_card(result: Any, args: dict) -> dict | None:
    diff_str = ""
    if isinstance(result, dict):
        diff_str = result.get("output") or result.get("diff") or str(result)
    elif isinstance(result, str):
        diff_str = result

    if not diff_str or len(diff_str) < 5:
        return None

    return code_card(f"🔀 Git Diff", "diff", str(diff_str)[:3000])


def _slack_channels_card(result: Any) -> dict | None:
    channels = []
    if isinstance(result, dict):
        channels = result.get("channels") or result.get("items") or []
    elif isinstance(result, list):
        channels = result

    if not channels:
        return None

    items = [
        {"label": f"#{c.get('name', 'channel')}", "sub": c.get("topic", {}).get("value", "")[:60] if isinstance(c.get("topic"), dict) else str(c.get("topic",""))[:60], "icon": "💬"}
        for c in channels[:30] if isinstance(c, dict)
    ]
    return list_card("💬 Slack Channels", items) if items else None


def _slack_messages_card(result: Any, args: dict) -> dict | None:
    msgs = []
    if isinstance(result, dict):
        msgs = result.get("messages") or result.get("items") or []
    elif isinstance(result, list):
        msgs = result

    if not msgs:
        return None

    columns = ["User", "Message", "Time"]
    rows = []
    for m in msgs[:20]:
        if isinstance(m, dict):
            rows.append([
                str(m.get("user") or m.get("username") or "")[:20],
                str(m.get("text") or m.get("message") or "")[:80],
                str(m.get("ts") or m.get("time") or "")[:15],
            ])

    channel = args.get("channel", "channel")
    return table_card(f"💬 #{channel}", columns, rows) if rows else None


def _spotify_search_card(result: Any, args: dict) -> dict | None:
    tracks = []
    if isinstance(result, dict):
        tracks = (result.get("tracks") or {}).get("items") or result.get("items") or []
    elif isinstance(result, list):
        tracks = result

    if not tracks:
        return None

    items = []
    for t in tracks[:20]:
        if isinstance(t, dict):
            name = t.get("name") or "Track"
            artist = ""
            artists = t.get("artists") or []
            if artists and isinstance(artists[0], dict):
                artist = artists[0].get("name", "")
            album = (t.get("album") or {}).get("name") if isinstance(t.get("album"), dict) else ""
            sub = f"{artist}" + (f" · {album}" if album else "")
            items.append({"label": name, "sub": sub, "icon": "🎵"})

    query = args.get("query", "")
    return list_card(f"🎵 Spotify: {query}", items) if items else None


def _youtube_search_card(result: Any, args: dict) -> dict | None:
    videos = []
    if isinstance(result, dict):
        videos = result.get("items") or result.get("videos") or []
    elif isinstance(result, list):
        videos = result

    if not videos:
        return None

    items = []
    for v in videos[:15]:
        if isinstance(v, dict):
            snippet = v.get("snippet") or {}
            title = snippet.get("title") or v.get("title") or "Video"
            channel = snippet.get("channelTitle") or v.get("channel") or ""
            items.append({"label": title[:80], "sub": channel, "icon": "▶️"})

    query = args.get("query", "")
    return list_card(f"▶️ YouTube: {query}", items) if items else None


def _notion_search_card(result: Any, args: dict) -> dict | None:
    pages = []
    if isinstance(result, dict):
        pages = result.get("results") or result.get("pages") or result.get("items") or []
    elif isinstance(result, list):
        pages = result

    if not pages:
        return None

    items = []
    for p in pages[:20]:
        if isinstance(p, dict):
            props = p.get("properties") or {}
            title = ""
            if "title" in props and isinstance(props["title"], dict):
                title_arr = props["title"].get("title") or []
                title = "".join(t.get("plain_text", "") for t in title_arr if isinstance(t, dict))
            if not title:
                title = p.get("title") or p.get("url") or str(p)[:60]
            icon = p.get("icon") or {}
            emoji = icon.get("emoji") if isinstance(icon, dict) else "📄"
            items.append({"label": title[:80], "icon": emoji or "📄"})

    query = args.get("query", "")
    return list_card(f"📝 Notion: {query}", items) if items else None


def _apps_list_card(result: Any, tool_name: str) -> dict | None:
    apps = []
    if isinstance(result, dict):
        apps = result.get("apps") or result.get("running") or result.get("items") or []
    elif isinstance(result, list):
        apps = result

    if not apps:
        return None

    items = []
    for a in apps[:40]:
        if isinstance(a, dict):
            name = a.get("name") or a.get("app") or str(a)
            sub = a.get("category") or a.get("url") or a.get("pid") or ""
            items.append({"label": name, "sub": str(sub), "icon": "📱"})
        elif isinstance(a, str):
            items.append({"label": a, "icon": "📱"})

    titles = {
        "list_running_apps": "⚙️ Running Apps",
        "find_installed_apps": "📱 Installed Apps",
        "list_available_web_apps": "🌐 Web Apps",
    }
    title = titles.get(tool_name, "Apps")
    return list_card(title, items) if items else None


def _cleanup_card(result: Any) -> dict | None:
    if not isinstance(result, dict):
        return None

    items = []
    files = result.get("files") or result.get("deleted") or result.get("items") or []
    for f in files[:30]:
        if isinstance(f, str):
            items.append({"label": f, "icon": "🗑️"})
        elif isinstance(f, dict):
            items.append({
                "label": f.get("path") or f.get("name") or str(f),
                "sub": f"{f.get('size', 0)//1024} KB" if f.get("size") else "",
                "icon": "🗑️",
            })

    freed = result.get("freed_bytes") or result.get("freed") or 0
    title = f"🧹 Cleanup — {freed//1024//1024:.1f} MB freed" if freed else "🧹 Cleanup"
    return list_card(title, items) if items else None
