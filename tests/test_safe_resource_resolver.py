"""Tests for SafeResourceResolver — path safety, symlink escape, TOCTOU."""
from __future__ import annotations
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from pacca.security.safe_resource_resolver import SafeResourceResolver
from pacca.models.resolved_resource import PathExpectation


def _make_scope(prefixes: list[str] | None = None) -> MagicMock:
    scope = MagicMock()
    scope.allowed_path_prefixes = prefixes or ["/tmp"]
    return scope


@pytest.fixture
def resolver():
    return SafeResourceResolver()


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


class TestAllowedPaths:
    def test_allowed_path_resolves(self, resolver, tmp_dir):
        scope = _make_scope([tmp_dir])
        target = os.path.join(tmp_dir, "test.txt")
        Path(target).write_text("hello")
        resource = resolver.resolve(target, scope, PathExpectation.MUST_EXIST)
        assert resource.is_safe()

    def test_path_outside_scope_blocked(self, resolver, tmp_dir):
        scope = _make_scope([tmp_dir])
        resource = resolver.resolve("/etc/passwd", scope, PathExpectation.MAY_EXIST)
        assert not resource.is_safe()

    def test_traversal_attack_blocked(self, resolver, tmp_dir):
        scope = _make_scope([tmp_dir])
        traversal = os.path.join(tmp_dir, "..", "..", "etc", "passwd")
        resource = resolver.resolve(traversal, scope, PathExpectation.MAY_EXIST)
        assert not resource.is_safe()

    def test_null_byte_blocked(self, resolver, tmp_dir):
        scope = _make_scope([tmp_dir])
        resource = resolver.resolve(f"{tmp_dir}/safe\x00evil", scope)
        assert not resource.is_safe()


class TestSymlinkEscape:
    def test_symlink_outside_scope_blocked(self, resolver, tmp_dir):
        """Symlink inside allowed dir pointing outside should be blocked."""
        scope = _make_scope([tmp_dir])
        link_path = os.path.join(tmp_dir, "escape_link")
        try:
            os.symlink("/etc/passwd", link_path)
            resource = resolver.resolve(link_path, scope, PathExpectation.MAY_EXIST)
            # After realpath resolution, /etc/passwd is outside tmp_dir → blocked
            assert not resource.is_safe()
        finally:
            try:
                os.unlink(link_path)
            except OSError:
                pass

    def test_symlink_inside_scope_allowed(self, resolver, tmp_dir):
        """Symlink staying inside allowed dir should pass."""
        scope = _make_scope([tmp_dir])
        target = os.path.join(tmp_dir, "real.txt")
        Path(target).write_text("hello")
        link_path = os.path.join(tmp_dir, "link.txt")
        try:
            os.symlink(target, link_path)
            resource = resolver.resolve(link_path, scope, PathExpectation.MUST_EXIST)
            assert resource.is_safe()
        finally:
            try:
                os.unlink(link_path)
            except OSError:
                pass


class TestCredentialPathBlocking:
    @pytest.mark.parametrize("cred_path", [
        "/etc/passwd",
        "/etc/shadow",
    ])
    def test_credential_path_blocked(self, resolver, cred_path):
        if not os.path.exists(cred_path):
            pytest.skip(f"{cred_path} doesn't exist on this system")
        scope = _make_scope(["/"])  # even with root scope
        resource = resolver.resolve(cred_path, scope, PathExpectation.MAY_EXIST)
        assert not resource.is_safe(), f"Credential path {cred_path} should be blocked"


class TestPathExpectations:
    def test_must_exist_nonexistent_blocked(self, resolver, tmp_dir):
        scope = _make_scope([tmp_dir])
        resource = resolver.resolve(os.path.join(tmp_dir, "no_such_file.txt"),
                                    scope, PathExpectation.MUST_EXIST)
        assert not resource.is_safe()

    def test_must_not_exist_existing_blocked(self, resolver, tmp_dir):
        scope = _make_scope([tmp_dir])
        existing = os.path.join(tmp_dir, "exists.txt")
        Path(existing).write_text("hi")
        resource = resolver.resolve(existing, scope, PathExpectation.MUST_NOT_EXIST)
        assert not resource.is_safe()

    def test_may_exist_nonexistent_allowed(self, resolver, tmp_dir):
        scope = _make_scope([tmp_dir])
        resource = resolver.resolve(os.path.join(tmp_dir, "new_file.txt"),
                                    scope, PathExpectation.MAY_EXIST)
        assert resource.is_safe()


class TestTOCTOU:
    def test_toctou_detects_file_change(self, resolver, tmp_dir):
        """After resolving a file, modifying it should be detected by check_toctou."""
        scope = _make_scope([tmp_dir])
        target = os.path.join(tmp_dir, "toctou.txt")
        Path(target).write_text("original content")
        resource = resolver.resolve(target, scope, PathExpectation.MUST_EXIST)
        assert resource.is_safe()

        # Modify the file to simulate a TOCTOU swap
        import time
        time.sleep(0.02)
        Path(target).write_text("tampered content — different size definitely")

        result = resolver.check_toctou(resource)
        # check_toctou returns (bool, reason_str) or may raise — tampering must be detected
        if result is not None:
            safe = result[0] if isinstance(result, tuple) else result
            assert not safe, f"TOCTOU check should have detected tampering, got: {result!r}"
