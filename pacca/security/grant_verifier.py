"""GrantVerifier — called by every tool at entry, before any side effect."""
from __future__ import annotations
import hashlib
import hmac
import json
import time
from typing import TYPE_CHECKING

from pacca.models.capability_grant import CapabilityGrant, CapabilityViolation
from pacca.security.used_grant_registry import UsedGrantRegistry

if TYPE_CHECKING:
    from pacca.models.resolved_resource import ResolvedResource
    from pacca.models.task_scope import TaskScope


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_args_hash(args: dict) -> str:
    canonical = json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return _sha256(canonical.encode())


def _canonical_resource_digest(resources: list["ResolvedResource"]) -> str:
    dicts = []
    for r in resources:
        dicts.append({
            "realpath": r.realpath,
            "inode": r.inode,
            "mtime_ns": r.mtime_ns,
            "st_size": r.st_size,
            "parent_inode": r.parent_inode,
        })
    canonical = json.dumps(dicts, sort_keys=True, separators=(",", ":"))
    return _sha256(canonical.encode())


class GrantVerifier:
    def __init__(self, registry: UsedGrantRegistry, secret_key: bytes,
                 current_policy_version: str):
        self.registry = registry
        self.secret_key = secret_key
        self.current_policy_version = current_policy_version

    def _sign(self, grant: CapabilityGrant) -> str:
        payload = json.dumps(grant.to_canonical_dict(), sort_keys=True,
                             separators=(",", ":")).encode()
        return hmac.new(self.secret_key, payload, hashlib.sha256).hexdigest()

    def verify(self, grant: CapabilityGrant, tool_name: str, args: dict,
               resources: list["ResolvedResource"],
               task_scope: "TaskScope | None" = None) -> None:

        expected_sig = self._sign(grant)
        if not hmac.compare_digest(grant.signature, expected_sig):
            raise CapabilityViolation("Grant signature invalid")

        if grant.tool_name != tool_name:
            raise CapabilityViolation(
                f"Grant tool_name mismatch: expected {grant.tool_name}, got {tool_name}"
            )

        if time.monotonic() > grant.expires_monotonic:
            raise CapabilityViolation("Grant expired (monotonic clock)")

        actual_args_hash = _canonical_args_hash(args)
        if grant.args_hash != actual_args_hash:
            raise CapabilityViolation("Args hash mismatch")

        if resources:
            actual_resource_digest = _canonical_resource_digest(resources)
            if grant.resolved_resource_digest != actual_resource_digest:
                raise CapabilityViolation("Resolved resource digest mismatch")

        if task_scope and grant.scope_digest != task_scope.scope_digest:
            raise CapabilityViolation("Scope digest mismatch")

        if grant.policy_version != self.current_policy_version:
            raise CapabilityViolation(
                f"Policy version mismatch — registry changed"
            )

        self.registry.consume(grant)
