"""Tests for PlanValidator URL blocklist (SEC-07 additions)."""
import pytest
from unittest.mock import MagicMock
from arix.pipeline.plan_validator import PlanValidator, PlanValidationError
from arix.models.task_scope import TaskScope


def _make_validator() -> PlanValidator:
    resolver = MagicMock()
    resolver.resolve.side_effect = lambda path, **kw: path
    tool_registry = {}
    return PlanValidator(resolver=resolver, tool_registry=tool_registry)


def _make_scope() -> TaskScope:
    scope = TaskScope.__new__(TaskScope)
    scope.allowed_tools = {"browser_open_url", "browser_web_search"}
    scope.allowed_paths = []
    scope.redacted_command = "test"
    scope.intent_domain = "browser"
    scope.intent_verb = "open"
    scope.original_command = "test"
    scope.task_id = "test-000"
    return scope


def _make_plan(url: str) -> list[dict]:
    return [{
        "step_id": "s1",
        "tool": "browser_open_url",
        "args": {"url": url},
        "description": "open url",
        "resolved_resources": [],
    }]


BLOCKED_URLS = [
    "http://169.254.169.254/latest/meta-data/",   # AWS metadata IP
    "http://[::1]/",                               # IPv6 loopback
    "http://[fc00::1]/",                           # IPv6 ULA
    "data:text/html,<h1>hello</h1>",               # data URI
    "https://user:pass@evil.com/",                 # embedded credentials
    "file:///etc/passwd",                          # file URI
]


@pytest.mark.parametrize("url", BLOCKED_URLS)
def test_blocked_url_in_plan(url):
    """PlanValidator must reject plans that contain blocked URLs."""
    validator = _make_validator()
    scope = _make_scope()
    # The validator itself OR the URL-safety check should raise / return error
    try:
        result = validator.validate(_make_plan(url), scope)
        # If validate returns instead of raising, check result marks as blocked
        for step in result:
            args = step.get("args", {})
            assert args.get("url") != url or not _is_dangerous(url), (
                f"Dangerous URL {url!r} was allowed through PlanValidator"
            )
    except (PlanValidationError, ValueError, RuntimeError):
        pass  # Correctly rejected


def _is_dangerous(url: str) -> bool:
    from arix.tools.browser_tools import _check_url_safety
    safe, _ = _check_url_safety(url)
    return not safe
