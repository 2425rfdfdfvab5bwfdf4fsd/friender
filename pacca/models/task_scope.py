"""TaskScope — derived from user command before any external content is processed."""
from __future__ import annotations
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from pacca.config import UserConfig


class TaskScopeError(Exception):
    pass


DOMAIN_TOOL_MAP: dict[str, frozenset[str]] = {
    "file": frozenset({
        "list_directory", "create_folder", "create_file", "read_file",
        "move_file", "copy_file", "search_files", "unzip_archive", "zip_files",
        "move_to_trash",
    }),
    "app": frozenset({
        "open_known_app", "close_app", "list_running_apps",
    }),
    "system": frozenset({
        "system_monitor",
    }),
    "calendar": frozenset({
        "list_calendar_events", "create_calendar_event", "delete_calendar_event",
    }),
    "browser": frozenset({
        "browser_open_url", "browser_web_search", "browser_extract_page_text",
        "browser_download_file", "browser_tab_management",
        "browser_click", "browser_type_text", "browser_fill_form",
        "browser_screenshot", "browser_wait_for_element", "browser_scroll",
        "browser_go_back", "browser_get_page_source", "browser_get_structured_data",
    }),
    "document": frozenset({
        "create_docx", "read_docx", "create_xlsx", "read_xlsx",
    }),
    "git": frozenset({
        "git_status", "git_diff", "git_add", "git_commit",
    }),
    "messaging": frozenset({
        "send_whatsapp_message",
    }),
    "vision": frozenset({
        "analyze_image", "capture_and_analyze",
    }),
    "coding": frozenset({
        "generate_code", "explain_code", "refactor_code", "write_tests",
        "analyze_code_quality", "run_code",
    }),
    "research": frozenset({
        "research_topic", "summarize_url",
    }),
}

INTENT_VERB_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\b(move|mv|relocate|transfer)\b', re.I), "move"),
    (re.compile(r'\b(copy|cp|duplicate|clone)\b', re.I), "copy"),
    (re.compile(r'\b(delete|remove|trash|discard)\b', re.I), "delete"),
    (re.compile(r'\b(read|open|show|display|view|print|cat|list|find|search|look)\b', re.I), "read"),
    (re.compile(r'\b(create|make|new|write|generate|build)\b', re.I), "create"),
    (re.compile(r'\b(download|fetch|get|retrieve)\b', re.I), "download"),
    (re.compile(r'\b(git|commit|diff|stage|add)\b', re.I), "git"),
    (re.compile(r'\b(browse|navigate|visit|go to|open url|web|search web|google)\b', re.I), "browse"),
    (re.compile(r'\b(zip|unzip|extract|compress|archive)\b', re.I), "archive"),
    (re.compile(r'\b(monitor|cpu|ram|memory|disk|process|system)\b', re.I), "monitor"),
    (re.compile(r'\b(send|message|notify|text|whatsapp)\b', re.I), "send"),
]

DOMAIN_KEYWORD_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\b(http|https|url|web|browser|website|page|google|search online|click|navigate|fill form|screenshot)\b', re.I), "browser"),
    (re.compile(r'\b(git|commit|diff|stage|repo|repository|branch)\b', re.I), "git"),
    (re.compile(r'\b(docx|xlsx|word|excel|spreadsheet|document)\b', re.I), "document"),
    (re.compile(r'\b(app|application|program|launch|quit|close|open\s+\w*(?:app|chrome|firefox|safari|terminal|finder|explorer|slack|spotify|vscode|code|notepad|calculator|mail|outlook|zoom|teams))\b', re.I), "app"),
    (re.compile(r'\b(cpu|ram|memory|disk|process|system monitor|system info|system status|system check|system stats|system resources|uptime|resources|hardware|performance|sysmon|stats)\b', re.I), "system"),
    (re.compile(r'\b(calendar|event|schedule|meeting|appointment|reminder|agenda|gcal|google calendar|add event|create event|book|booking|due date|deadlines?)\b', re.I), "calendar"),
    (re.compile(r'\b(files?|folders?|directory|directories|path|\.pdf|\.txt|\.py|\.js|\.zip|\.csv|\.json|\.md|\.log|\.env)\b', re.I), "file"),
    (re.compile(r'\b(search|find|look for|locate)\b.{0,30}\b(files?|folders?|directory|content|text|code)\b', re.I), "file"),
    (re.compile(r'\b(whatsapp|send message|notify|notification|text message)\b', re.I), "messaging"),
    (re.compile(r'\b(image|photo|picture|screenshot|vision|analyze image|describe image|capture)\b', re.I), "vision"),
    (re.compile(r'\b(generate code|generate_code|write code|code for|explain code|refactor|unit test|code quality|programming)\b', re.I), "coding"),
    (re.compile(r'\b(research|investigate|summarize url|summarize website|web research|find info about)\b', re.I), "research"),
]


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


@dataclass
class TaskScope:
    task_id: str
    raw_command: str
    redacted_command: str
    intent_verb: str
    intent_domain: Literal["file", "app", "system", "calendar", "browser", "document", "git", "messaging", "vision", "coding", "research", "mixed"]
    allowed_tools: frozenset
    allowed_path_prefixes: tuple
    allowed_url_patterns: tuple | None
    max_steps: int
    scope_digest: str
    created_at: float
    created_monotonic: float
    created_by: Literal["command_parser"] = "command_parser"
    dry_run: bool = False

    @staticmethod
    def derive(task_id: str, command: str, redacted_command: str,
               allowed_path_prefixes: list[str],
               max_steps: int = 30) -> "TaskScope":
        verb = _detect_verb(command)
        domains = _detect_domains(command)

        if len(domains) == 0:
            domains = {"file"}
        if len(domains) == 1:
            domain = list(domains)[0]
        else:
            domain = "mixed"

        if domain == "mixed":
            allowed_tools = frozenset().union(*[DOMAIN_TOOL_MAP[d] for d in domains])
        else:
            allowed_tools = DOMAIN_TOOL_MAP.get(domain, DOMAIN_TOOL_MAP["file"])

        url_patterns: tuple | None = None
        if "browser" in domains:
            url_patterns = ("https://", "http://")

        canonical = json.dumps({
            "task_id": task_id,
            "redacted_command": redacted_command,
            "intent_verb": verb,
            "intent_domain": domain,
            "allowed_tools": sorted(allowed_tools),
            "allowed_path_prefixes": sorted(allowed_path_prefixes),
            "allowed_url_patterns": sorted(url_patterns) if url_patterns else None,
            "max_steps": max_steps,
        }, sort_keys=True, separators=(",", ":"))

        return TaskScope(
            task_id=task_id,
            raw_command=command,
            redacted_command=redacted_command,
            intent_verb=verb,
            intent_domain=domain,
            allowed_tools=allowed_tools,
            allowed_path_prefixes=tuple(sorted(allowed_path_prefixes)),
            allowed_url_patterns=url_patterns,
            max_steps=max_steps,
            scope_digest=_sha256(canonical),
            created_at=time.time(),
            created_monotonic=time.monotonic(),
        )


def _detect_verb(command: str) -> str:
    for pattern, verb in INTENT_VERB_PATTERNS:
        if pattern.search(command):
            return verb
    return "execute"


def _detect_domains(command: str) -> set[str]:
    found: set[str] = set()
    for pattern, domain in DOMAIN_KEYWORD_PATTERNS:
        if pattern.search(command):
            found.add(domain)
    return found
