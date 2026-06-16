"""GitSafetyChecker — pre-flight checks before git operations."""
from __future__ import annotations
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from arix.security.local_text_redactor import REDACTION_PATTERNS


class GitSafetyError(Exception):
    pass


GIT_ALLOWED_SUBCOMMANDS = frozenset({"status", "diff", "add", "commit"})

EXECUTABLE_EXTENSIONS = {
    ".exe", ".sh", ".bat", ".ps1", ".py", ".rb", ".pl",
    ".dmg", ".pkg", ".deb", ".rpm", ".msi", ".cmd", ".vbs",
}


@dataclass
class GitSafetyReport:
    repo_path: str
    has_hooks: bool = False
    hook_names: list[str] = field(default_factory=list)
    has_lfs: bool = False
    has_submodules: bool = False
    has_credential_helpers: bool = False
    unsafe_configs: list[str] = field(default_factory=list)
    secret_matches: list[str] = field(default_factory=list)
    risk_level: Literal["OK", "WARN", "BLOCK"] = "OK"


def run_git(subcommand: str, *args: str, repo_path: str,
            timeout: int = 30) -> subprocess.CompletedProcess:
    if subcommand not in GIT_ALLOWED_SUBCOMMANDS:
        raise GitSafetyError(f"Git subcommand '{subcommand}' not allowed in v1.0")
    cmd = ["git", "-C", repo_path, subcommand, *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


class GitSafetyChecker:
    def check_repo(self, repo_path: str) -> GitSafetyReport:
        report = GitSafetyReport(repo_path=repo_path)

        hooks_dir = Path(repo_path) / ".git" / "hooks"
        if hooks_dir.exists():
            for hook in hooks_dir.iterdir():
                if hook.is_file() and os.access(hook, os.X_OK) and not hook.suffix == ".sample":
                    report.has_hooks = True
                    report.hook_names.append(hook.name)

        gitattributes = Path(repo_path) / ".gitattributes"
        if gitattributes.exists():
            try:
                content = gitattributes.read_text(errors="replace")
                if "filter=lfs" in content:
                    report.has_lfs = True
                    report.risk_level = "WARN"
            except OSError:
                pass

        gitmodules = Path(repo_path) / ".gitmodules"
        if gitmodules.exists():
            report.has_submodules = True
            report.risk_level = "WARN"

        try:
            result = subprocess.run(
                ["git", "-C", repo_path, "config", "--list"],
                capture_output=True, text=True, timeout=10
            )
            config_lines = result.stdout.splitlines()
            for line in config_lines:
                if line.startswith("credential.helper"):
                    report.has_credential_helpers = True
                for unsafe_key in ("core.fsmonitor", "diff.external",
                                   "merge.tool", "filter."):
                    if unsafe_key in line.split("=")[0]:
                        report.unsafe_configs.append(line)
                        report.risk_level = "WARN"
        except Exception:
            pass

        return report

    def scan_staged_diff_for_secrets(self, repo_path: str) -> list[str]:
        try:
            result = run_git("diff", "--cached", repo_path=repo_path)
            diff = result.stdout
        except Exception:
            return []

        matches = []
        for name, pattern in REDACTION_PATTERNS:
            if pattern.search(diff):
                matches.append(f"{name} pattern matched in staged diff")
        return matches

    def scan_text_for_secrets(self, text: str) -> list[str]:
        matches = []
        for name, pattern in REDACTION_PATTERNS:
            if pattern.search(text):
                matches.append(name)
        return matches
