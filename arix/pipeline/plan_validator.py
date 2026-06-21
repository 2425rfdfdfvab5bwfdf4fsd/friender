"""PlanValidator — validates LLM action plan before any execution."""
from __future__ import annotations
import re
from typing import Any

from arix.models.task_scope import TaskScope
from arix.models.resolved_resource import ResolvedResource, PathExpectation
from arix.security.safe_resource_resolver import SafeResourceResolver

PRIVATE_IP_PATTERNS = [
    re.compile(r'^https?://localhost', re.I),
    re.compile(r'^https?://127\.'),
    re.compile(r'^https?://10\.'),
    re.compile(r'^https?://192\.168\.'),
    re.compile(r'^https?://172\.(1[6-9]|2[0-9]|3[01])\.'),
    re.compile(r'^file://'),
    re.compile(r'^https?://0\.0\.0\.0'),
    # Link-local / cloud metadata service endpoints
    re.compile(r'^https?://169\.254\.'),
    # IPv6 loopback, link-local, and unique local
    re.compile(r'^https?://\[::1\]'),
    re.compile(r'^https?://\[fe80:', re.I),
    re.compile(r'^https?://\[fc', re.I),
    re.compile(r'^https?://\[fd', re.I),
    # Any IPv6 bracket address (catch-all for unknown private ranges)
    re.compile(r'^https?://\['),
    # data: URIs
    re.compile(r'^data:', re.I),
    # Credentials embedded in URL (user:pass@host)
    re.compile(r'^https?://[^/\s]*:[^/\s]*@'),
    # Octal / zero-prefixed IP notation (e.g. http://0177.0.0.1)
    re.compile(r'^https?://0\d+\.'),
    # Null/zero host
    re.compile(r'^https?://0+\.'),
]

PAYMENT_URL_PATTERNS = [
    re.compile(r'stripe\.com/pay', re.I),
    re.compile(r'paypal\.com/checkout', re.I),
    re.compile(r'checkout\.(stripe|braintree)', re.I),
]

MAX_STEPS = 30


class PlanValidationError(Exception):
    pass


class PlanValidator:
    def __init__(self, resolver: SafeResourceResolver,
                 tool_registry: dict[str, Any]):
        self.resolver = resolver
        self.tool_registry = tool_registry

    def validate(self, plan: list[dict], task_scope: TaskScope) -> list[dict]:
        if not isinstance(plan, list):
            raise PlanValidationError("Plan must be a list of steps")

        if len(plan) > MAX_STEPS:
            raise PlanValidationError(
                f"Plan has {len(plan)} steps (max {MAX_STEPS})"
            )

        seen_tools: set[str] = set()
        validated_steps = []

        for i, step in enumerate(plan):
            if not isinstance(step, dict):
                raise PlanValidationError(f"Step {i} is not a dict")

            tool_name = step.get("tool")
            if not tool_name:
                raise PlanValidationError(f"Step {i} missing 'tool' field")

            if tool_name not in self.tool_registry:
                raise PlanValidationError(
                    f"Step {i}: unknown tool '{tool_name}'"
                )

            if tool_name not in task_scope.allowed_tools:
                raise PlanValidationError(
                    f"Step {i}: tool '{tool_name}' not allowed for "
                    f"intent domain '{task_scope.intent_domain}' — "
                    f"possible prompt injection blocked"
                )

            args = step.get("args", {})
            if not isinstance(args, dict):
                raise PlanValidationError(f"Step {i}: 'args' must be a dict")

            # Check for missing required arguments based on tool_registry
            meta = self.tool_registry.get(tool_name)
            if hasattr(meta, "required_args"):
                for req in meta.required_args:
                    if req not in args:
                        raise PlanValidationError(f"Step {i}: missing required argument '{req}' for tool '{tool_name}'")

            validated_args, resolved = self._validate_args(
                tool_name, args, task_scope, i
            )

            # Check if we should enforce URL validation
            tool_meta = self.tool_registry.get(tool_name)
            data_egress = getattr(tool_meta, "data_egress", False)
            egress_type = getattr(tool_meta, "egress_type", "none")
            
            # If the tool is a browser tool or has cloud egress, validate 'url' argument
            if egress_type == "browser" or data_egress:
                for arg_name in ["url", "link", "target_url", "site"]:
                    if arg_name in args and isinstance(args[arg_name], str):
                        self._validate_url(args[arg_name], i)

            validated_steps.append({
                "step_id": f"step_{i:03d}",
                "tool": tool_name,
                "args": validated_args,
                "resolved_resources": resolved,
                "description": step.get("description", f"Execute {tool_name}"),
            })

        return validated_steps

    def _validate_args(self, tool_name: str, args: dict,
                       task_scope: TaskScope, step_idx: int
                       ) -> tuple[dict, list[ResolvedResource]]:
        resolved_resources = []
        validated_args = dict(args)

        path_arg_names = {"path", "source", "destination", "src", "dst",
                          "file_path", "dir_path", "archive_path",
                          "target_path", "repo_path", "output_path"}

        list_path_arg_names = {"source_paths", "paths"}

        for key, value in args.items():
            if key in path_arg_names and isinstance(value, str):
                resource = self.resolver.resolve(
                    value, task_scope, PathExpectation.MAY_EXIST
                )
                if not resource.is_safe():
                    raise PlanValidationError(
                        f"Step {step_idx}: path '{value}' blocked — "
                        f"{resource.blocked_reason}"
                    )
                resolved_resources.append(resource)
                validated_args[f"_resolved_{key}"] = resource.capability_token

            elif key in list_path_arg_names and isinstance(value, list):
                tokens = []
                for i, p in enumerate(value):
                    if not isinstance(p, str):
                        continue
                    resource = self.resolver.resolve(
                        p, task_scope, PathExpectation.MAY_EXIST
                    )
                    if not resource.is_safe():
                        raise PlanValidationError(
                            f"Step {step_idx}: path '{p}' in '{key}[{i}]' blocked — "
                            f"{resource.blocked_reason}"
                        )
                    resolved_resources.append(resource)
                    tokens.append(resource.capability_token)
                validated_args[f"_resolved_{key}"] = tokens

        return validated_args, resolved_resources

    def _validate_url(self, url: str, step_idx: int) -> None:
        for pattern in PRIVATE_IP_PATTERNS:
            if pattern.search(url):
                raise PlanValidationError(
                    f"Step {step_idx}: URL blocked (private/local): {url}"
                )
        for pattern in PAYMENT_URL_PATTERNS:
            if pattern.search(url):
                raise PlanValidationError(
                    f"Step {step_idx}: URL blocked (payment flow): {url}"
                )
