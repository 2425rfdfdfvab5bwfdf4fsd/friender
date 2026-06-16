"""ResolvedResource — output of SafeResourceResolver."""
from __future__ import annotations
import time
from dataclasses import dataclass
from enum import Enum
from typing import Literal


class PathExpectation(Enum):
    MUST_EXIST = "must_exist"
    MUST_NOT_EXIST = "must_not_exist"
    MAY_EXIST = "may_exist"
    PARENT_ONLY = "parent_only"


@dataclass(frozen=True)
class ResolvedResource:
    raw_input: str

    path_type: Literal[
        "existing_file", "existing_dir", "nonexistent",
        "new_file_target", "new_dir_target",
    ]
    path_variant: Literal[
        "normal", "unc", "device", "nt_namespace", "ads",
        "short_name", "trailing_dot_space", "hardlink", "reparse_point",
    ]

    absolute_path: str
    realpath: str

    inode: int | None
    mtime_ns: int | None
    st_size: int | None
    st_dev: int | None
    win_file_id: tuple | None

    parent_realpath: str
    parent_inode: int
    parent_dev: int

    within_scope: bool
    blocked_reason: str | None

    resolved_at: float
    resolved_monotonic: float

    capability_token: str
    capability_nonce: str

    def is_safe(self) -> bool:
        return self.within_scope and self.blocked_reason is None

    def stat_tuple(self) -> tuple:
        return (self.inode, self.mtime_ns, self.st_size, self.parent_inode)
