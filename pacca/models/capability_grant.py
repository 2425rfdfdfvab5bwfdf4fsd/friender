"""CapabilityGrant — single-use HMAC-signed authorization for one tool call."""
from __future__ import annotations
import time
import threading
from dataclasses import dataclass, field
from typing import Literal


class CapabilityViolation(Exception):
    pass


@dataclass(frozen=True)
class CapabilityGrant:
    grant_id: str
    nonce: str

    task_id: str
    step_id: str
    tool_name: str
    args_hash: str
    resolved_resource_digest: str
    scope_digest: str

    policy_version: str
    confirmation_receipt_id: str | None

    issued_at: float
    issued_monotonic: float
    expires_at: float
    expires_monotonic: float

    issued_by: Literal["policy_engine"] = "policy_engine"
    signature: str = ""

    consumed_at: float | None = None

    def is_expired(self) -> bool:
        return time.monotonic() > self.expires_monotonic

    def to_canonical_dict(self) -> dict:
        return {
            "grant_id": self.grant_id,
            "nonce": self.nonce,
            "task_id": self.task_id,
            "step_id": self.step_id,
            "tool_name": self.tool_name,
            "args_hash": self.args_hash,
            "resolved_resource_digest": self.resolved_resource_digest,
            "scope_digest": self.scope_digest,
            "policy_version": self.policy_version,
            "issued_monotonic": self.issued_monotonic,
            "expires_monotonic": self.expires_monotonic,
        }
