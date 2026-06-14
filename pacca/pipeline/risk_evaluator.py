"""CumulativePlanRiskEvaluator — scores an entire plan before execution."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any


WEIGHTS = {
    "files_affected": 1,
    "bytes_read": 0.0005,
    "bytes_written": 0.001,
    "read_egress_events": 3,
    "write_egress_events": 10,
    "screenshot_calls": 2,
    "network_calls": 5,
    "irreversible_steps": 15,
    "high_risk_tools": 20,
    "critical_risk_tools": 50,
}

PROCEED_THRESHOLD = 30
CONFIRM_THRESHOLD = 100


@dataclass
class RiskScore:
    total: float
    breakdown: dict[str, float]
    gate: str
    requires_yes: bool
    requires_acknowledge: bool


class CumulativePlanRiskEvaluator:
    def __init__(self, proceed_threshold: float = PROCEED_THRESHOLD,
                 confirm_threshold: float = CONFIRM_THRESHOLD):
        self.proceed_threshold = proceed_threshold
        self.confirm_threshold = confirm_threshold

    def evaluate(self, validated_steps: list[dict],
                 tool_registry: dict[str, Any]) -> RiskScore:
        counters: dict[str, float] = {k: 0.0 for k in WEIGHTS}

        for step in validated_steps:
            tool_name = step["tool"]
            meta = tool_registry.get(tool_name)
            if not meta:
                continue

            counters["files_affected"] += 1

            risk = getattr(meta, "risk_level", None)
            if risk is not None:
                risk_str = risk.value if hasattr(risk, "value") else str(risk)
                if risk_str == "HIGH":
                    counters["high_risk_tools"] += 1
                elif risk_str == "CRITICAL":
                    counters["critical_risk_tools"] += 1

            if not getattr(meta, "reversible", True):
                counters["irreversible_steps"] += 1

            if getattr(meta, "requires_screenshot", False):
                counters["screenshot_calls"] += 1

            if getattr(meta, "data_egress", False):
                if risk_str in ("HIGH", "CRITICAL"):
                    counters["write_egress_events"] += 1
                else:
                    counters["read_egress_events"] += 1

            egress_type = getattr(meta, "egress_type", None)
            if egress_type == "browser":
                counters["network_calls"] += 1

        breakdown: dict[str, float] = {}
        total = 0.0
        for factor, count in counters.items():
            weight = WEIGHTS.get(factor, 0)
            contribution = count * weight
            if contribution > 0:
                breakdown[factor] = contribution
            total += contribution

        if total > self.confirm_threshold:
            gate = "YES_REQUIRED"
            requires_yes = True
            requires_acknowledge = False
        elif total > self.proceed_threshold:
            gate = "ACKNOWLEDGE"
            requires_yes = False
            requires_acknowledge = True
        else:
            gate = "PROCEED"
            requires_yes = False
            requires_acknowledge = False

        return RiskScore(
            total=total,
            breakdown=breakdown,
            gate=gate,
            requires_yes=requires_yes,
            requires_acknowledge=requires_acknowledge,
        )
