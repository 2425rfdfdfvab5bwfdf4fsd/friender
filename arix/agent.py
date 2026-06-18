"""Arix Agent — orchestrates the full pipeline for each user command."""
from __future__ import annotations
import asyncio
import hashlib
import json
import os
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Any

from arix.config import ArixConfig, get_grant_secret_key
from arix.personal.profile import UserProfile
from arix.pipeline.heuristic_planner import HeuristicPlanner
from arix.models.audit_log import AuditLogger
from arix.models.provider_consent import ConsentStore
from arix.models.task_scope import TaskScope
from arix.pipeline.command_parser import CommandParser
from arix.pipeline.content_gateway import ContentDataGateway
from arix.pipeline.plan_validator import PlanValidator, PlanValidationError
from arix.pipeline.policy_engine import PolicyEngine
from arix.pipeline.risk_evaluator import CumulativePlanRiskEvaluator, RiskScore
from arix.pipeline.runtime_validator import RuntimeStepValidator, RuntimeValidationError
from arix.pipeline.task_state_machine import TaskStateMachine, TaskState
from arix.security.grant_verifier import GrantVerifier
from arix.security.local_text_redactor import LocalTextRedactor
from arix.security.safe_resource_resolver import SafeResourceResolver
from arix.security.used_grant_registry import UsedGrantRegistry
from arix.memory.task_history import TaskHistory
from arix.tools.registry import TOOL_REGISTRY, policy_version
from arix.memory.undo_manager import UndoManager, make_move_undo, make_create_undo, make_create_folder_undo
from arix.intelligence.advisor import AdvisoryIntentDetector, is_chitchat
from arix.llm_client import LLMClient
from arix.memory.memory_manager import MemoryManager
from arix.intelligence.supervisor import GoalSupervisor, is_multi_step_goal
from arix.intelligence.curator import get_curator
from arix.intelligence.multi_agent_router import get_router
from arix.memory.rag_ingester import get_knowledge_base
from arix.hands.catalog import get_hand_manager
from arix.mcp_client import get_mcp_manager
from arix.intelligence.tool_loop import ToolCallingLoop

import arix.tools.file_tools as file_tools
import arix.tools.app_tools as app_tools
import arix.tools.system_tools as system_tools
import arix.tools.browser_tools as browser_tools
import arix.tools.document_tools as document_tools
import arix.tools.git_tools as git_tools
import arix.tools.whatsapp_tools as whatsapp_tools
import arix.tools.vision_tools as vision_tools
import arix.tools.code_tools as code_tools
import arix.tools.research_tools as research_tools
import arix.tools.calendar_tools as calendar_tools
import arix.tools.desktop_tools as desktop_tools
import arix.tools.webapp_tools as webapp_tools
import arix.tools.gmail_tools as gmail_tools
import arix.tools.drive_tools as drive_tools
import arix.tools.notion_tools as notion_tools
import arix.tools.slack_tools as slack_tools
import arix.tools.trello_tools as trello_tools
import arix.tools.spotify_tools as spotify_tools
import arix.tools.youtube_tools as youtube_tools


@dataclass
class AgentEvent:
    type: str
    data: dict
    timestamp: float = field(default_factory=time.time)


TOOL_DISPATCH: dict[str, Callable] = {
    "list_directory": lambda args: file_tools.list_directory(**_clean(args)),
    "create_folder": lambda args: file_tools.create_folder(**_clean(args)),
    "create_file": lambda args: file_tools.create_file(**_clean(args)),
    "read_file": lambda args: file_tools.read_file(**_clean(args)),
    "move_file": lambda args: file_tools.move_file(**_clean(args)),
    "copy_file": lambda args: file_tools.copy_file(**_clean(args)),
    "search_files": lambda args: file_tools.search_files(**_clean(args)),
    "unzip_archive": lambda args: file_tools.unzip_archive(**_clean(args)),
    "zip_files": lambda args: file_tools.zip_files(**_clean(args)),
    "move_to_trash": lambda args: file_tools.move_to_trash(**_clean(args)),
    "open_known_app": lambda args: app_tools.open_known_app(**_clean(args)),
    "close_app": lambda args: app_tools.close_app(**_clean(args)),
    "list_running_apps": lambda args: app_tools.list_running_apps(),
    "system_monitor": lambda args: system_tools.system_monitor(**_clean(args)),
    "browser_open_url": lambda args: browser_tools.browser_open_url(**_clean(args)),
    "browser_web_search": lambda args: browser_tools.browser_web_search(**_clean(args)),
    "browser_extract_page_text": lambda args: browser_tools.browser_extract_page_text(**_clean(args)),
    "browser_download_file": lambda args: browser_tools.browser_download_file(**_clean(args)),
    "browser_tab_management": lambda args: browser_tools.browser_tab_management(**_clean(args)),
    "browser_click": lambda args: browser_tools.browser_click(**_clean(args)),
    "browser_type_text": lambda args: browser_tools.browser_type_text(**_clean(args)),
    "browser_fill_form": lambda args: browser_tools.browser_fill_form(**_clean(args)),
    "browser_screenshot": lambda args: browser_tools.browser_screenshot(**_clean(args)),
    "browser_wait_for_element": lambda args: browser_tools.browser_wait_for_element(**_clean(args)),
    "browser_scroll": lambda args: browser_tools.browser_scroll(**_clean(args)),
    "browser_go_back": lambda args: browser_tools.browser_go_back(**_clean(args)),
    "browser_get_page_source": lambda args: browser_tools.browser_get_page_source(**_clean(args)),
    "browser_get_structured_data": lambda args: browser_tools.browser_get_structured_data(**_clean(args)),
    "create_docx": lambda args: document_tools.create_docx(**_clean(args)),
    "read_docx": lambda args: document_tools.read_docx(**_clean(args)),
    "create_xlsx": lambda args: document_tools.create_xlsx(**_clean(args)),
    "read_xlsx": lambda args: document_tools.read_xlsx(**_clean(args)),
    "git_status": lambda args: git_tools.git_status(**_clean(args)),
    "git_diff": lambda args: git_tools.git_diff(**_clean(args)),
    "git_add": lambda args: git_tools.git_add(**_clean(args)),
    "git_commit": lambda args: git_tools.git_commit(**_clean(args)),
    "send_whatsapp_message": lambda args: whatsapp_tools.send_whatsapp_message(**_clean(args)),
    # Vision tools
    "analyze_image": lambda args: vision_tools.analyze_image(**_clean(args)),
    "capture_and_analyze": lambda args: vision_tools.capture_and_analyze(**_clean(args)),
    # Coding Agent tools
    "generate_code": lambda args: code_tools.generate_code(**_clean(args)),
    "explain_code": lambda args: code_tools.explain_code(**_clean(args)),
    "refactor_code": lambda args: code_tools.refactor_code(**_clean(args)),
    "write_tests": lambda args: code_tools.write_tests(**_clean(args)),
    "analyze_code_quality": lambda args: code_tools.analyze_code_quality(**_clean(args)),
    # Research Agent tools
    "research_topic": lambda args: research_tools.research_topic(**_clean(args)),
    "summarize_url": lambda args: research_tools.summarize_url(**_clean(args)),
    "search_knowledge_base": lambda args: research_tools.search_knowledge_base(**_clean(args)),
    # Sandbox code execution (Gap #1)
    "run_code": lambda args: code_tools.run_code(**_clean(args)),
    # Google Calendar tools
    "list_calendar_events": lambda args: calendar_tools.list_calendar_events(**_clean(args)),
    "create_calendar_event": lambda args: calendar_tools.create_calendar_event(**_clean(args)),
    "delete_calendar_event": lambda args: calendar_tools.delete_calendar_event(**_clean(args)),
    # Digital Employee tools
    "cleanup_temp_files": lambda args: system_tools.cleanup_temp_files(**_clean(args)),
    "open_web_app": lambda args: webapp_tools.open_web_app(**_clean(args)),
    "navigate_web_app": lambda args: webapp_tools.navigate_web_app(**_clean(args)),
    "find_installed_apps": lambda args: app_tools.find_installed_apps(**_clean(args)),
    "list_available_web_apps": lambda args: webapp_tools.list_available_web_apps(),
    # Gmail tools
    "gmail_list_emails": lambda args: gmail_tools.gmail_list_emails(**_clean(args)),
    "gmail_read_email": lambda args: gmail_tools.gmail_read_email(**_clean(args)),
    "gmail_send_email": lambda args: gmail_tools.gmail_send_email(**_clean(args)),
    "gmail_search_emails": lambda args: gmail_tools.gmail_search_emails(**_clean(args)),
    "gmail_delete_email": lambda args: gmail_tools.gmail_delete_email(**_clean(args)),
    # Google Drive tools
    "drive_list_files": lambda args: drive_tools.drive_list_files(**_clean(args)),
    "drive_search_files": lambda args: drive_tools.drive_search_files(**_clean(args)),
    "drive_read_file": lambda args: drive_tools.drive_read_file(**_clean(args)),
    "drive_upload_file": lambda args: drive_tools.drive_upload_file(**_clean(args)),
    # Notion tools
    "notion_search": lambda args: notion_tools.notion_search(**_clean(args)),
    "notion_read_page": lambda args: notion_tools.notion_read_page(**_clean(args)),
    "notion_create_page": lambda args: notion_tools.notion_create_page(**_clean(args)),
    "notion_append_to_page": lambda args: notion_tools.notion_append_to_page(**_clean(args)),
    # Slack tools
    "slack_list_channels": lambda args: slack_tools.slack_list_channels(**_clean(args)),
    "slack_send_message": lambda args: slack_tools.slack_send_message(**_clean(args)),
    "slack_get_messages": lambda args: slack_tools.slack_get_messages(**_clean(args)),
    "slack_search": lambda args: slack_tools.slack_search(**_clean(args)),
    # Trello tools
    "trello_list_boards": lambda args: trello_tools.trello_list_boards(**_clean(args)),
    "trello_list_cards": lambda args: trello_tools.trello_list_cards(**_clean(args)),
    "trello_create_card": lambda args: trello_tools.trello_create_card(**_clean(args)),
    "trello_get_lists": lambda args: trello_tools.trello_get_lists(**_clean(args)),
    # Spotify tools
    "spotify_search": lambda args: spotify_tools.spotify_search(**_clean(args)),
    "spotify_current_track": lambda args: spotify_tools.spotify_current_track(**_clean(args)),
    "spotify_play_pause": lambda args: spotify_tools.spotify_play_pause(**_clean(args)),
    # YouTube tools
    "youtube_search": lambda args: youtube_tools.youtube_search(**_clean(args)),
    "youtube_get_video": lambda args: youtube_tools.youtube_get_video(**_clean(args)),
    "youtube_search_channels": lambda args: youtube_tools.youtube_search_channels(**_clean(args)),
    # Desktop tools (via local bridge agent)
    "desktop_screenshot": lambda args: desktop_tools.desktop_screenshot(**_clean(args)),
    "desktop_click": lambda args: desktop_tools.desktop_click(**_clean(args)),
    "desktop_double_click": lambda args: desktop_tools.desktop_double_click(**_clean(args)),
    "desktop_right_click": lambda args: desktop_tools.desktop_right_click(**_clean(args)),
    "desktop_type_text": lambda args: desktop_tools.desktop_type_text(**_clean(args)),
    "desktop_key": lambda args: desktop_tools.desktop_key(**_clean(args)),
    "desktop_scroll": lambda args: desktop_tools.desktop_scroll(**_clean(args)),
    "desktop_move_mouse": lambda args: desktop_tools.desktop_move_mouse(**_clean(args)),
    "desktop_drag": lambda args: desktop_tools.desktop_drag(**_clean(args)),
    "desktop_find_and_click": lambda args: desktop_tools.desktop_find_and_click(**_clean(args)),
    "desktop_read_screen": lambda args: desktop_tools.desktop_read_screen(**_clean(args)),
    # v8.4: RAG Knowledge Base tools
    "ingest_document": lambda args: get_knowledge_base().ingest(
        file_path=args.get("file_path", ""),
        doc_name=args.get("doc_name"),
    ),
    "query_knowledge_base": lambda args: get_knowledge_base().query(
        query_text=args.get("query", ""),
        top_k=int(args.get("top_k", 5)),
        doc_filter=args.get("doc_filter"),
    ),
}

# Tools whose results can feed the undo manager
_UNDO_BUILDERS: dict[str, Callable[[dict, dict], tuple[str, Callable] | None]] = {}


def _clean(args: dict) -> dict:
    return {k: v for k, v in args.items() if not k.startswith("_resolved_")}


def _try_register_undo(undo_mgr: UndoManager, task_id: str, step_id: str,
                        tool_name: str, args: dict, result: dict) -> None:
    """Attempt to register an undo action for a successful tool call."""
    try:
        if tool_name == "create_file" and not result.get("error"):
            path = args.get("path", "")
            if path:
                undo_mgr.record(
                    task_id=task_id, step_id=step_id, tool_name=tool_name,
                    description=f"Created file: {path}",
                    undo_fn=make_create_undo(path),
                    undo_description=f"Delete {path}",
                )
        elif tool_name == "create_folder" and not result.get("error"):
            path = args.get("path", "")
            if path:
                undo_mgr.record(
                    task_id=task_id, step_id=step_id, tool_name=tool_name,
                    description=f"Created folder: {path}",
                    undo_fn=make_create_folder_undo(path),
                    undo_description=f"Remove folder {path}",
                )
        elif tool_name == "move_file" and not result.get("error"):
            src = args.get("source", "")
            dst = args.get("destination", "")
            final = result.get("destination", dst)
            if src and final:
                undo_mgr.record(
                    task_id=task_id, step_id=step_id, tool_name=tool_name,
                    description=f"Moved {src} → {final}",
                    undo_fn=make_move_undo(src_final=final, src_original=src),
                    undo_description=f"Move back to {src}",
                )
    except Exception:
        pass


class ArixAgent:
    def __init__(self, config: ArixConfig | None = None):
        self.config = config or ArixConfig.load()
        self._secret_key = get_grant_secret_key()
        self._policy_version = policy_version()

        self.redactor = LocalTextRedactor()
        self.resolver = SafeResourceResolver(secret_key=self._secret_key)
        self.consent_store = ConsentStore()
        self.audit_logger = AuditLogger(
            path_mode=self.config.audit_log_path_mode,
            retention_days=self.config.audit_log_retention_days,
        )
        self.grant_registry = UsedGrantRegistry()
        self.grant_verifier = GrantVerifier(
            registry=self.grant_registry,
            secret_key=self._secret_key,
            current_policy_version=self._policy_version,
        )
        self.command_parser = CommandParser(
            redactor=self.redactor,
            allowed_path_prefixes=self.config.allowed_path_prefixes,
        )
        self.plan_validator = PlanValidator(
            resolver=self.resolver,
            tool_registry=TOOL_REGISTRY,
        )
        self.risk_evaluator = CumulativePlanRiskEvaluator(
            proceed_threshold=self.config.risk_proceed_threshold,
            confirm_threshold=self.config.risk_confirm_threshold,
        )
        self.policy_engine = PolicyEngine(
            secret_key=self._secret_key,
            tool_registry=TOOL_REGISTRY,
            policy_version=self._policy_version,
        )
        self.runtime_validator = RuntimeStepValidator(
            grant_verifier=self.grant_verifier,
            resolver=self.resolver,
            tool_registry=TOOL_REGISTRY,
        )
        self.state_machine = TaskStateMachine(
            on_transition=self._on_state_transition,
        )
        self.undo_manager = UndoManager(max_depth=50)
        self.task_history = TaskHistory()
        self.heuristic_planner = HeuristicPlanner()
        self.advisory_detector = AdvisoryIntentDetector()
        self.memory = MemoryManager()

        llm_client: LLMClient | None = None
        if not self.config.offline_mode:
            llm_client = LLMClient(
                provider=self.config.provider,
                model=self.config.model,
                api_key=None,
            )
        self.llm_client = llm_client

        # Wire LLM client into AI-powered tool modules
        if llm_client is not None:
            vision_tools.set_llm_client(llm_client)
            code_tools.set_llm_client(llm_client)
            research_tools.set_llm_client(llm_client)
            browser_tools.set_llm_client(llm_client)  # Gap #4: vision-click fallback

        # Gap #2 (neural vector memory): wire OpenAI sync client into VectorIndex
        # Uses OPENAI_API_KEY directly — independent of the main LLM provider choice.
        _openai_key = os.environ.get("OPENAI_API_KEY", "")
        if _openai_key:
            try:
                import openai as _openai
                self.memory.set_embedding_provider(_openai.OpenAI(api_key=_openai_key))
            except Exception:
                pass  # openai not installed or key invalid — VectorIndex stays on TF-IDF

        # Wire memory manager into research tools so reports are auto-persisted
        research_tools.set_memory_manager(self.memory)

        self.gateway = ContentDataGateway(
            redactor=self.redactor,
            consent_store=self.consent_store,
            llm_client=llm_client,
            provider_id=self.config.provider,
            max_file_egress_bytes=self.config.max_file_egress_bytes,
        )

        self.supervisor = GoalSupervisor(
            run_command_fn=self.run_command,
            max_retries=3,       # attempt 0 + self-heal + LLM reflection
            goal_timeout=600.0,
            max_depth=3,
        )
        if llm_client is not None:
            self.supervisor.set_llm_client(llm_client)
        self.supervisor.set_memory(self.memory)  # Gap #12: skill saving after goal

        # ── v8.4: OpenClaw-inspired upgrades ─────────────────────────────────

        # Hermes Curator — autonomous skill self-improvement loop
        self.curator = get_curator()
        self.curator.set_task_history(self.task_history)
        if llm_client is not None:
            self.curator.set_llm_client(llm_client)

        # Multi-Agent Router — specialist agent dispatch
        self.agent_router = get_router()
        if llm_client is not None:
            self.agent_router.set_llm_client(llm_client)
        self.agent_router.set_command_fn(self.run_command)

        # RAG Knowledge Base — document ingestion + BM25 retrieval
        self.knowledge_base = get_knowledge_base()
        if _openai_key:
            try:
                import openai as _openai2
                self.knowledge_base.set_embedding_provider(_openai2.OpenAI(api_key=_openai_key))
            except Exception:
                pass

        # Capability Hands — OpenFang-style autonomous capability packs
        self.hand_manager = get_hand_manager()

        # MCP Client — Model Context Protocol tool server manager
        self.mcp_manager = get_mcp_manager()

        # ── Gap #8: per-task execution trace store (task_id → list of trace entries)
        self._trace: dict[str, list] = {}

        # Gap #7: per-task skip-step sets (task_id → set of step_ids to skip)
        self._skip_steps: dict[str, set] = {}

        # Confirmation gates: key = "task_id:confirmation_id" → asyncio.Queue(1)
        self._confirmation_gates: dict[str, asyncio.Queue] = {}
        # Goal emit queues: goal_id → asyncio.Queue for supervisor events
        self._goal_queues: dict[str, asyncio.Queue] = {}

    def _on_state_transition(self, task_id: str, old: TaskState, new: TaskState) -> None:
        self.audit_logger.log_event(
            task_id=task_id,
            step_id="state_machine",
            event_type="state_transition",
            state_from=old.value,
            state_to=new.value,
        )

    async def _run_curator_async(self) -> None:
        """Run Hermes-style Curator loop in the background (non-blocking)."""
        try:
            curator = get_curator()
            curator.set_llm_client(self.llm_client)
            curator.set_task_history(getattr(self, "task_history", None))
            result = await curator.run_loop()
            log.info(
                "Curator run #%s complete — created=%s refined=%s pruned=%s core=%s",
                result.get("run_number"),
                result.get("stage_2_created"),
                result.get("stage_3_refined"),
                result.get("stage_4_pruned"),
                result.get("core_skills"),
            )
        except Exception as e:
            log.warning("Curator run error: %s", e)

    async def run_command(self, command: str,
                          task_id: str | None = None) -> AsyncIterator[AgentEvent]:
        task_id = task_id or str(uuid.uuid4())
        queue: asyncio.Queue = asyncio.Queue()

        # Gap #8: Initialize trace store for this task
        self._trace[task_id] = [{"type": "command", "data": {"command": command[:300]}, "ts": time.time()}]
        if len(self._trace) > 50:
            oldest_key = next(iter(self._trace))
            self._trace.pop(oldest_key, None)

        async def _produce():
            try:
                async for event in self._execute_pipeline(command, task_id):
                    await queue.put(event)
            except Exception as e:
                await queue.put(AgentEvent(
                    type="error",
                    data={"message": str(e), "task_id": task_id}
                ))
            finally:
                await queue.put(None)

        asyncio.create_task(_produce())

        _TRACE_EVENTS = frozenset({
            "plan", "step_start", "step_complete", "step_error",
            "completed", "error", "goal_start", "goal_complete",
            "subtask_complete", "subtask_failed", "subtask_reflected",
            "goal_replanning",
        })

        while True:
            event = await queue.get()
            if event is None:
                break
            # Gap #8: Capture relevant events in trace
            if event.type in _TRACE_EVENTS:
                self._trace[task_id].append({
                    "type": event.type,
                    "data": event.data,
                    "ts": event.timestamp,
                })
            yield event

    async def _execute_pipeline(self, command: str,
                                 task_id: str) -> AsyncIterator[AgentEvent]:
        # Detect dry-run prefix
        dry_run = False
        raw_cmd = command.strip()
        for prefix in ("dry-run:", "dry run:", "dryrun:", "--dry-run"):
            if raw_cmd.lower().startswith(prefix):
                dry_run = True
                raw_cmd = raw_cmd[len(prefix):].strip()
                break

        if dry_run:
            yield AgentEvent("status", {
                "message": "🔍 Dry-run mode — plan will be shown but NOT executed",
                "task_id": task_id,
            })

        # ── Natural language preference detection ────────────────────────────────
        if not dry_run:
            pref_result = self.memory.parse_and_store_preference(raw_cmd)
            if pref_result is not None:
                yield AgentEvent("preference_stored", {
                    "task_id": task_id,
                    "message": pref_result,
                })
                return

        # ── Memory query shorthand commands ──────────────────────────────────────
        _lower = raw_cmd.lower().strip()
        _weekly_triggers = (
            "what have i been working on",
            "what did i work on",
            "show my work this week",
            "show weekly summary",
            "show weekly",
            "weekly summary",
            "memory weekly",
            "this week",
            "recent activity",
            "my activity",
            "what have i done",
        )
        if not dry_run and any(_lower.startswith(t) or _lower == t for t in _weekly_triggers):
            summary = self.memory.get_weekly_summary()
            yield AgentEvent("memory_weekly", {
                "task_id": task_id,
                "summary": summary,
            })
            return

        _pref_triggers = (
            "show my preferences",
            "my preferences",
            "list preferences",
            "show preferences",
            "what are my preferences",
        )
        if not dry_run and (_lower in _pref_triggers or _lower.startswith("show my preferences")):
            prefs = self.memory.get_all_preferences()
            yield AgentEvent("preferences_display", {
                "task_id": task_id,
                "preferences": prefs,
            })
            return

        # ── LLM-First Deep Intent Analysis ───────────────────────────────────────
        # For every non-obvious command, the LLM deeply analyzes words/sentences/paragraphs
        # to understand true intent, tone, and context before deciding how to respond.
        # Clear action-prefixed commands skip this to avoid wasted latency.
        _CLEAR_ACTION_PREFIXES = (
            "list ", "ls ", "create file", "create folder", "create a file", "create a folder",
            "make file", "make folder", "make a ", "move ", "mv ", "copy ", "cp ",
            "rename ", "delete ", "trash ", "remove file", "remove folder",
            "read file", "read the file", "open file", "open url", "open app",
            "unzip ", "extract ", "zip ", "search files", "search for files", "find files",
            "git status", "git diff", "git add", "git commit", "git log", "git push",
            "download ", "show system", "send whatsapp", "dry-run:", "dry run:",
        )
        _is_clear_action = any(_lower.startswith(p) for p in _CLEAR_ACTION_PREFIXES)

        # Build rich user context — everything Arix knows about this person
        _user_name = ""
        _user_context_lines: list[str] = []
        try:
            _profile = UserProfile.load()
            _user_name = _profile.name or ""
            if _profile.name:
                _user_context_lines.append(f"Name: {_profile.name}")
            if _profile.role:
                _user_context_lines.append(f"Role/Profession: {_profile.role}")
            if _profile.company:
                _user_context_lines.append(f"Company/Organisation: {_profile.company}")
            if _profile.timezone:
                _user_context_lines.append(f"Timezone: {_profile.timezone}")
            if _profile.communication_style:
                _user_context_lines.append(f"Preferred communication style: {_profile.communication_style}")
            if _profile.primary_use_cases:
                _user_context_lines.append(f"Primary use cases: {', '.join(_profile.primary_use_cases)}")
            if _profile.current_projects:
                _user_context_lines.append(f"Current projects: {', '.join(str(p) for p in _profile.current_projects)}")
        except Exception:
            pass
        try:
            _mem_prefs = self.memory.get_all_preferences()
            if not _user_name:
                _user_name = _mem_prefs.get("name", "") or ""
            for _k, _v in _mem_prefs.items():
                if _k not in ("name",) and _v:
                    _user_context_lines.append(f"User preference — {_k}: {_v}")
        except Exception:
            pass
        _user_context = "\n".join(_user_context_lines)

        # effective_cmd: cleaned English description of the task (from deep analysis).
        # Falls back to raw_cmd if deep analysis is unavailable or returns no description.
        effective_cmd = raw_cmd
        _llm_routed = False  # True once LLM has classified and handled this message

        if not dry_run and not _is_clear_action and self.llm_client is not None \
                and self.llm_client.is_available() and not self.config.offline_mode:
            try:
                analysis = await self.llm_client.deep_analyze(
                    raw_cmd, user_name=_user_name, user_context=_user_context
                )
                intent = analysis.get("intent", "task")
                response_text = analysis.get("response", "").strip()
                task_description = analysis.get("task_description", "").strip()

                _llm_routed = True  # LLM successfully classified this message

                if intent in ("chat", "advisory") and response_text:
                    yield AgentEvent("advisory", {
                        "task_id": task_id,
                        "question": raw_cmd,
                        "response": response_text,
                        "provider": self.config.provider,
                        "model": self.config.model,
                    })
                    return

                # intent == "task" — use the LLM's clean English task description
                # so the command parser and planner understand even informal/Urdu inputs
                if task_description:
                    effective_cmd = task_description

            except Exception:
                # Deep analysis failed — fall through to offline pattern-based routing
                pass

        # ── Offline / fallback pattern-based routing (when LLM unavailable) ──
        if not dry_run and not _is_clear_action:
            _has_action = any(kw in _lower for kw in (
                "create", "make", "write", "generate", "build", "delete", "remove",
                "trash", "move", "rename", "copy", "read", "open", "show", "list",
                "find", "search", "download", "upload", "extract", "unzip", "run",
                "execute", "start", "launch", "close", "kill", "git", "commit",
                "push", "pull", "diff", "install", "update", "edit", "modify",
                "send", "email", "message", "whatsapp", "schedule", "remind",
                "analyse", "analyze", "research", "summarize", "translate",
            ))
            if is_chitchat(raw_cmd) and not _has_action:
                greeting_name = f", {_user_name}" if _user_name else ""
                _lc = _lower
                if any(w in _lc for w in ("bye", "goodbye", "see you", "later", "cya", "farewell")):
                    offline_resp = f"Goodbye{greeting_name}! Come back whenever you need me. 👋"
                elif any(w in _lc for w in ("thanks", "thank you", "thx", "ty", "cheers")):
                    offline_resp = f"Happy to help{greeting_name}! Let me know if there's anything else. 😊"
                elif any(w in _lc for w in ("how are you", "how r u", "how are u", "you doing")):
                    offline_resp = f"I'm doing great{greeting_name}, thanks for asking! Ready to help — just give me a task or ask me anything."
                elif any(w in _lc for w in ("who are you", "what are you", "what is your name")):
                    offline_resp = (
                        f"I'm Arix{greeting_name} — your Personal AI Computer-Control Agent! "
                        "I can manage files, browse the web, run git commands, monitor your system, "
                        "create documents, and execute complex multi-step tasks. What can I do for you?"
                    )
                elif any(w in _lc for w in ("what can you do", "what do you do")):
                    offline_resp = (
                        f"Here's what I can do{greeting_name}:\n\n"
                        "- 📁 **Files** — create, read, move, copy, search, unzip\n"
                        "- 🌐 **Browser** — open URLs, search the web, extract page content, download files\n"
                        "- 💻 **System** — monitor CPU/RAM, list running apps\n"
                        "- 🔀 **Git** — status, diff, add, commit\n"
                        "- 📄 **Documents** — create/read Word and Excel files\n"
                        "- 🤖 **Research & Code** — answer questions, analyze topics, write code\n"
                        "- 🎯 **Multi-step goals** — chain complex tasks together automatically\n\n"
                        "Just type a command and I'll get it done!"
                    )
                elif any(w in _lc for w in ("how do you", "how do you do", "how can you", "how does arix", "how does it work")):
                    offline_resp = (
                        f"Great question{greeting_name}! Here's how I execute tasks:\n\n"
                        "1. **You give me a command** — in plain English (e.g. *\"find all PDFs in Downloads\"* or *\"open LinkedIn\"*)\n"
                        "2. **I analyze your intent** — I classify what you want: a task, a question, or a conversation\n"
                        "3. **I build a plan** — I select the right tools and sequence the steps needed\n"
                        "4. **Security check** — every step is validated for safety before running\n"
                        "5. **I execute** — tools run one by one (file ops, browser, git, system, etc.) and I report results\n\n"
                        "**Tools I can use:** files, browser, system monitor, git, documents (Word/Excel), code generation, "
                        "web research, desktop automation, Gmail, Drive, Calendar, Notion, Slack, Spotify, Trello, YouTube, and more.\n\n"
                        "Try typing a task like *\"list my Downloads folder\"* or *\"search the web for Python tutorials\"*!"
                    )
                else:
                    offline_resp = (
                        f"Hey{greeting_name}! I'm Arix, your personal AI assistant. "
                        "I'm ready to help — just tell me what you'd like to do."
                    )
                yield AgentEvent("advisory", {
                    "task_id": task_id,
                    "question": raw_cmd,
                    "response": offline_resp,
                    "provider": "offline",
                    "model": "demo",
                })
                return

        # ── Autonomous goal execution path ─────────────────────────────────────
        if is_multi_step_goal(raw_cmd) and not dry_run:
            goal_queue: asyncio.Queue = asyncio.Queue()

            def _emit_goal(event_type: str, data: dict) -> None:
                goal_queue.put_nowait(AgentEvent(event_type, {**data, "task_id": task_id}))

            async def _run_goal():
                try:
                    await self.supervisor.execute_goal(raw_cmd, _emit_goal)
                finally:
                    goal_queue.put_nowait(None)

            asyncio.create_task(_run_goal())

            while True:
                evt = await goal_queue.get()
                if evt is None:
                    break
                yield evt
                if evt.type == "goal_complete":
                    steps = evt.data.get("steps_completed", 0)
                    self.memory.record_task(
                        task_id=task_id,
                        command=raw_cmd,
                        intent_verb="goal",
                        intent_domain="multi_step",
                        outcome="completed",
                        steps_executed=steps,
                    )
            return

        # ── Advisory path: questions / analysis / expert guidance ─────────────
        # Skip when LLM deep analysis already classified and handled this message
        if not _llm_routed and self.advisory_detector.is_advisory(raw_cmd):
            if (self.llm_client is not None and self.llm_client.is_available()
                    and not self.config.offline_mode):
                yield AgentEvent("status", {
                    "message": f"Thinking… ({self.config.provider} / {self.config.model})",
                    "task_id": task_id,
                })
                try:
                    response = await self.llm_client.advise(raw_cmd)
                    yield AgentEvent("advisory", {
                        "task_id": task_id,
                        "question": raw_cmd,
                        "response": response,
                        "provider": self.config.provider,
                        "model": self.config.model,
                    })
                    self.audit_logger.log_event(
                        task_id=task_id, step_id="advisor",
                        event_type="advisory_response",
                        command_redacted=self.redactor.redact(raw_cmd).redacted[:200],
                    )
                    return
                except Exception as e:
                    yield AgentEvent("warning", {
                        "message": f"Advisor unavailable ({e}) — trying as command",
                        "task_id": task_id,
                    })
                    # Fall through to normal pipeline
            else:
                _lc2 = raw_cmd.lower()
                _gn2 = f", {_user_name}" if _user_name else ""

                # Capability questions can be answered offline without LLM
                if any(w in _lc2 for w in (
                    "how do you", "how can you", "how do you do", "how does it work",
                    "how does arix", "how you work", "how do u", "how r you",
                )):
                    offline_advisory = (
                        f"Great question{_gn2}! Here's how I execute tasks:\n\n"
                        "1. **You give me a command** — plain English (e.g. *\"find all PDFs in Downloads\"*)\n"
                        "2. **I analyse your intent** — classify it as a task, question, or conversation\n"
                        "3. **I build a plan** — select the right tools and sequence the steps\n"
                        "4. **Security check** — every step is validated for safety before running\n"
                        "5. **I execute** — tools run one by one and I stream results back to you\n\n"
                        "**Available tool domains:** files, browser, system monitor, git, "
                        "documents (Word/Excel), code generation, web research, desktop automation, "
                        "Gmail, Drive, Calendar, Notion, Slack, Spotify, Trello, YouTube, and more.\n\n"
                        "Try: *\"list my Downloads folder\"* or *\"search the web for Python tutorials\"*"
                    )
                elif any(w in _lc2 for w in ("what can you do", "what do you do", "what are your capabilities")):
                    offline_advisory = (
                        f"Here's what I can do{_gn2}:\n\n"
                        "- 📁 **Files** — create, read, move, copy, search, unzip\n"
                        "- 🌐 **Browser** — open URLs, search the web, extract content, download files\n"
                        "- 💻 **System** — monitor CPU/RAM, list running apps\n"
                        "- 🔀 **Git** — status, diff, add, commit\n"
                        "- 📄 **Documents** — create/read Word and Excel files\n"
                        "- 🤖 **Research & Code** — analyze topics, write and explain code\n"
                        "- 📧 **Gmail / Drive / Calendar** — read mail, manage files, check events\n"
                        "- 💬 **Slack / Notion / Trello / Spotify / YouTube** — app integrations\n"
                        "- 🎯 **Multi-step goals** — chain complex tasks automatically\n\n"
                        "Just type a command and I'll get it done!"
                    )
                elif any(w in _lc2 for w in ("who are you", "what are you", "what is arix", "tell me about yourself")):
                    offline_advisory = (
                        f"I'm Arix{_gn2} — your Personal AI Computer-Control Agent! "
                        "I execute natural-language commands to control your computer: manage files, "
                        "browse the web, run git commands, monitor your system, interact with apps "
                        "like Gmail, Slack and Notion, and chain complex multi-step tasks together. "
                        "What would you like me to do?"
                    )
                else:
                    key_hint = ""
                    if self.llm_client:
                        err = self.llm_client.key_error()
                        if err:
                            key_hint = f"\n\n**Current issue:** {err}"
                    offline_advisory = (
                        "**Advisory mode requires a working API key.**\n\n"
                        "To enable full AI advisory responses:\n"
                        "1. Go to Replit Secrets (🔒 in the left sidebar)\n"
                        "2. Add `ANTHROPIC_API_KEY` (recommended), or a valid `GEMINI_API_KEY` "
                        "(must start with `AIza`) or `OPENAI_API_KEY`\n"
                        "3. Restart the app"
                        + key_hint + "\n\n"
                        "In demo mode, only computer-control actions (file, git, system, browser) "
                        "work with the heuristic planner."
                    )
                yield AgentEvent("advisory", {
                    "task_id": task_id,
                    "question": raw_cmd,
                    "response": offline_advisory,
                    "provider": "offline",
                    "model": "demo",
                })
                return

        # ── OpenClaw-style native tool-calling agentic loop ──────────────────────
        # When an LLM is available, route tasks through the iterative tool-calling
        # loop instead of the static plan→validate→execute path.
        # The LLM drives execution: think → call_tool → see_result → think → …
        _use_tool_loop = (
            not dry_run
            and not self.config.offline_mode
            and self.llm_client is not None
            and self.llm_client.is_available()
        )

        if _use_tool_loop:
            # ── Detect matching Capability Hand ───────────────────────────────
            active_hand = self.hand_manager.detect_hand(effective_cmd or raw_cmd)
            if active_hand:
                yield AgentEvent("hand_activated", {
                    "task_id": task_id,
                    "hand_id": active_hand.hand_id,
                    "hand_name": active_hand.name,
                    "hand_icon": active_hand.icon,
                    "hand_persona": active_hand.persona[:120],
                    "knowledge_count": len(active_hand.knowledge),
                })

            yield AgentEvent("status", {
                "message": (
                    f"🤖 Arix agent loop starting"
                    + (f" · {active_hand.icon} {active_hand.name} Hand" if active_hand else "")
                    + f" ({self.config.provider} / {self.config.model})"
                ),
                "task_id": task_id,
            })

            _loop = ToolCallingLoop(
                llm_client=self.llm_client,
                tool_dispatch=TOOL_DISPATCH,
            )

            _loop_start = time.time()
            _had_error = False

            try:
                async for (evt_type, evt_data) in _loop.run(
                    command=effective_cmd or raw_cmd,
                    task_id=task_id,
                    hand=active_hand,
                    user_context=_user_context,
                ):
                    yield AgentEvent(evt_type, {**evt_data, "task_id": task_id})
                    if evt_type == "tool_loop_error":
                        _had_error = True
            except Exception as _e:
                _had_error = True
                yield AgentEvent("error", {
                    "task_id": task_id,
                    "message": f"Agent loop error: {_e}",
                })

            _loop_duration = time.time() - _loop_start

            # Record Hand metrics
            if active_hand:
                self.hand_manager.record_run(
                    active_hand.hand_id,
                    success=not _had_error,
                    duration_s=_loop_duration,
                )

            # Record in memory
            try:
                self.memory.record_task(
                    task_id=task_id,
                    command=(raw_cmd)[:300],
                    intent_verb="tool_loop",
                    intent_domain="agentic",
                    outcome="failed" if _had_error else "completed",
                    steps_executed=0,
                )
            except Exception:
                pass

            # ── Hermes-style Curator: fire after N completed goals ────────────
            try:
                curator = get_curator()
                should_run = curator.on_goal_completed(
                    goal=raw_cmd[:200],
                    steps_completed=1,
                    success=not _had_error,
                )
                if should_run and self.llm_client and self.llm_client.is_available():
                    import asyncio as _asyncio
                    _asyncio.ensure_future(self._run_curator_async())
            except Exception:
                pass

            if not _had_error:
                yield AgentEvent("completed", {
                    "task_id": task_id,
                    "steps_executed": 0,
                    "output": "",
                })

            return

        yield AgentEvent("status", {"message": "Parsing command...", "task_id": task_id})

        scope = self.command_parser.parse(effective_cmd, task_id=task_id)
        scope.dry_run = dry_run

        self.audit_logger.log_event(
            task_id=task_id, step_id="init",
            event_type="task_created",
            command_redacted=scope.redacted_command,
            task_scope_digest=scope.scope_digest,
        )

        yield AgentEvent("scope", {
            "task_id": task_id,
            "intent_verb": scope.intent_verb,
            "intent_domain": scope.intent_domain,
            "allowed_tools": sorted(scope.allowed_tools),
            "dry_run": dry_run,
        })

        use_llm = (
            not self.config.offline_mode
            and not dry_run
            and self.llm_client is not None
            and self.llm_client.is_available()
        )

        if use_llm:
            yield AgentEvent("status", {
                "message": f"Planning with {self.config.provider} / {self.config.model}..."
            })
            try:
                mem_context = self.memory.build_context_for_command(
                    effective_cmd, scope.intent_domain
                )

                # ── Memory-augmented few-shot planning ────────────────────────
                # Search episodic memory for up to 3 similar past tasks that
                # succeeded.  Inject their command + plan as worked examples so
                # the LLM can reason from real past experience rather than just
                # the static prompt examples.
                few_shot_lines: list[str] = []
                try:
                    similar = self.memory.search_similar_tasks(
                        effective_cmd, limit=3, success_only=True
                    )
                    for past in similar:
                        domain = past.get("intent_domain", "")
                        steps_n = past.get("steps_executed", 0)
                        few_shot_lines.append(
                            f'  • [{domain}] "{past["command"][:80]}"'
                            f' — completed in {steps_n} step(s)'
                        )
                except Exception:
                    pass

                few_shot_section = (
                    "SIMILAR PAST SUCCESSFUL TASKS (for reference — adapt, don't copy):\n"
                    + "\n".join(few_shot_lines)
                    if few_shot_lines else ""
                )

                # ── RAG Knowledge Base context injection ──────────────────
                # Query the local document knowledge base for passages relevant
                # to this command and inject the top results as context so the
                # LLM planner can leverage the user's own documents.
                rag_context = ""
                try:
                    kb_stats = self.knowledge_base.get_stats()
                    if kb_stats.get("total_chunks", 0) > 0:
                        kb_results = self.knowledge_base.query(effective_cmd, top_k=3)
                        passages = kb_results.get("results", [])
                        if passages:
                            rag_lines = [
                                f'  [{r.get("doc_name","doc")} p.{r.get("page",1)}] '
                                f'{(r.get("text") or "")[:200].strip()}'
                                for r in passages if r.get("text")
                            ]
                            if rag_lines:
                                rag_context = (
                                    "RELEVANT PASSAGES FROM YOUR KNOWLEDGE BASE:\n"
                                    + "\n".join(rag_lines)
                                )
                except Exception:
                    pass

                # Prepend user profile + few-shot examples so the planner knows
                # who it's working for and can match past successful patterns.
                context_parts = [p for p in [
                    f"USER PROFILE:\n{_user_context}" if _user_context else "",
                    few_shot_section,
                    mem_context,
                    rag_context,
                ] if p]
                full_context = "\n\n".join(context_parts)

                plan = await self.llm_client.plan(scope, context=full_context)
            except Exception as e:
                yield AgentEvent("warning", {
                    "message": f"LLM unavailable ({e}) — falling back to heuristic planner"
                })
                plan = self.heuristic_planner.plan(scope)
        else:
            mode = "dry-run" if dry_run else "demo"
            yield AgentEvent("status", {
                "message": f"⚠ Using heuristic planner ({mode} mode)"
            })
            plan = self.heuristic_planner.plan(scope)

        if not plan:
            yield AgentEvent("error", {
                "message": "Planner produced an empty plan.",
                "task_id": task_id,
            })
            return

        yield AgentEvent("status", {
            "message": f"Validating plan ({len(plan)} step{'s' if len(plan) != 1 else ''})..."
        })

        try:
            validated = self.plan_validator.validate(plan, scope)
        except PlanValidationError as e:
            yield AgentEvent("error", {
                "message": f"Plan rejected: {e}",
                "task_id": task_id,
            })
            self.audit_logger.log_event(
                task_id=task_id, step_id="validator",
                event_type="plan_rejected", error=str(e),
            )
            return

        risk_score = self.risk_evaluator.evaluate(validated, TOOL_REGISTRY)
        self.state_machine.create(task_id, total_steps=len(validated))

        # Record in task history
        hist_record = self.task_history.record_start(
            task_id=task_id,
            command_redacted=scope.redacted_command[:200],
            intent_domain=scope.intent_domain,
            intent_verb=scope.intent_verb,
            steps_total=len(validated),
            risk_score=risk_score.total,
        )

        yield AgentEvent("plan", {
            "task_id": task_id,
            "dry_run": dry_run,
            "steps": [{
                "step_id": s["step_id"],
                "tool": s["tool"],
                "description": s.get("description", ""),
                "args_preview": {k: str(v)[:80] for k, v in s["args"].items()
                                 if not k.startswith("_")},
                "risk_level": (TOOL_REGISTRY[s["tool"]].risk_level.value
                               if s["tool"] in TOOL_REGISTRY else "unknown"),
                "reversible": (TOOL_REGISTRY[s["tool"]].reversible
                               if s["tool"] in TOOL_REGISTRY else False),
            } for s in validated],
            "risk_score": risk_score.total,
            "risk_gate": risk_score.gate,
            "risk_breakdown": risk_score.breakdown,
        })

        if dry_run:
            yield AgentEvent("dry_run_complete", {
                "task_id": task_id,
                "message": "Dry-run complete — no tools were executed.",
                "steps": len(validated),
                "risk_score": risk_score.total,
            })
            self.task_history.update_status(task_id, "dry_run")
            return

        # Plan-level risk gate
        if risk_score.requires_yes or risk_score.requires_acknowledge:
            gate_msg = (
                f"⚠ Risk score {risk_score.total:.0f} — "
                f"{'Type YES to proceed' if risk_score.requires_yes else 'Press ENTER to acknowledge'}"
            )
            yield AgentEvent("confirmation_required", {
                "task_id": task_id,
                "confirmation_id": "plan_risk",
                "type": "plan_risk",
                "message": gate_msg,
                "requires_yes": risk_score.requires_yes,
                "score": risk_score.total,
            })
            confirmed = await self._wait_for_confirmation(task_id, "plan_risk")
            if not confirmed:
                self.state_machine.cancel(task_id)
                self.task_history.update_status(task_id, "cancelled")
                yield AgentEvent("cancelled", {"task_id": task_id, "reason": "User declined"})
                return

        confirmation_receipt_id = str(uuid.uuid4()) if risk_score.requires_yes else None

        self.state_machine.transition(task_id, TaskState.EXECUTING)
        yield AgentEvent("executing", {"task_id": task_id})

        results = []
        files_affected: list[str] = []

        for i, step in enumerate(validated):
            if self.state_machine.is_cancelled(task_id):
                yield AgentEvent("cancelled", {"task_id": task_id})
                break

            tool_name = step["tool"]
            meta = TOOL_REGISTRY.get(tool_name)
            step_id = step["step_id"]

            # Gap #7: honour user-deselected steps
            if step_id in self._skip_steps.get(task_id, set()):
                results.append({"step_id": step_id, "tool": tool_name,
                                 "result": {"skipped": True, "reason": "Deselected by user"}})
                yield AgentEvent("step_complete", {
                    "task_id": task_id,
                    "step_id": step_id,
                    "step_number": i + 1,
                    "tool": tool_name,
                    "result": {"skipped": True, "reason": "Deselected by user"},
                })
                continue

            # Step-level confirmation for HIGH-risk tools
            if meta and meta.requires_confirmation:
                yield AgentEvent("confirmation_required", {
                    "task_id": task_id,
                    "confirmation_id": step_id,
                    "step_id": step_id,
                    "type": "step_confirmation",
                    "tool": tool_name,
                    "description": step.get("description", ""),
                    "risk_level": meta.risk_level.value,
                    "message": (
                        f"Step {i+1}/{len(validated)}: {tool_name}\n"
                        f"{step.get('description', '')}\n"
                        f"Risk: {meta.risk_level.value} — Type YES to execute"
                    ),
                    "requires_yes": True,
                })
                confirmed = await self._wait_for_confirmation(task_id, step_id)
                if not confirmed:
                    self.state_machine.transition(task_id, TaskState.CANCELLED)
                    self.task_history.update_status(task_id, "cancelled",
                                                     steps_executed=len(results))
                    yield AgentEvent("cancelled", {
                        "task_id": task_id,
                        "reason": f"User declined step {step_id}",
                    })
                    return

            yield AgentEvent("step_start", {
                "task_id": task_id,
                "step_id": step_id,
                "step_number": i + 1,
                "total_steps": len(validated),
                "tool": tool_name,
                "description": step.get("description", ""),
            })

            try:
                grant = self.policy_engine.issue_grant(
                    task_id=task_id,
                    step_id=step_id,
                    tool_name=tool_name,
                    args=_clean(step["args"]),
                    resources=step.get("resolved_resources", []),
                    task_scope=scope,
                    confirmation_receipt_id=confirmation_receipt_id,
                )

                try:
                    self.runtime_validator.validate_step(grant, step, scope)
                except RuntimeValidationError as e:
                    yield AgentEvent("step_error", {
                        "task_id": task_id,
                        "step_id": step_id,
                        "error": str(e),
                    })
                    self.audit_logger.log_event(
                        task_id=task_id, step_id=step_id,
                        event_type="runtime_validation_failed",
                        error=str(e),
                    )
                    continue

                result = await self._execute_tool(tool_name, step["args"])

                # Track undo
                _try_register_undo(
                    self.undo_manager, task_id, step_id, tool_name,
                    _clean(step["args"]), result
                )

                # Track affected files
                for field_name in ("path", "source", "destination", "archive_path"):
                    val = step["args"].get(field_name, "")
                    if val and isinstance(val, str):
                        files_affected.append(val)

                self.audit_logger.log_event(
                    task_id=task_id, step_id=step_id,
                    event_type="tool_executed",
                    tool_name=tool_name,
                    sanitized_args=_clean(step["args"]),
                    result_summary=str(result)[:200],
                    grant_id=grant.grant_id,
                )

                results.append({"step_id": step_id, "tool": tool_name, "result": result})
                yield AgentEvent("step_complete", {
                    "task_id": task_id,
                    "step_id": step_id,
                    "step_number": i + 1,
                    "tool": tool_name,
                    "result": result,
                })

            except Exception as e:
                yield AgentEvent("step_error", {
                    "task_id": task_id,
                    "step_id": step_id,
                    "error": str(e),
                })
                self.audit_logger.log_event(
                    task_id=task_id, step_id=step_id,
                    event_type="tool_error", error=str(e),
                )

        final_status = "completed" if not self.state_machine.is_cancelled(task_id) else "cancelled"
        if not self.state_machine.is_cancelled(task_id):
            self.state_machine.transition(task_id, TaskState.COMPLETED)

        self.task_history.update_status(
            task_id, final_status,
            steps_executed=len(results),
            files_affected=files_affected,
        )

        self.memory.record_task(
            task_id=task_id,
            command=scope.redacted_command[:300],
            intent_verb=scope.intent_verb,
            intent_domain=scope.intent_domain,
            outcome=final_status,
            steps_executed=len(results),
            risk_score=risk_score.total,
            files_affected=files_affected[:10],
        )

        can_undo = self.undo_manager.can_undo()
        yield AgentEvent("completed", {
            "task_id": task_id,
            "steps_executed": len(results),
            "can_undo": can_undo,
            "results_summary": [
                {"step": r["step_id"], "tool": r["tool"],
                 "success": "error" not in r["result"]}
                for r in results
            ],
        })

    async def _execute_tool(self, tool_name: str, args: dict) -> dict:
        clean_args = _clean(args)
        handler = TOOL_DISPATCH.get(tool_name)
        if not handler:
            return {"error": f"No handler for tool: {tool_name}"}
        timeout = getattr(self.config, "tool_timeout_seconds", 60)
        try:
            result = handler(clean_args)
            if asyncio.iscoroutine(result):
                result = await asyncio.wait_for(result, timeout=float(timeout))
            else:
                result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, lambda: result),
                    timeout=float(timeout),
                )
        except asyncio.TimeoutError:
            return {
                "error": f"Tool '{tool_name}' timed out after {timeout}s",
                "timeout": True,
            }
        return result

    async def _wait_for_confirmation(self, task_id: str,
                                      confirmation_id: str,
                                      timeout: float = 300.0) -> bool:
        key = f"{task_id}:{confirmation_id}"
        gate: asyncio.Queue = asyncio.Queue(maxsize=1)
        self._confirmation_gates[key] = gate
        try:
            return await asyncio.wait_for(gate.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return False
        finally:
            self._confirmation_gates.pop(key, None)

    def confirm(self, task_id: str, confirmation_id: str, response: str,
                skip_steps: list[str] | None = None) -> bool:
        key = f"{task_id}:{confirmation_id}"
        gate = self._confirmation_gates.get(key)
        if gate is None:
            return False
        accepted = response.strip().upper() in ("YES", "Y", "OK", "ENTER", "")
        # Gap #7: store deselected step IDs when the plan is confirmed
        if accepted and skip_steps and confirmation_id == "plan_risk":
            self._skip_steps[task_id] = set(skip_steps)
        try:
            gate.put_nowait(accepted)
            return True
        except asyncio.QueueFull:
            return False

    def cancel_task(self, task_id: str) -> None:
        self.state_machine.cancel(task_id)
        # Release all pending confirmation gates for this task
        for key in list(self._confirmation_gates.keys()):
            if key.startswith(f"{task_id}:"):
                gate = self._confirmation_gates.pop(key, None)
                if gate:
                    try:
                        gate.put_nowait(False)
                    except asyncio.QueueFull:
                        pass

    def has_provider_consent(self, provider_id: str) -> bool:
        return self.consent_store.has_consent(provider_id)

    def record_provider_consent(self, provider_id: str) -> None:
        from arix.pipeline.content_gateway import PROVIDER_INFO
        info = PROVIDER_INFO.get(provider_id, {
            "display_name": provider_id,
            "privacy_url": "https://example.com/privacy",
            "egress_types": ["command_text", "file_excerpt"],
        })
        self.consent_store.record_consent(
            provider_id=provider_id,
            display_name=info["display_name"],
            privacy_url=info["privacy_url"],
            egress_types=info["egress_types"],
        )
