"""UsedGrantRegistry — prevents Capability Grant replay."""
from __future__ import annotations
import threading
from pacca.models.capability_grant import CapabilityGrant, CapabilityViolation


class UsedGrantRegistry:
    """
    In-memory set of consumed grant_ids. Cleared on process restart.
    Checked and updated atomically under threading.Lock.
    """

    def __init__(self) -> None:
        self._consumed: set[str] = set()
        self._lock = threading.Lock()

    def consume(self, grant: CapabilityGrant) -> None:
        with self._lock:
            if grant.grant_id in self._consumed:
                raise CapabilityViolation(
                    f"Grant {grant.grant_id} already consumed — replay prevented"
                )
            self._consumed.add(grant.grant_id)

    def is_consumed(self, grant_id: str) -> bool:
        with self._lock:
            return grant_id in self._consumed

    def clear(self) -> None:
        with self._lock:
            self._consumed.clear()

    def count(self) -> int:
        with self._lock:
            return len(self._consumed)
