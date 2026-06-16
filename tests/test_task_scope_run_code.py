"""Tests for run_code in DOMAIN_TOOL_MAP (REL-06)."""
import pytest
from arix.models.task_scope import DOMAIN_TOOL_MAP


def test_run_code_in_coding_domain():
    """run_code must be in the coding domain so TaskScope allows it."""
    coding_tools = DOMAIN_TOOL_MAP.get("coding", set())
    assert "run_code" in coding_tools, (
        "run_code is missing from DOMAIN_TOOL_MAP['coding'] — REL-06 regression"
    )


def test_all_domain_tool_maps_are_sets():
    """All domain → tools mappings should be frozensets or sets."""
    for domain, tools in DOMAIN_TOOL_MAP.items():
        assert hasattr(tools, "__contains__"), (
            f"DOMAIN_TOOL_MAP[{domain!r}] should be a set-like object"
        )
