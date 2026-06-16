"""Tests for new v8.0 config fields (SEC-01, REL-03)."""
import pytest
from arix.config import ArixConfig


def test_tool_timeout_seconds_default():
    cfg = ArixConfig()
    assert hasattr(cfg, "tool_timeout_seconds")
    assert cfg.tool_timeout_seconds == 60


def test_require_auth_default():
    cfg = ArixConfig()
    assert hasattr(cfg, "require_auth")
    assert cfg.require_auth is False


def test_allowed_ws_origins_default():
    cfg = ArixConfig()
    assert hasattr(cfg, "allowed_ws_origins")
    assert isinstance(cfg.allowed_ws_origins, list)


def test_rate_limit_defaults():
    cfg = ArixConfig()
    assert cfg.api_rate_limit_per_minute > 0
    assert cfg.ws_command_rate_limit_per_minute > 0
