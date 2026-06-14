"""PACCA Agent — orchestrates the full pipeline for each user command."""
from __future__ import annotations
import asyncio
import hashlib
import json
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Any

from pacca.config import PACCAConfig, get_grant_secret_key
from pacca.heuristic_planner import HeuristicPlanner
from pacca.models.audit_log import AuditLogger
from pacca.models.provider_consent import ConsentStore
from pacca.models.task_scope import TaskScope
from pacca.pipeline.command_parser import CommandParser
from pacca.pipeline.content_gateway import ContentDataGateway
from pacca.pipeline.plan_validator import PlanValidator, PlanValidationError
from pacca.pipeline.policy_engine import PolicyEngine
from pacca.pipeline.risk_evaluator import CumulativePlanRiskEvaluator, RiskScore
from pacca.pipeline.runtime_validator import RuntimeStepValidator, RuntimeValidationError
from pacca.pipeline.task_state_machine import TaskStateMachine, TaskState
from pacca.security.grant_verifier import GrantVerifier
from pacca.security.local_text_redactor import LocalTextRedactor
from pacca.security.safe_resource_resolver import SafeResourceResolver
from pacca.security.used_grant_registry import UsedGrantRegistry
from pacca.task_history import TaskHistory
from pacca.tools.registry import TOOL_REGISTRY, policy_version
from pacca.undo_manager import UndoManager, make_move_undo, make_create_undo, make_create_folder_undo
from pacca.advisor import AdvisoryIntentDetector
from pacca.llm_client import LLMClient
from pacca.memory.memory_manager import MemoryManager
from pacca.supervisor import GoalSupervisor, is_multi_step_goal

import pacca.tools.file_tools as file_tools
import pacca.tools.app_tools as app_tools
import pacca.tools.system_tools as system_tools
import pacca.tools.browser_tools as browser_tools
import pacca.tools.document_tools as document_tools
import pacca.tools.git_tools as git_tools
import pacca.tools.whatsapp_tools as whatsapp_tools


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


class PACCAAgent:
    def __init__(self, config: PACCAConfig | None = None):
        self.config = config or PACCAConfig.load()
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

        self.gateway = ContentDataGateway(
            redactor=self.redactor,
            consent_store=self.consent_store,
            llm_client=llm_client,
            provider_id=self.config.provider,
            max_file_egress_bytes=self.config.max_file_egress_bytes,
        )

        self.supervisor = GoalSupervisor(
            run_command_fn=self.run_command,
            max_retries=2,
            goal_timeout=600.0,
            max_depth=3,
        )

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

    async def run_command(self, command: str,
                          task_id: str | None = None) -> AsyncIterator[AgentEvent]:
        task_id = task_id or str(uuid.uuid4())
        queue: asyncio.Queue = asyncio.Queue()

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

        while True:
            event = await queue.get()
            if event is None:
                break
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
        if self.advisory_detector.is_advisory(raw_cmd):
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
                yield AgentEvent("advisory", {
                    "task_id": task_id,
                    "question": raw_cmd,
                    "response": (
                        "**Advisory mode requires an API key.**\n\n"
                        "To enable full AI advisory responses:\n"
                        "1. Go to Replit Secrets (🔒 in the left sidebar)\n"
                        "2. Add `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `GEMINI_API_KEY`\n"
                        "3. Restart the app\n\n"
                        "In demo mode, only computer-control actions (file, git, system, browser) work with the heuristic planner."
                    ),
                    "provider": "offline",
                    "model": "demo",
                })
                return

        yield AgentEvent("status", {"message": "Parsing command...", "task_id": task_id})

        scope = self.command_parser.parse(raw_cmd, task_id=task_id)
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
                plan = await self.llm_client.plan(scope)
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
        result = handler(clean_args)
        if asyncio.iscoroutine(result):
            result = await result
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

    def confirm(self, task_id: str, confirmation_id: str, response: str) -> bool:
        key = f"{task_id}:{confirmation_id}"
        gate = self._confirmation_gates.get(key)
        if gate is None:
            return False
        accepted = response.strip().upper() in ("YES", "Y", "OK", "ENTER", "")
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
        from pacca.pipeline.content_gateway import PROVIDER_INFO
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
