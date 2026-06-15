"""Tests for the persistent UsedGrantRegistry (SEC-03)."""
import time
import pytest
from unittest.mock import MagicMock
from pacca.security.used_grant_registry import UsedGrantRegistry
from pacca.models.capability_grant import CapabilityViolation


def _make_grant(grant_id: str = "grant-001", expires_at: float | None = None) -> MagicMock:
    g = MagicMock()
    g.grant_id = grant_id
    g.expires_at = expires_at or (time.time() + 300)
    return g


def test_consume_first_time():
    reg = UsedGrantRegistry()
    reg.clear()
    grant = _make_grant("test-first-001")
    reg.consume(grant)
    assert reg.is_consumed("test-first-001")


def test_replay_raises():
    reg = UsedGrantRegistry()
    reg.clear()
    grant = _make_grant("test-replay-001")
    reg.consume(grant)
    with pytest.raises(CapabilityViolation):
        reg.consume(grant)


def test_persistence_across_instances(tmp_path, monkeypatch):
    """Grant consumed in one registry instance is blocked in a new instance."""
    import pacca.security.used_grant_registry as ugr_module
    db_path = tmp_path / "grants.db"
    monkeypatch.setattr(ugr_module, "_GRANTS_DB", db_path)
    monkeypatch.setattr(ugr_module, "PACCA_DIR", tmp_path)

    grant = _make_grant("test-persist-001")

    reg1 = UsedGrantRegistry()
    reg1.consume(grant)

    reg2 = UsedGrantRegistry()
    assert reg2.is_consumed("test-persist-001")


def test_clear():
    reg = UsedGrantRegistry()
    reg.clear()
    grant = _make_grant("test-clear-001")
    reg.consume(grant)
    reg.clear()
    assert not reg.is_consumed("test-clear-001")
