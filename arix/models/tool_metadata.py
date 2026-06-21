"""ToolMetadata — capability metadata for every tool in the registry."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Callable


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class ToolMetadata:
    name: str
    description: str
    risk_level: RiskLevel
    reversible: bool
    reversible_notes: str | None
    requires_confirmation: bool
    conditional_confirmation_rules: list[str]
    data_egress: bool
    egress_type: Literal["none", "cloud_content", "cloud_metadata", "browser", "outbound_api", "api_call"] | None
    network_behavior: str | None
    path_scope_required: bool
    max_files_without_confirmation: int | None
    max_total_bytes_without_confirmation: int | None
    overwrite_policy: Literal["block", "confirm", "allow"]
    secret_scan_required: bool
    requires_diff_preview: bool
    dry_run_supported: bool
    undo_supported: bool
    atomic: bool
    requires_screenshot: bool
    can_indirectly_execute_code: bool
    code_execution_mitigations: list[str] | None
    platforms: list[str]
    domain: str
    allowed_in_macro: bool = False
    batchable: bool = False
    idempotent: bool = False
    allowed_egress_destinations: list[str] | None = None
    undo_fn: Callable | None = None
