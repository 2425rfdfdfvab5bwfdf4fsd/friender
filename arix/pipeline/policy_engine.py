"""PolicyEngine — issues single-use Capability Grants per step."""
from __future__ import annotations
import hashlib
import hmac
import json
import secrets
import time
import uuid
from typing import Any

from arix.models.capability_grant import CapabilityGrant, CapabilityViolation
from arix.models.resolved_resource import ResolvedResource
from arix.models.task_scope import TaskScope
from arix.security.grant_verifier import (
    _canonical_args_hash, _canonical_resource_digest
)

GRANT_TTL_SECONDS = 300


class PolicyEngine:
    def __init__(self, secret_key: bytes, tool_registry: dict[str, Any],
                 policy_version: str):
        self.secret_key = secret_key
        self.tool_registry = tool_registry
        self.policy_version = policy_version

    def _sign(self, grant: CapabilityGrant) -> str:
        payload = json.dumps(
            grant.to_canonical_dict(), sort_keys=True, separators=(",", ":")
        ).encode()
        return hmac.new(self.secret_key, payload, hashlib.sha256).hexdigest()

    def issue_grant(self, task_id: str, step_id: str, tool_name: str,
                    args: dict, resources: list[ResolvedResource],
                    task_scope: TaskScope,
                    confirmation_receipt_id: str | None = None) -> CapabilityGrant:
        meta = self.tool_registry.get(tool_name)
        if not meta:
            raise CapabilityViolation(f"Tool '{tool_name}' not in registry")

        now = time.time()
        mono_now = time.monotonic()
        grant_id = str(uuid.uuid4())
        nonce = secrets.token_hex(16)

        args_hash = _canonical_args_hash(args)
        resource_digest = _canonical_resource_digest(resources) if resources else _canonical_resource_digest([])

        grant = CapabilityGrant(
            grant_id=grant_id,
            nonce=nonce,
            task_id=task_id,
            step_id=step_id,
            tool_name=tool_name,
            args_hash=args_hash,
            resolved_resource_digest=resource_digest,
            scope_digest=task_scope.scope_digest,
            policy_version=self.policy_version,
            confirmation_receipt_id=confirmation_receipt_id,
            issued_at=now,
            issued_monotonic=mono_now,
            expires_at=now + GRANT_TTL_SECONDS,
            expires_monotonic=mono_now + GRANT_TTL_SECONDS,
        )

        sig = self._sign(grant)
        object.__setattr__(grant, "signature", sig)
        return grant

    def needs_confirmation(self, tool_name: str) -> bool:
        meta = self.tool_registry.get(tool_name)
        if not meta:
            return True
        return getattr(meta, "requires_confirmation", False)
