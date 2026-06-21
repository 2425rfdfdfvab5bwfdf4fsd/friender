"""SafeResourceResolver — single source of truth for path resolution and token issuance."""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from arix.models.resolved_resource import ResolvedResource, PathExpectation

if TYPE_CHECKING:
    from arix.models.task_scope import TaskScope

CREDENTIAL_PATHS = [
    "~/.ssh", "~/.aws", "~/.gnupg", "~/.netrc", "~/.npmrc",
    "~/.pypirc", "~/.docker/config.json", "~/.config/gcloud",
    "~/.azure", "~/.kube/config", "/etc/passwd", "/etc/shadow",
    "/etc/sudoers", "/etc/hosts",
]

WINDOWS_DEVICE_NAMES = frozenset({
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
})


class ResourceTokenError(Exception):
    pass


class SafeResourceResolver:
    """
    The only place where path resolution, validation, and resource handle issuance occurs.
    Tools receive opaque PathCapability tokens, not raw path strings.
    """

    def __init__(self, secret_key: bytes | None = None):
        self._secret_key = secret_key or secrets.token_bytes(32)
        self._token_store: dict[str, tuple[str, float]] = {}
        self._credential_paths = [
            os.path.realpath(os.path.expanduser(p))
            for p in CREDENTIAL_PATHS
            if os.path.exists(os.path.expanduser(p))
        ] + [os.path.expanduser(p) for p in CREDENTIAL_PATHS]

    def resolve(self, raw_path: str, task_scope: "TaskScope | None",
                expectation: PathExpectation = PathExpectation.MAY_EXIST) -> ResolvedResource:
        t = time.monotonic()
        wall = time.time()

        path_variant = self._classify_path_variant(raw_path)
        if path_variant not in ("normal", "hardlink", "reparse_point"):
            return self._blocked(raw_path, cast(Literal["normal", "unc", "device", "nt_namespace", "ads", "short_name", "trailing_dot_space", "hardlink", "reparse_point"], path_variant), t, wall,
                                 f"Unsafe path variant: {path_variant}")

        expanded = os.path.expanduser(os.path.expandvars(raw_path))
        if '\x00' in expanded:
            return self._blocked(raw_path, cast(Literal["normal", "unc", "device", "nt_namespace", "ads", "short_name", "trailing_dot_space", "hardlink", "reparse_point"], path_variant), t, wall, "Null byte in path")

        absolute_path = os.path.abspath(expanded)
        realpath = os.path.realpath(absolute_path)

        blocked = self._check_credential_path(realpath)
        if blocked:
            return self._blocked(raw_path, cast(Literal["normal", "unc", "device", "nt_namespace", "ads", "short_name", "trailing_dot_space", "hardlink", "reparse_point"], path_variant), t, wall, blocked)

        within_scope = True
        if task_scope and task_scope.allowed_path_prefixes:
            within_scope = any(
                realpath.startswith(prefix)
                for prefix in task_scope.allowed_path_prefixes
            )

        exists = os.path.exists(realpath)
        is_dir = os.path.isdir(realpath) if exists else False

        if expectation == PathExpectation.MUST_EXIST and not exists:
            return self._blocked(raw_path, cast(Literal["normal", "unc", "device", "nt_namespace", "ads", "short_name", "trailing_dot_space", "hardlink", "reparse_point"], path_variant), t, wall,
                                 f"Path does not exist: {realpath}")
        if expectation == PathExpectation.MUST_NOT_EXIST and exists:
            return self._blocked(raw_path, cast(Literal["normal", "unc", "device", "nt_namespace", "ads", "short_name", "trailing_dot_space", "hardlink", "reparse_point"], path_variant), t, wall,
                                 f"Path already exists: {realpath}")

        inode = mtime_ns = st_size = st_dev = None
        parent_inode = parent_dev = 0
        win_file_id = None
        variant = path_variant

        if exists:
            try:
                st = os.stat(realpath)
                inode = st.st_ino
                mtime_ns = st.st_mtime_ns
                st_size = st.st_size
                st_dev = st.st_dev
                if st.st_nlink > 1 and not is_dir:
                    variant = "hardlink"
            except OSError:
                pass

        parent = os.path.dirname(realpath)
        try:
            pst = os.stat(parent)
            parent_inode = pst.st_ino
            parent_dev = pst.st_dev
        except OSError:
            pass

        if is_dir:
            path_type = "existing_dir"
        elif exists:
            path_type = "existing_file"
        else:
            path_type = "nonexistent"

        nonce = secrets.token_hex(16)
        token = self._issue_token(realpath, t, nonce)

        blocked_reason = None if within_scope else "Path outside allowed scope"

        return ResolvedResource(
            raw_input=raw_path,
            path_type=path_type,
            path_variant=cast(Literal["normal", "unc", "device", "nt_namespace", "ads", "short_name", "trailing_dot_space", "hardlink", "reparse_point"], variant),
            absolute_path=absolute_path,
            realpath=realpath,
            inode=inode,
            mtime_ns=mtime_ns,
            st_size=st_size,
            st_dev=st_dev,
            win_file_id=win_file_id,
            parent_realpath=parent,
            parent_inode=parent_inode,
            parent_dev=parent_dev,
            within_scope=within_scope,
            blocked_reason=blocked_reason,
            resolved_at=wall,
            resolved_monotonic=t,
            capability_token=token,
            capability_nonce=nonce,
        )

    def _issue_token(self, realpath: str, resolved_monotonic: float, nonce: str) -> str:
        payload = f"{realpath}:{resolved_monotonic}:{nonce}".encode()
        token = hmac.new(self._secret_key, payload, hashlib.sha256).hexdigest()
        self._token_store[token] = (realpath, resolved_monotonic)
        return token

    def verify_token(self, token: str, realpath: str, resolved_monotonic: float,
                     nonce: str) -> bool:
        payload = f"{realpath}:{resolved_monotonic}:{nonce}".encode()
        expected = hmac.new(self._secret_key, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(token, expected)

    def check_toctou(self, resource: ResolvedResource) -> tuple[bool, str]:
        """Re-stat and compare inode+mtime_ns+st_size+parent_inode to detect tampering."""
        if resource.path_type in ("nonexistent", "new_file_target", "new_dir_target"):
            parent = resource.parent_realpath
            try:
                pst = os.stat(parent)
                if pst.st_ino != resource.parent_inode:
                    return False, "Parent directory inode changed — possible rename attack"
            except OSError as e:
                return False, f"Cannot re-stat parent: {e}"
            return True, ""

        try:
            st = os.stat(resource.realpath)
        except OSError as e:
            return False, f"Cannot re-stat path: {e}"

        if st.st_ino != resource.inode:
            return False, f"Inode changed ({resource.inode} → {st.st_ino})"
        if st.st_mtime_ns != resource.mtime_ns:
            return False, f"mtime changed — file may have been replaced"
        if st.st_size != resource.st_size:
            return False, f"File size changed ({resource.st_size} → {st.st_size})"

        parent = resource.parent_realpath
        try:
            pst = os.stat(parent)
            if pst.st_ino != resource.parent_inode:
                return False, "Parent directory inode changed"
        except OSError:
            pass

        return True, ""

    def _classify_path_variant(self, path: str) -> str:
        if sys.platform == "win32":
            if path.startswith("\\\\?\\") or path.startswith("\\\\.\\"):
                return "nt_namespace"
            if path.startswith("\\\\"):
                return "unc"
            stem = Path(path).stem.upper()
            if stem in WINDOWS_DEVICE_NAMES:
                return "device"
            if ":" in Path(path).name and not (len(path) >= 2 and path[1] == ":"):
                return "ads"
            if path.rstrip() != path or path.rstrip(".") != path:
                return "trailing_dot_space"
        return "normal"

    def _check_credential_path(self, realpath: str) -> str | None:
        for cred_path in self._credential_paths:
            if realpath == cred_path or realpath.startswith(cred_path + os.sep):
                return f"Access blocked: credential path ({cred_path})"
        return None

    def _blocked(self, raw_input: str, variant: str, mono: float, wall: float,
                 reason: str) -> ResolvedResource:
        nonce = secrets.token_hex(16)
        return ResolvedResource(
            raw_input=raw_input,
            path_type="nonexistent",
            path_variant=cast(Literal["normal", "unc", "device", "nt_namespace", "ads", "short_name", "trailing_dot_space", "hardlink", "reparse_point"], variant),
            absolute_path="",
            realpath="",
            inode=None, mtime_ns=None, st_size=None, st_dev=None, win_file_id=None,
            parent_realpath="",
            parent_inode=0, parent_dev=0,
            within_scope=False,
            blocked_reason=reason,
            resolved_at=wall,
            resolved_monotonic=mono,
            capability_token="",
            capability_nonce=nonce,
        )
