"""Git tools — git_status, git_diff, git_add, git_commit."""
from __future__ import annotations
import os
from pathlib import Path

from arix.security.git_safety import (
    GitSafetyChecker, GitSafetyError, run_git, GIT_ALLOWED_SUBCOMMANDS
)


def _find_git_root(path: str) -> str | None:
    p = Path(path).resolve()
    while p != p.parent:
        if (p / ".git").exists():
            return str(p)
        p = p.parent
    return None


def git_status(repo_path: str) -> dict:
    root = _find_git_root(repo_path)
    if not root:
        return {"error": f"Not a git repository: {repo_path}"}
    try:
        result = run_git("status", "--porcelain", "--branch", repo_path=root)
        if result.returncode != 0:
            return {"error": result.stderr.strip()}
        lines = result.stdout.splitlines()
        branch = ""
        changes = []
        for line in lines:
            if line.startswith("##"):
                branch = line[3:].split("...")[0].strip()
            elif line.strip():
                status_code = line[:2].strip()
                filename = line[3:].strip()
                changes.append({"status": status_code, "file": filename})
        return {
            "repo": root,
            "branch": branch,
            "changes": changes,
            "clean": len(changes) == 0,
        }
    except Exception as e:
        return {"error": str(e)}


def git_diff(repo_path: str, staged: bool = False,
             file_path: str | None = None) -> dict:
    root = _find_git_root(repo_path)
    if not root:
        return {"error": f"Not a git repository: {repo_path}"}

    checker = GitSafetyChecker()
    args = []
    if staged:
        args.append("--cached")
    if file_path:
        args.extend(["--", file_path])

    try:
        result = run_git("diff", *args, repo_path=root)
        if result.returncode != 0:
            return {"error": result.stderr.strip()}

        diff_text = result.stdout
        secrets = checker.scan_text_for_secrets(diff_text)

        return {
            "repo": root,
            "staged": staged,
            "diff": diff_text[:32768],
            "truncated": len(diff_text) > 32768,
            "secret_warnings": secrets,
            "lines": len(diff_text.splitlines()),
        }
    except Exception as e:
        return {"error": str(e)}


def git_add(repo_path: str, paths: list[str] | None = None,
            all_changes: bool = False, dry_run: bool = False) -> dict:
    root = _find_git_root(repo_path)
    if not root:
        return {"error": f"Not a git repository: {repo_path}"}

    checker = GitSafetyChecker()
    report = checker.check_repo(root)

    if report.has_lfs:
        return {
            "warning": "Repository uses Git LFS — LFS filter may trigger external calls",
            "requires_confirmation": True,
            "repo": root,
        }

    if dry_run:
        return {"dry_run": True, "repo": root,
                "would_add": paths or ["ALL changes"]}

    args = []
    if all_changes:
        args.append("-A")
    elif paths:
        args.extend(paths)
    else:
        args.append(".")

    try:
        result = run_git("add", *args, repo_path=root)
        if result.returncode != 0:
            return {"error": result.stderr.strip()}

        secrets = checker.scan_staged_diff_for_secrets(root)
        if secrets:
            try:
                import subprocess as _sp
                _sp.run(["git", "-C", root, "reset", "HEAD"],
                        capture_output=True, timeout=30)
            except Exception:
                pass
            return {
                "error": "Secret detected in staged files — git add reversed",
                "blocked": True,
                "patterns": secrets,
            }

        staged_result = run_git("diff", "--cached", "--name-only", repo_path=root)
        staged_files = staged_result.stdout.strip().splitlines()
        return {
            "staged": staged_files,
            "repo": root,
            "count": len(staged_files),
        }
    except Exception as e:
        return {"error": str(e)}


def git_commit(repo_path: str, message: str,
               dry_run: bool = False) -> dict:
    root = _find_git_root(repo_path)
    if not root:
        return {"error": f"Not a git repository: {repo_path}"}

    checker = GitSafetyChecker()
    report = checker.check_repo(root)

    if report.has_hooks:
        pass

    secrets = checker.scan_staged_diff_for_secrets(root)
    if secrets:
        return {
            "error": "Secret detected in staged diff — commit blocked",
            "blocked": True,
            "patterns": secrets,
        }

    diff_result = run_git("diff", "--cached", repo_path=root)
    diff_preview = diff_result.stdout
    if not diff_preview.strip():
        return {"error": "Nothing staged to commit"}

    if dry_run:
        return {
            "dry_run": True,
            "repo": root,
            "message": message,
            "diff_preview": diff_preview[:2000],
            "hooks_present": report.hook_names,
            "note": "--no-verify will be used (hooks bypassed)",
        }

    try:
        result = run_git("commit", "--no-verify", "-m", message, repo_path=root)
        if result.returncode != 0:
            return {"error": result.stderr.strip()}
        return {
            "committed": True,
            "repo": root,
            "message": message,
            "output": result.stdout.strip(),
            "hooks_bypassed": report.hook_names,
            "no_verify": True,
        }
    except Exception as e:
        return {"error": str(e)}
