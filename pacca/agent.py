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
from pacca.tools.registry import TOOL_REGISTRY, policy_version
from pacca.llm_client import LLMClient

import pacca.tools.file_tools as file_tools
import pacca.tools.app_tools as app_tools
import pacca.tools.system_tools as system_tools
import pacca.tools.browser_tools as browser_tools
import pacca.tools.document_tools as document_tools
import pacca.tools.git_tools as git_tools


@dataclass
class AgentEvent:
    type: str
    data: dict
    timestamp: float = field(default_factory=time.time)


TOOL_DISPATCH: dict[str, Callable] = {
    "list_directory": lambda args: file_tools.list_directory(**_file_args(args)),
    "create_folder": lambda args: file_tools.create_folder(**_file_args(args)),
    "create_file": lambda args: file_tools.create_file(**_file_args(args)),
    "read_file": lambda args: file_tools.read_file(**_file_args(args)),
    "move_file": lambda args: file_tools.move_file(**_file_args(args)),
    "copy_file": lambda args: file_tools.copy_file(**_file_args(args)),
    "search_files": lambda args: file_tools.search_files(**_file_args(args)),
    "unzip_archive": lambda args: file_tools.unzip_archive(**_file_args(args)),
    "move_to_trash": lambda args: file_tools.move_to_trash(**_file_args(args)),
    "open_known_app": lambda args: app_tools.open_known_app(**_file_args(args)),
    "close_app": lambda args: app_tools.close_app(**_file_args(args)),
    "list_running_apps": lambda args: app_tools.list_running_apps(),
    "system_monitor": lambda args: system_tools.system_monitor(**_file_args(args)),
    "browser_open_url": lambda args: browser_tools.browser_open_url(**_file_args(args)),
    "browser_web_search": lambda args: browser_tools.browser_web_search(**_file_args(args)),
    "browser_extract_page_text": lambda args: browser_tools.browser_extract_page_text(**_file_args(args)),
    "browser_download_file": lambda args: browser_tools.browser_download_file(**_file_args(args)),
    "browser_tab_management": lambda args: browser_tools.browser_tab_management(**_file_args(args)),
    "create_docx": lambda args: document_tools.create_docx(**_file_args(args)),
    "read_docx": lambda args: document_tools.read_docx(**_file_args(args)),
    "create_xlsx": lambda args: document_tools.create_xlsx(**_file_args(args)),
    "read_xlsx": lambda args: document_tools.read_xlsx(**_file_args(args)),
    "git_status": lambda args: git_tools.git_status(**_file_args(args)),
    "git_diff": lambda args: git_tools.git_diff(**_file_args(args)),
    "git_add": lambda args: git_tools.git_add(**_file_args(args)),
    "git_commit": lambda args: git_tools.git_commit(**_file_args(args)),
}


def _file_args(args: dict) -> dict:
    return {k: v for k, v in args.items() if not k.startswith("_resolved_")}


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

        self._pending_confirmations: dict[str, asyncio.Future] = {}
        self._event_queues: dict[str, asyncio.Queue] = {}
        self._active_tasks: dict[str, str] = {}

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
        self._event_queues[task_id] = queue

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

        if task_id in self._event_queues:
            del self._event_queues[task_id]

    async def _execute_pipeline(self, command: str,
                                 task_id: str) -> AsyncIterator[AgentEvent]:
        yield AgentEvent("status", {"message": "Parsing command...", "task_id": task_id})

        scope = self.command_parser.parse(command, task_id=task_id)

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
        })

        if self.config.offline_mode or not self.llm_client or not self.llm_client.is_available():
            yield AgentEvent("status", {"message": "⚠ No LLM available — dry-run demo mode"})
            plan = self._demo_plan(scope)
        else:
            yield AgentEvent("status", {
                "message": f"Planning with {self.config.provider} / {self.config.model}..."
            })
            try:
                raw_plan = await self.llm_client.plan(scope)
                plan = raw_plan
            except Exception as e:
                yield AgentEvent("error", {"message": f"LLM planning failed: {e}"})
                return

        yield AgentEvent("status", {"message": f"Validating plan ({len(plan)} steps)..."})

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
        task = self.state_machine.create(task_id, total_steps=len(validated))

        yield AgentEvent("plan", {
            "task_id": task_id,
            "steps": [{
                "step_id": s["step_id"],
                "tool": s["tool"],
                "description": s.get("description", ""),
                "args_preview": {k: str(v)[:80] for k, v in s["args"].items()
                                 if not k.startswith("_")},
            } for s in validated],
            "risk_score": risk_score.total,
            "risk_gate": risk_score.gate,
            "risk_breakdown": risk_score.breakdown,
        })

        if risk_score.requires_yes or risk_score.requires_acknowledge:
            gate_msg = (
                f"⚠ Risk score {risk_score.total:.0f} — "
                f"{'Type YES to proceed' if risk_score.requires_yes else 'Press ENTER to acknowledge'}"
            )
            yield AgentEvent("confirmation_required", {
                "task_id": task_id,
                "type": "plan_risk",
                "message": gate_msg,
                "requires_yes": risk_score.requires_yes,
                "score": risk_score.total,
            })
            confirmed = await self._wait_for_confirmation(task_id, "plan_risk")
            if not confirmed:
                self.state_machine.cancel(task_id)
                yield AgentEvent("cancelled", {"task_id": task_id, "reason": "User declined"})
                return

        confirmation_receipt_id = str(uuid.uuid4()) if risk_score.requires_yes else None

        self.state_machine.transition(task_id, TaskState.EXECUTING)
        yield AgentEvent("executing", {"task_id": task_id})

        results = []
        for i, step in enumerate(validated):
            if self.state_machine.is_cancelled(task_id):
                yield AgentEvent("cancelled", {"task_id": task_id})
                return

            tool_name = step["tool"]
            meta = TOOL_REGISTRY.get(tool_name)
            step_id = step["step_id"]

            if meta and meta.requires_confirmation:
                yield AgentEvent("confirmation_required", {
                    "task_id": task_id,
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
                    args=_file_args(step["args"]),
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

                self.audit_logger.log_event(
                    task_id=task_id, step_id=step_id,
                    event_type="tool_executed",
                    tool_name=tool_name,
                    sanitized_args=_file_args(step["args"]),
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

        self.state_machine.transition(task_id, TaskState.COMPLETED)
        yield AgentEvent("completed", {
            "task_id": task_id,
            "steps_executed": len(results),
            "results_summary": [
                {"step": r["step_id"], "tool": r["tool"],
                 "success": "error" not in r["result"]}
                for r in results
            ],
        })

    async def _execute_tool(self, tool_name: str, args: dict) -> dict:
        clean_args = _file_args(args)
        handler = TOOL_DISPATCH.get(tool_name)
        if not handler:
            return {"error": f"No handler for tool: {tool_name}"}
        result = handler(clean_args)
        if asyncio.iscoroutine(result):
            result = await result
        return result

    async def _wait_for_confirmation(self, task_id: str,
                                      confirmation_id: str) -> bool:
        key = f"{task_id}:{confirmation_id}"
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_confirmations[key] = future
        try:
            return await asyncio.wait_for(future, timeout=300.0)
        except asyncio.TimeoutError:
            return False
        finally:
            self._pending_confirmations.pop(key, None)

    def confirm(self, task_id: str, confirmation_id: str,
                response: str) -> bool:
        key = f"{task_id}:{confirmation_id}"
        future = self._pending_confirmations.get(key)
        if not future or future.done():
            return False
        accepted = response.strip().upper() in ("YES", "Y", "ENTER", "")
        future.set_result(accepted)
        return True

    def cancel_task(self, task_id: str) -> None:
        self.state_machine.cancel(task_id)
        for key, future in list(self._pending_confirmations.items()):
            if key.startswith(f"{task_id}:") and not future.done():
                future.set_result(False)

    def _demo_plan(self, scope: TaskScope) -> list[dict]:
        """Generate a demo plan when no LLM is available."""
        domain = scope.intent_domain
        verb = scope.intent_verb
        command = scope.redacted_command.lower()

        if domain == "system" or "monitor" in command or "cpu" in command:
            return [{"tool": "system_monitor", "args": {},
                     "description": "Show system resource usage"}]
        if domain == "app" or "list" in command and "app" in command:
            return [{"tool": "list_running_apps", "args": {},
                     "description": "List running applications"}]
        if "list" in verb or "ls" in command:
            import os
            path = os.path.expanduser("~")
            return [{"tool": "list_directory", "args": {"path": path},
                     "description": f"List home directory"}]
        if domain == "git" or "git" in command:
            import os
            return [{"tool": "git_status", "args": {"repo_path": os.getcwd()},
                     "description": "Check git status"}]
        if "search" in verb:
            import os
            return [{"tool": "search_files",
                     "args": {"path": os.path.expanduser("~"), "pattern": "*.txt"},
                     "description": "Search for text files"}]
        import os
        return [{"tool": "list_directory",
                 "args": {"path": os.getcwd()},
                 "description": "List current directory"}]

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
