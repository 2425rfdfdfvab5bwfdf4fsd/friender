"""Tests for CapabilityGrant: HMAC signing, expiry, tamper detection, replay."""
from __future__ import annotations
import dataclasses
import hashlib
import hmac
import json
import time
import pytest
from unittest.mock import MagicMock

from arix.models.capability_grant import CapabilityGrant, CapabilityViolation
from arix.pipeline.policy_engine import PolicyEngine
from arix.security.grant_verifier import GrantVerifier, _canonical_args_hash
from arix.security.used_grant_registry import UsedGrantRegistry

SECRET = b"test-secret-key-32-bytes-padded!!"


def _make_registry(tool_name: str = "list_directory",
                   risk: str = "LOW",
                   requires_confirmation: bool = False) -> dict:
    meta = MagicMock()
    meta.risk_level.value = risk
    meta.requires_confirmation = requires_confirmation
    meta.reversible = True
    return {tool_name: meta}


def _make_scope() -> MagicMock:
    scope = MagicMock()
    scope.scope_digest = "test-scope-digest-001"
    scope.allowed_tools = {"list_directory"}
    scope.allowed_path_prefixes = ["/tmp"]
    return scope


def _make_engine(secret: bytes = SECRET) -> PolicyEngine:
    return PolicyEngine(
        secret_key=secret,
        tool_registry=_make_registry(),
        policy_version="8.0.0",
    )


def _make_verifier(secret: bytes = SECRET,
                   registry: UsedGrantRegistry | None = None) -> GrantVerifier:
    reg = registry or UsedGrantRegistry()
    reg.clear()
    return GrantVerifier(registry=reg, secret_key=secret,
                         current_policy_version="8.0.0")


class TestGrantIssuance:
    def test_grant_has_signature(self):
        engine = _make_engine()
        scope = _make_scope()
        grant = engine.issue_grant("t1", "s1", "list_directory",
                                   {"path": "/tmp"}, [], scope)
        assert grant.signature, "Grant must have a non-empty signature"

    def test_grant_fields_bound(self):
        engine = _make_engine()
        scope = _make_scope()
        grant = engine.issue_grant("task-abc", "step-1", "list_directory",
                                   {"path": "/tmp"}, [], scope)
        assert grant.task_id == "task-abc"
        assert grant.step_id == "step-1"
        assert grant.tool_name == "list_directory"
        assert grant.scope_digest == "test-scope-digest-001"
        assert grant.policy_version == "8.0.0"

    def test_unknown_tool_raises(self):
        engine = _make_engine()
        scope = _make_scope()
        with pytest.raises(CapabilityViolation):
            engine.issue_grant("t1", "s1", "unknown_tool", {}, [], scope)

    def test_args_hash_changes_with_args(self):
        h1 = _canonical_args_hash({"path": "/tmp/a"})
        h2 = _canonical_args_hash({"path": "/tmp/b"})
        assert h1 != h2

    def test_args_hash_deterministic(self):
        h1 = _canonical_args_hash({"b": 2, "a": 1})
        h2 = _canonical_args_hash({"a": 1, "b": 2})
        assert h1 == h2, "Args hash must be order-independent (sorted keys)"


class TestGrantExpiry:
    def test_not_expired_fresh(self):
        engine = _make_engine()
        grant = engine.issue_grant("t1", "s1", "list_directory",
                                   {}, [], _make_scope())
        assert not grant.is_expired()

    def test_expired_grant(self):
        engine = _make_engine()
        scope = _make_scope()
        grant = engine.issue_grant("t1", "s1", "list_directory", {}, [], scope)
        expired = dataclasses.replace(grant, expires_monotonic=time.monotonic() - 1)
        assert expired.is_expired()

    def test_expiry_via_verifier(self):
        """GrantVerifier must reject when monotonic clock is past expires_monotonic."""
        import unittest.mock as mock
        engine = _make_engine()
        scope = _make_scope()
        grant = engine.issue_grant("t1", "s1", "list_directory", {}, [], scope)
        verifier = _make_verifier()
        # Mock time.monotonic to return a time past the grant's expiry
        future = grant.expires_monotonic + 10
        with mock.patch("arix.security.grant_verifier.time.monotonic", return_value=future):
            with pytest.raises(CapabilityViolation):
                verifier.verify(grant, tool_name="list_directory", args={},
                                resources=[], task_scope=None)


class TestGrantTampering:
    def _resign(self, grant: CapabilityGrant, key: bytes) -> str:
        payload = json.dumps(grant.to_canonical_dict(), sort_keys=True,
                             separators=(",", ":")).encode()
        return hmac.new(key, payload, hashlib.sha256).hexdigest()

    def test_tampered_tool_name_detected(self):
        """Changing tool_name after signing must invalidate the signature."""
        engine = _make_engine()
        scope = _make_scope()
        grant = engine.issue_grant("t1", "s1", "list_directory", {}, [], scope)
        tampered = dataclasses.replace(grant, tool_name="delete_file")
        # Original sig vs signature of tampered payload
        tampered_sig = self._resign(tampered, SECRET)
        assert tampered_sig != grant.signature, "Tampered grant must have different signature"

    def test_verifier_rejects_wrong_tool(self):
        engine = _make_engine()
        scope = _make_scope()
        grant = engine.issue_grant("t1", "s1", "list_directory", {}, [], scope)
        verifier = _make_verifier()
        with pytest.raises(CapabilityViolation):
            verifier.verify(grant, tool_name="delete_file", args={},
                            resources=[], task_scope=None)

    def test_verifier_rejects_wrong_args(self):
        engine = _make_engine()
        scope = _make_scope()
        grant = engine.issue_grant("t1", "s1", "list_directory",
                                   {"path": "/tmp"}, [], scope)
        verifier = _make_verifier()
        with pytest.raises(CapabilityViolation):
            verifier.verify(grant, tool_name="list_directory",
                            args={"path": "/other"}, resources=[], task_scope=None)

    def test_different_key_different_signature(self):
        engine1 = _make_engine(b"key-one-32-bytes-padded-securely!!")
        engine2 = _make_engine(b"key-two-32-bytes-padded-securely!!")
        scope = _make_scope()
        g1 = engine1.issue_grant("t1", "s1", "list_directory", {}, [], scope)
        g2 = engine2.issue_grant("t1", "s1", "list_directory", {}, [], scope)
        assert g1.signature != g2.signature


class TestGrantReplay:
    def test_replay_raises_via_verifier(self):
        """Second call to verifier.verify with same grant must raise CapabilityViolation."""
        engine = _make_engine()
        scope = _make_scope()
        grant = engine.issue_grant("t1", "s1", "list_directory", {}, [], scope)
        reg = UsedGrantRegistry()
        reg.clear()
        verifier = GrantVerifier(registry=reg, secret_key=SECRET,
                                 current_policy_version="8.0.0")
        # First use — should pass
        verifier.verify(grant, tool_name="list_directory", args={},
                        resources=[], task_scope=None)
        # Second use — replay
        with pytest.raises(CapabilityViolation):
            verifier.verify(grant, tool_name="list_directory", args={},
                            resources=[], task_scope=None)

    def test_different_nonces_different_grants(self):
        engine = _make_engine()
        scope = _make_scope()
        g1 = engine.issue_grant("t1", "s1", "list_directory", {}, [], scope)
        g2 = engine.issue_grant("t1", "s2", "list_directory", {}, [], scope)
        assert g1.grant_id != g2.grant_id
        assert g1.nonce != g2.nonce
