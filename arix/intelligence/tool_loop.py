"""
ToolCallingLoop — OpenClaw/OpenFang-style native agentic tool-calling loop.

Instead of: LLM generates a static plan → we execute each step in sequence
Does:        LLM decides which tools to call → calls them → sees results
             → decides next action → calls more tools → ... → done

This is the core of "working like OpenClaw" — the LLM is in the driver's
seat, adapting in real time to what tools actually return.

Supports:
  - Anthropic: native tool_use API (Messages)
  - OpenAI / Gemini (via OpenAI-compat): function_calling tools API
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import AsyncIterator, Callable, Any

log = logging.getLogger(__name__)

# ── Tool input schemas (proper JSON Schema for each tool) ─────────────────────

_STR = {"type": "string"}
_INT = {"type": "integer"}
_BOOL = {"type": "boolean"}
_PATH = {"type": "string", "description": "Absolute path or ~/relative path"}
_REPO = {"type": "string", "description": "Path to the git repository root"}


def _obj(props: dict, required: list | None = None) -> dict:
    s: dict = {"type": "object", "properties": props}
    if required:
        s["required"] = required
    return s


TOOL_SCHEMAS: dict[str, dict] = {
    # ── File tools ───────────────────────────────────────────────────────────
    "list_directory": _obj({"path": _PATH}, ["path"]),
    "create_folder": _obj({"path": _PATH}, ["path"]),
    "create_file": _obj(
        {"path": _PATH, "content": {"type": "string", "description": "File content to write"}},
        ["path", "content"],
    ),
    "read_file": _obj({"path": _PATH}, ["path"]),
    "move_file": _obj({"source": _PATH, "destination": _PATH}, ["source", "destination"]),
    "copy_file": _obj({"source": _PATH, "destination": _PATH}, ["source", "destination"]),
    "search_files": _obj(
        {"path": _PATH, "pattern": {"type": "string", "description": "Glob pattern e.g. *.pdf, *.py"}},
        ["path", "pattern"],
    ),
    "zip_files": _obj(
        {"paths": {"type": "array", "items": _STR, "description": "List of paths to zip"},
         "output": {"type": "string", "description": "Output .zip file path"}},
        ["paths", "output"],
    ),
    "unzip_archive": _obj(
        {"path": _PATH, "destination": {"type": "string", "description": "Extraction directory"}},
        ["path"],
    ),
    "move_to_trash": _obj({"path": _PATH}, ["path"]),

    # ── App tools ────────────────────────────────────────────────────────────
    "open_known_app": _obj(
        {"app_name": {"type": "string", "description": "App name e.g. Chrome, Spotify, Excel"}},
        ["app_name"],
    ),
    "close_app": _obj({"app_name": _STR}, ["app_name"]),
    "list_running_apps": _obj({}),
    "find_installed_apps": _obj({"query": {"type": "string", "description": "Search query"}}, ["query"]),
    "list_available_web_apps": _obj({}),

    # ── System tools ─────────────────────────────────────────────────────────
    "system_monitor": _obj({"detail": {"type": "string", "enum": ["basic", "full"]}}),
    "cleanup_temp_files": _obj(
        {"dry_run": {"type": "boolean", "description": "Preview without deleting"},
         "older_than_days": {"type": "integer", "description": "Delete files older than N days"}},
    ),

    # ── Browser tools ────────────────────────────────────────────────────────
    "browser_open_url": _obj({"url": {"type": "string", "description": "Full URL to open"}}, ["url"]),
    "browser_web_search": _obj({"query": {"type": "string", "description": "Search query"}}, ["query"]),
    "browser_extract_page_text": _obj({"url": _STR}, ["url"]),
    "browser_download_file": _obj({"url": _STR, "destination": _PATH}, ["url", "destination"]),
    "browser_tab_management": _obj({"action": {"type": "string", "enum": ["list", "close_current", "new"]}}),
    "browser_click": _obj({"selector": _STR, "description": _STR}, ["selector"]),
    "browser_type_text": _obj({"selector": _STR, "text": _STR}, ["selector", "text"]),
    "browser_fill_form": _obj({"fields": {"type": "object", "description": "Field selector → value map"}}, ["fields"]),
    "browser_screenshot": _obj({"save_path": _STR}),
    "browser_wait_for_element": _obj({"selector": _STR, "timeout": _INT}, ["selector"]),
    "browser_scroll": _obj({"direction": {"type": "string", "enum": ["up", "down"]}, "amount": _INT}),
    "browser_go_back": _obj({}),
    "browser_get_page_source": _obj({}),
    "browser_get_structured_data": _obj({"data_type": {"type": "string", "description": "Type of data to extract"}}),

    # ── Document tools ───────────────────────────────────────────────────────
    "create_docx": _obj({"path": _PATH, "content": _STR}, ["path", "content"]),
    "read_docx": _obj({"path": _PATH}, ["path"]),
    "create_xlsx": _obj(
        {"path": _PATH, "data": {"type": "object", "description": "Sheet name → list of rows"}},
        ["path", "data"],
    ),
    "read_xlsx": _obj({"path": _PATH}, ["path"]),

    # ── Git tools ────────────────────────────────────────────────────────────
    "git_status": _obj({"repo_path": _REPO}, ["repo_path"]),
    "git_diff": _obj({"repo_path": _REPO}, ["repo_path"]),
    "git_add": _obj(
        {"repo_path": _REPO,
         "paths": {"type": "array", "items": _STR, "description": "Files to stage; empty = all"}},
        ["repo_path"],
    ),
    "git_commit": _obj({"repo_path": _REPO, "message": _STR}, ["repo_path", "message"]),

    # ── Code tools ───────────────────────────────────────────────────────────
    "generate_code": _obj(
        {"description": _STR, "language": {"type": "string", "description": "Programming language"}},
        ["description"],
    ),
    "explain_code": _obj({"code": _STR, "language": _STR}, ["code"]),
    "refactor_code": _obj({"code": _STR, "instruction": _STR}, ["code", "instruction"]),
    "write_tests": _obj({"code": _STR, "language": _STR, "framework": _STR}, ["code"]),
    "analyze_code_quality": _obj({"code": _STR, "language": _STR}, ["code"]),
    "run_code": _obj(
        {"language": {"type": "string", "enum": ["python", "javascript", "bash", "ruby"]},
         "code": _STR},
        ["language", "code"],
    ),

    # ── Research tools ───────────────────────────────────────────────────────
    "research_topic": _obj(
        {"topic": _STR, "depth": {"type": "string", "enum": ["quick", "standard", "deep"]}},
        ["topic"],
    ),
    "summarize_url": _obj({"url": _STR}, ["url"]),

    # ── Vision tools ─────────────────────────────────────────────────────────
    "analyze_image": _obj(
        {"path": _PATH, "question": {"type": "string", "description": "What to analyze/look for"}},
        ["path"],
    ),
    "capture_and_analyze": _obj({"question": _STR}),

    # ── Calendar tools ───────────────────────────────────────────────────────
    "list_calendar_events": _obj(
        {"days_ahead": _INT, "max_results": _INT},
    ),
    "create_calendar_event": _obj(
        {"title": _STR,
         "start": {"type": "string", "description": "ISO 8601 datetime e.g. 2026-06-20T14:00:00"},
         "end": {"type": "string", "description": "ISO 8601 datetime"},
         "description": _STR,
         "location": _STR},
        ["title", "start", "end"],
    ),
    "delete_calendar_event": _obj({"event_id": _STR}, ["event_id"]),

    # ── Web app tools ────────────────────────────────────────────────────────
    "open_web_app": _obj({"app_name": _STR}, ["app_name"]),
    "navigate_web_app": _obj(
        {"app_name": _STR, "destination": {"type": "string", "description": "Section or page to navigate to"}},
        ["app_name", "destination"],
    ),

    # ── WhatsApp ─────────────────────────────────────────────────────────────
    "send_whatsapp_message": _obj({"to": _STR, "message": _STR}, ["to", "message"]),

    # ── Gmail ────────────────────────────────────────────────────────────────
    "gmail_list_emails": _obj({"max_results": _INT, "label": _STR}),
    "gmail_read_email": _obj({"message_id": _STR}, ["message_id"]),
    "gmail_send_email": _obj({"to": _STR, "subject": _STR, "body": _STR}, ["to", "subject", "body"]),
    "gmail_search_emails": _obj({"query": _STR, "max_results": _INT}, ["query"]),
    "gmail_delete_email": _obj({"message_id": _STR}, ["message_id"]),

    # ── Google Drive ─────────────────────────────────────────────────────────
    "drive_list_files": _obj({"max_results": _INT, "folder_id": _STR}),
    "drive_search_files": _obj({"query": _STR, "max_results": _INT}, ["query"]),
    "drive_read_file": _obj({"file_id": _STR}, ["file_id"]),
    "drive_upload_file": _obj({"file_path": _PATH, "folder_id": _STR}, ["file_path"]),

    # ── Notion ───────────────────────────────────────────────────────────────
    "notion_search": _obj({"query": _STR, "max_results": _INT}, ["query"]),
    "notion_read_page": _obj({"page_id": _STR}, ["page_id"]),
    "notion_create_page": _obj(
        {"title": _STR, "content": _STR, "parent_id": _STR},
        ["title", "content"],
    ),
    "notion_append_to_page": _obj({"page_id": _STR, "content": _STR}, ["page_id", "content"]),

    # ── Slack ────────────────────────────────────────────────────────────────
    "slack_list_channels": _obj({}),
    "slack_send_message": _obj({"channel": _STR, "message": _STR}, ["channel", "message"]),
    "slack_get_messages": _obj({"channel": _STR, "limit": _INT}, ["channel"]),
    "slack_search": _obj({"query": _STR}, ["query"]),

    # ── Trello ───────────────────────────────────────────────────────────────
    "trello_list_boards": _obj({}),
    "trello_list_cards": _obj({"list_id": _STR}, ["list_id"]),
    "trello_create_card": _obj({"list_id": _STR, "name": _STR, "desc": _STR}, ["list_id", "name"]),
    "trello_get_lists": _obj({"board_id": _STR}, ["board_id"]),

    # ── Spotify ──────────────────────────────────────────────────────────────
    "spotify_search": _obj(
        {"query": _STR,
         "search_type": {"type": "string", "enum": ["track", "artist", "album", "playlist"]}},
        ["query"],
    ),
    "spotify_current_track": _obj({}),
    "spotify_play_pause": _obj({"action": {"type": "string", "enum": ["play", "pause", "toggle"]}}),

    # ── YouTube ──────────────────────────────────────────────────────────────
    "youtube_search": _obj({"query": _STR, "max_results": _INT}, ["query"]),
    "youtube_get_video": _obj({"video_id": _STR}, ["video_id"]),
    "youtube_search_channels": _obj({"query": _STR}, ["query"]),

    # ── Desktop (bridge) ────────────────────────────────────────────────────
    "desktop_screenshot": _obj({"save_path": _STR}),
    "desktop_click": _obj({"x": _INT, "y": _INT}, ["x", "y"]),
    "desktop_double_click": _obj({"x": _INT, "y": _INT}, ["x", "y"]),
    "desktop_right_click": _obj({"x": _INT, "y": _INT}, ["x", "y"]),
    "desktop_type_text": _obj({"text": _STR}, ["text"]),
    "desktop_key": _obj({"key": _STR}, ["key"]),
    "desktop_scroll": _obj({"x": _INT, "y": _INT, "clicks": _INT}),
    "desktop_move_mouse": _obj({"x": _INT, "y": _INT}, ["x", "y"]),
    "desktop_drag": _obj({"x1": _INT, "y1": _INT, "x2": _INT, "y2": _INT}),
    "desktop_find_and_click": _obj({"label": _STR}, ["label"]),
    "desktop_read_screen": _obj({}),

    # ── RAG Knowledge Base ───────────────────────────────────────────────────
    "ingest_document": _obj({"file_path": _PATH, "doc_name": _STR}, ["file_path"]),
    "query_knowledge_base": _obj({"query": _STR, "top_k": _INT, "doc_filter": _STR}, ["query"]),
}

# ── System prompts ────────────────────────────────────────────────────────────

_LOOP_SYSTEM = """You are Arix — a powerful personal AI computer-control agent with real tool access.

{hand_section}

## How you work
You have access to tools that can control a real computer. Execute the user's request step by step by calling tools.

## Rules
1. Think before each tool call — plan what you need to do
2. Call ONE tool at a time — tools are executed sequentially
3. Use absolute file paths: ~/path/to/file or /absolute/path
4. Read files before writing them if you need to know their current content
5. After each tool result, decide: do you need another tool, or are you done?
6. Be specific — don't use vague paths or partial information
7. If a tool fails, adapt — try an alternative approach
8. When you've completed the task, give a clear summary of what you did

## Important rules for safety
- Never delete files without showing what they are first
- For git operations, always check status before committing
- For emails and messages, show the content before sending
- Prefer ~/Downloads or /tmp for temporary files

{memory_context}
"""

_HAND_SECTION_TEMPLATE = """## Active Capability Hand: {icon} {name}
**Persona:** {persona}

**Expert knowledge for this task:**
{knowledge}
"""


def _build_tool_definitions(tool_dispatch: dict, allowed_tools: list | None = None) -> list[dict]:
    """Convert tool dispatch dict to Anthropic/OpenAI tool definitions."""
    defs = []
    # Get descriptions from TOOL_REGISTRY if available
    try:
        from arix.tools.registry import TOOL_REGISTRY
    except Exception:
        TOOL_REGISTRY = {}

    for name in tool_dispatch:
        if allowed_tools is not None and name not in allowed_tools:
            continue
        schema = TOOL_SCHEMAS.get(name, {"type": "object", "properties": {}})
        description = ""
        if name in TOOL_REGISTRY:
            description = TOOL_REGISTRY[name].description
        else:
            # Humanize from name
            description = name.replace("_", " ").capitalize()
        defs.append({
            "name": name,
            "description": description,
            "input_schema": schema,
        })
    return defs


def _truncate_result(result: Any, max_chars: int = 2000) -> str:
    """Stringify and truncate a tool result for the LLM."""
    try:
        if isinstance(result, dict):
            s = json.dumps(result, default=str)
        elif isinstance(result, (list, tuple)):
            s = json.dumps(result, default=str)
        else:
            s = str(result)
    except Exception:
        s = repr(result)

    if len(s) > max_chars:
        s = s[:max_chars] + f"\n... [truncated, {len(s) - max_chars} chars omitted]"
    return s


# ── Main loop class ───────────────────────────────────────────────────────────

class ToolCallingLoop:
    """
    OpenClaw-style native tool-use agentic loop.

    The LLM drives execution iteratively:
      user message → LLM thinks → calls tool → sees result → thinks → calls tool → ... → done

    Supports Anthropic (native tool_use) and OpenAI/Gemini (function_calling).
    """

    MAX_ITERATIONS = 12
    MAX_TOKENS = 2000

    def __init__(
        self,
        llm_client: Any,
        tool_dispatch: dict,
        max_iterations: int = 12,
    ):
        self.llm = llm_client
        self.tool_dispatch = tool_dispatch
        self.max_iterations = max_iterations

    async def _execute_tool(self, name: str, args: dict) -> Any:
        """Execute a tool by name, checking the read-only cache first."""
        from arix import tool_cache as _tc
        cached = _tc.get(name, args)
        if cached is not None:
            return cached
        fn = self.tool_dispatch.get(name)
        if fn is None:
            return {"error": f"Tool '{name}' not found"}
        try:
            result = await asyncio.to_thread(fn, args)
            _tc.put(name, args, result)
            return result
        except Exception as e:
            return {"error": str(e)}

    async def run(
        self,
        command: str,
        task_id: str,
        hand=None,
        user_context: str = "",
        allowed_tools: list | None = None,
    ) -> AsyncIterator[tuple[str, dict]]:
        """
        Async generator yielding (event_type, data) tuples.

        Event types:
          tool_loop_start     — loop beginning
          tool_loop_thinking  — LLM text before tool call
          tool_loop_call      — tool is being called
          tool_loop_result    — tool result received
          tool_loop_done      — final LLM text answer
          tool_loop_error     — unrecoverable error
        """
        # Build system prompt
        hand_section = ""
        if hand is not None:
            knowledge_bullets = "\n".join(
                f"  • {k}" for k in (hand.knowledge or [])[:8]
            )
            hand_section = _HAND_SECTION_TEMPLATE.format(
                icon=hand.icon,
                name=hand.name,
                persona=hand.persona,
                knowledge=knowledge_bullets,
            )

        memory_section = ""
        if user_context:
            memory_section = f"## User context\n{user_context}"

        system = _LOOP_SYSTEM.format(
            hand_section=hand_section,
            memory_context=memory_section,
        ).strip()

        # Build tool definitions
        tool_defs = _build_tool_definitions(self.tool_dispatch, allowed_tools)

        yield ("tool_loop_start", {
            "task_id": task_id,
            "hand": hand.name if hand else None,
            "tool_count": len(tool_defs),
        })

        provider = getattr(self.llm, "provider", "unknown")

        if provider == "anthropic":
            async for event in self._run_anthropic(
                command, task_id, system, tool_defs
            ):
                yield event
        else:
            # OpenAI-compatible: OpenAI, Gemini
            async for event in self._run_openai_compat(
                command, task_id, system, tool_defs
            ):
                yield event

    # ── Anthropic native tool_use ─────────────────────────────────────────────

    async def _run_anthropic(
        self, command: str, task_id: str, system: str, tool_defs: list
    ) -> AsyncIterator[tuple[str, dict]]:
        import anthropic
        import os

        base_url = os.environ.get("AI_INTEGRATIONS_ANTHROPIC_BASE_URL")
        api_key = (
            os.environ.get("AI_INTEGRATIONS_ANTHROPIC_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY")
            or self.llm.api_key
        )
        client_kwargs: dict = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = anthropic.AsyncAnthropic(**client_kwargs)

        messages: list[dict] = [{"role": "user", "content": command}]
        model = getattr(self.llm, "model", "claude-opus-4-5")

        for iteration in range(self.max_iterations):
            try:
                response = await client.messages.create(
                    model=model,
                    max_tokens=self.MAX_TOKENS,
                    system=system,
                    tools=tool_defs,
                    messages=messages,
                )
            except Exception as e:
                yield ("tool_loop_error", {
                    "task_id": task_id,
                    "error": str(e),
                    "iteration": iteration,
                })
                return

            # Collect tool_use blocks and text blocks
            tool_use_blocks = []
            text_blocks = []
            for block in response.content:
                if hasattr(block, "type"):
                    if block.type == "text" and block.text.strip():
                        text_blocks.append(block.text)
                    elif block.type == "tool_use":
                        tool_use_blocks.append(block)

            # Emit any thinking text
            for text in text_blocks:
                if response.stop_reason == "end_turn" or not tool_use_blocks:
                    yield ("tool_loop_done", {
                        "task_id": task_id,
                        "text": text,
                        "iterations": iteration + 1,
                    })
                else:
                    yield ("tool_loop_thinking", {
                        "task_id": task_id,
                        "text": text,
                        "iteration": iteration + 1,
                    })

            # If done, stop
            if response.stop_reason == "end_turn" or not tool_use_blocks:
                if not text_blocks:
                    yield ("tool_loop_done", {
                        "task_id": task_id,
                        "text": "Task completed.",
                        "iterations": iteration + 1,
                    })
                return

            # Emit all call announcements first (parallel batch)
            tool_calls_info = []
            for block in tool_use_blocks:
                tool_name = block.name
                tool_args = dict(block.input) if block.input else {}
                tool_calls_info.append((block, tool_name, tool_args))
                yield ("tool_loop_call", {
                    "task_id": task_id,
                    "tool": tool_name,
                    "args": {k: str(v)[:120] for k, v in tool_args.items()},
                    "iteration": iteration + 1,
                    "parallel": len(tool_use_blocks) > 1,
                })

            # Execute ALL tool calls in parallel (asyncio.gather)
            raw_results = await asyncio.gather(*[
                self._execute_tool(tn, ta)
                for (_, tn, ta) in tool_calls_info
            ])

            tool_results = []
            for (block, tool_name, tool_args), result in zip(tool_calls_info, raw_results):
                result_text = _truncate_result(result)
                success = "error" not in str(result_text).lower()[:50]

                # Try to emit an A2UI card for rich visual rendering
                a2ui_card = None
                try:
                    from arix.intelligence.a2ui import result_to_card
                    a2ui_card = result_to_card(tool_name, tool_args, result)
                except Exception:
                    pass

                yield ("tool_loop_result", {
                    "task_id": task_id,
                    "tool": tool_name,
                    "result_preview": result_text[:300],
                    "success": success,
                })

                if a2ui_card:
                    yield ("a2ui_card", {
                        "task_id": task_id,
                        "tool": tool_name,
                        "card": a2ui_card,
                    })

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                })

            # Add assistant turn + tool results to messages
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        # Hit max iterations
        yield ("tool_loop_error", {
            "task_id": task_id,
            "error": f"Reached max iterations ({self.max_iterations}). Task may be incomplete.",
        })

    # ── OpenAI-compatible tool_calling (OpenAI + Gemini) ─────────────────────

    async def _run_openai_compat(
        self, command: str, task_id: str, system: str, tool_defs: list
    ) -> AsyncIterator[tuple[str, dict]]:
        import openai
        import os

        provider = getattr(self.llm, "provider", "openai")
        api_key = self.llm.api_key
        base_url = None
        if provider == "gemini":
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        model = getattr(self.llm, "model", "gpt-4o")

        client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

        # Convert Anthropic-style tool defs → OpenAI format
        oai_tools = [
            {
                "type": "function",
                "function": {
                    "name": td["name"],
                    "description": td["description"],
                    "parameters": td["input_schema"],
                },
            }
            for td in tool_defs
        ]

        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": command})

        for iteration in range(self.max_iterations):
            try:
                response = await client.chat.completions.create(
                    model=model,
                    max_tokens=self.MAX_TOKENS,
                    tools=oai_tools,
                    tool_choice="auto",
                    messages=messages,
                )
            except Exception as e:
                yield ("tool_loop_error", {
                    "task_id": task_id,
                    "error": str(e),
                    "iteration": iteration,
                })
                return

            choice = response.choices[0]
            msg = choice.message

            # Add assistant message to history
            messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in (msg.tool_calls or [])
                ] or None,
            })

            # Emit thinking text
            if msg.content and msg.content.strip():
                if choice.finish_reason == "stop" or not msg.tool_calls:
                    yield ("tool_loop_done", {
                        "task_id": task_id,
                        "text": msg.content,
                        "iterations": iteration + 1,
                    })
                    return
                else:
                    yield ("tool_loop_thinking", {
                        "task_id": task_id,
                        "text": msg.content,
                        "iteration": iteration + 1,
                    })

            # If done
            if choice.finish_reason == "stop" or not msg.tool_calls:
                if not (msg.content and msg.content.strip()):
                    yield ("tool_loop_done", {
                        "task_id": task_id,
                        "text": "Task completed.",
                        "iterations": iteration + 1,
                    })
                return

            # Parse all tool calls first
            parsed_calls = []
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    tool_args = {}
                parsed_calls.append((tc, tool_name, tool_args))
                yield ("tool_loop_call", {
                    "task_id": task_id,
                    "tool": tool_name,
                    "args": {k: str(v)[:120] for k, v in tool_args.items()},
                    "iteration": iteration + 1,
                    "parallel": len(msg.tool_calls) > 1,
                })

            # Execute ALL tool calls in parallel
            raw_results = await asyncio.gather(*[
                self._execute_tool(tn, ta) for (_, tn, ta) in parsed_calls
            ])

            for (tc, tool_name, tool_args), result in zip(parsed_calls, raw_results):
                result_text = _truncate_result(result)
                success = "error" not in str(result_text).lower()[:50]

                yield ("tool_loop_result", {
                    "task_id": task_id,
                    "tool": tool_name,
                    "result_preview": result_text[:300],
                    "success": success,
                })

                # A2UI card
                try:
                    from arix.intelligence.a2ui import result_to_card
                    card = result_to_card(tool_name, tool_args, result)
                    if card:
                        yield ("a2ui_card", {"task_id": task_id, "tool": tool_name, "card": card})
                except Exception:
                    pass

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_text,
                })

        yield ("tool_loop_error", {
            "task_id": task_id,
            "error": f"Reached max iterations ({self.max_iterations}). Task may be incomplete.",
        })
