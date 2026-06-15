"""Tests for CumulativePlanRiskEvaluator."""
import pytest
from unittest.mock import MagicMock
from pacca.pipeline.risk_evaluator import (
    CumulativePlanRiskEvaluator, PROCEED_THRESHOLD, CONFIRM_THRESHOLD
)


def _make_tool(risk: str = "LOW", reversible: bool = True,
               requires_screenshot: bool = False,
               data_egress: bool = False,
               egress_type: str | None = None) -> MagicMock:
    meta = MagicMock()
    meta.risk_level.value = risk
    meta.reversible = reversible
    meta.requires_screenshot = requires_screenshot
    meta.data_egress = data_egress
    meta.egress_type = egress_type
    return meta


def _make_step(tool: str) -> dict:
    return {"step_id": "s1", "tool": tool, "args": {}}


@pytest.fixture
def evaluator():
    return CumulativePlanRiskEvaluator()


class TestLowRiskPlan:
    def test_single_low_risk_step(self, evaluator):
        registry = {"list_directory": _make_tool("LOW")}
        score = evaluator.evaluate([_make_step("list_directory")], registry)
        assert score.total < PROCEED_THRESHOLD
        assert score.gate == "PROCEED"
        assert not score.requires_yes
        assert not score.requires_acknowledge

    def test_empty_plan_zero_score(self, evaluator):
        score = evaluator.evaluate([], {})
        assert score.total == 0.0


class TestHighRiskPlan:
    def test_high_risk_tool_scores_higher(self, evaluator):
        registry = {
            "delete_file": _make_tool("HIGH", reversible=False),
        }
        score = evaluator.evaluate([_make_step("delete_file")], registry)
        low_score = evaluator.evaluate(
            [_make_step("list_directory")],
            {"list_directory": _make_tool("LOW")}
        )
        assert score.total > low_score.total

    def test_critical_risk_requires_confirmation(self, evaluator):
        registry = {"run_code": _make_tool("CRITICAL", reversible=False)}
        steps = [_make_step("run_code")] * 3
        score = evaluator.evaluate(steps, registry)
        # Should be at acknowledgement or yes-required level
        assert score.total >= PROCEED_THRESHOLD or score.requires_yes or score.requires_acknowledge

    def test_irreversible_steps_add_risk(self, evaluator):
        rev = {"copy": _make_tool("LOW", reversible=True)}
        irrev = {"delete": _make_tool("LOW", reversible=False)}
        s_rev = evaluator.evaluate([_make_step("copy")], rev)
        s_irrev = evaluator.evaluate([_make_step("delete")], irrev)
        assert s_irrev.total > s_rev.total


class TestRiskGates:
    def test_gate_values_are_uppercase(self, evaluator):
        """Gate values from the evaluator must be uppercase strings."""
        registry = {"low": _make_tool("LOW")}
        score = evaluator.evaluate([_make_step("low")], registry)
        assert score.gate in ("PROCEED", "ACKNOWLEDGE", "YES_REQUIRED")

    def test_gate_proceed_for_low_risk(self, evaluator):
        registry = {"low": _make_tool("LOW")}
        score = evaluator.evaluate([_make_step("low")], registry)
        assert score.gate == "PROCEED"

    def test_breakdown_sums_to_total(self, evaluator):
        registry = {
            "high_tool": _make_tool("HIGH", reversible=False),
            "low_tool": _make_tool("LOW"),
        }
        steps = [_make_step("high_tool"), _make_step("low_tool")]
        score = evaluator.evaluate(steps, registry)
        assert abs(sum(score.breakdown.values()) - score.total) < 0.01
