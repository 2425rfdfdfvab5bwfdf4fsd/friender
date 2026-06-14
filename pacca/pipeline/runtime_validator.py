"""RuntimeStepValidator — re-validates each step immediately before execution."""
from __future__ import annotations
import time
from typing import Any

from pacca.models.capability_grant import CapabilityGrant, CapabilityViolation
from pacca.models.resolved_resource import ResolvedResource, PathExpectation
from pacca.models.task_scope import TaskScope
from pacca.security.grant_verifier import GrantVerifier
from pacca.security.safe_resource_resolver import SafeResourceResolver


class RuntimeValidationError(Exception):
    pass


class RuntimeStepValidator:
    def __init__(self, grant_verifier: GrantVerifier,
                 resolver: SafeResourceResolver,
                 tool_registry: dict[str, Any]):
        self.grant_verifier = grant_verifier
        self.resolver = resolver
        self.tool_registry = tool_registry

    def validate_step(self, grant: CapabilityGrant, step: dict,
                      task_scope: TaskScope) -> list[ResolvedResource]:
        tool_name = step["tool"]
        args = step.get("args", {})
        resources = step.get("resolved_resources", [])

        if grant.is_expired():
            raise RuntimeValidationError(
                f"Grant expired for step {step.get('step_id')}"
            )

        if tool_name not in task_scope.allowed_tools:
            raise RuntimeValidationError(
                f"Tool '{tool_name}' not in TaskScope.allowed_tools (re-check at runtime)"
            )

        re_resolved = []
        for resource in resources:
            if not resource.realpath:
                continue
            fresh = self.resolver.resolve(
                resource.realpath, task_scope, PathExpectation.MAY_EXIST
            )
            ok, reason = self.resolver.check_toctou(resource)
            if not ok:
                raise RuntimeValidationError(
                    f"TOCTOU violation for '{resource.realpath}': {reason}"
                )
            re_resolved.append(fresh)

        clean_args = {k: v for k, v in args.items() if not k.startswith("_resolved_")}

        try:
            self.grant_verifier.verify(
                grant, tool_name, clean_args, resources, task_scope
            )
        except CapabilityViolation as e:
            raise RuntimeValidationError(f"Grant verification failed: {e}") from e

        return re_resolved
