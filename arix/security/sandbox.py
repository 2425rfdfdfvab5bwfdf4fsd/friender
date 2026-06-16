"""Execution sandbox — clean-environment subprocess jail for AI-generated code.

Gap #1: Sandboxed code execution
- Strips all sensitive env vars (*_KEY, *_TOKEN, *_SECRET, *_PASSWORD, etc.)
- Isolated working directory in /tmp/arix_sandbox/<uuid>/
- Hard timeout with process kill
- Resource-limited (stdout/stderr capped)
"""
from __future__ import annotations
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


# ── Sensitive env var patterns to always strip ────────────────────────────────

_STRIP_PATTERNS: list[re.Pattern] = [
    re.compile(r'.*(API[_\-]?KEY|APIKEY).*', re.I),
    re.compile(r'.*SECRET.*', re.I),
    re.compile(r'.*TOKEN.*', re.I),
    re.compile(r'.*(PASSWORD|PASSWD|PASS)$', re.I),
    re.compile(r'.*CREDENTIAL.*', re.I),
    re.compile(r'.*PRIVATE[_\-]?KEY.*', re.I),
    re.compile(r'^AWS_.*', re.I),
    re.compile(r'^GOOGLE_.*KEY.*', re.I),
    re.compile(r'.*(DATABASE|DB_URL|MONGO|REDIS|POSTGRES|MYSQL).*', re.I),
    re.compile(r'^ANTHROPIC.*', re.I),
    re.compile(r'^OPENAI.*', re.I),
    re.compile(r'^GEMINI.*', re.I),
    re.compile(r'^AI_INTEGRATIONS.*', re.I),
    re.compile(r'^WHATSAPP.*', re.I),
    re.compile(r'^REPLIT.*', re.I),
    re.compile(r'^REPL_.*', re.I),
    re.compile(r'^SESSION.*', re.I),
]

# Env vars that are safe to pass through
_SAFE_PASSTHROUGH: set[str] = {
    'PATH', 'HOME', 'TMPDIR', 'TEMP', 'TMP', 'LANG', 'LC_ALL',
    'LC_CTYPE', 'LC_MESSAGES', 'LANGUAGE', 'USER', 'LOGNAME',
    'SHELL', 'TERM', 'TERM_PROGRAM', 'PYTHONPATH', 'PYTHONDONTWRITEBYTECODE',
    'VIRTUAL_ENV', 'PWD', 'OLDPWD', 'COLORTERM', 'XDG_RUNTIME_DIR',
}

_SANDBOX_BASE = Path(tempfile.gettempdir()) / "arix_sandbox"

_CMD_MAP: dict[str, list[str]] = {
    "python": ["python3"],
    "python3": ["python3"],
    "javascript": ["node"],
    "js": ["node"],
    "bash": ["bash"],
    "shell": ["bash"],
    "sh": ["bash"],
    "ruby": ["ruby"],
}

_EXT_MAP: dict[str, str] = {
    "python": ".py", "python3": ".py",
    "javascript": ".js", "js": ".js",
    "bash": ".sh", "shell": ".sh", "sh": ".sh",
    "ruby": ".rb",
}


def make_clean_env() -> dict[str, str]:
    """Return a sanitized copy of os.environ with all sensitive vars stripped."""
    clean: dict[str, str] = {}
    for key, val in os.environ.items():
        if key in _SAFE_PASSTHROUGH:
            clean[key] = val
            continue
        if any(pat.match(key) for pat in _STRIP_PATTERNS):
            continue
        # Pass through anything else that looks non-sensitive
        clean[key] = val

    if "PATH" not in clean:
        clean["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    return clean


def run_sandboxed(
    code: str,
    language: str = "python",
    timeout: float = 30.0,
    stdin_data: str | None = None,
) -> dict:
    """Execute code in an isolated subprocess with a clean environment.

    Returns:
        dict with keys: stdout, stderr, returncode, timed_out, elapsed,
                        language, sandbox_dir, env_vars_stripped
    """
    lang = language.lower()
    ext = _EXT_MAP.get(lang, ".py")
    interp = _CMD_MAP.get(lang, ["python3"])

    # Count stripped vars for transparency
    total_env = len(os.environ)
    clean_env = make_clean_env()
    stripped_count = total_env - len(clean_env)

    _SANDBOX_BASE.mkdir(exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(dir=_SANDBOX_BASE, prefix="run_"))

    try:
        code_file = work_dir / f"script{ext}"
        code_file.write_text(code, encoding="utf-8")

        cmd = interp + [str(code_file)]
        start = time.monotonic()

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(work_dir),
                env=clean_env,
                stdin=subprocess.DEVNULL if stdin_data is None else None,
                input=stdin_data,
            )
            elapsed = round(time.monotonic() - start, 3)
            return {
                "stdout": proc.stdout[:16384],
                "stderr": proc.stderr[:4096],
                "returncode": proc.returncode,
                "timed_out": False,
                "elapsed": elapsed,
                "language": language,
                "sandbox_dir": str(work_dir),
                "env_vars_stripped": stripped_count,
            }
        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": f"Execution timed out after {timeout:.0f}s — process killed",
                "returncode": -1,
                "timed_out": True,
                "elapsed": timeout,
                "language": language,
                "sandbox_dir": str(work_dir),
                "env_vars_stripped": stripped_count,
            }

    except Exception as exc:
        return {
            "stdout": "",
            "stderr": str(exc),
            "returncode": -1,
            "timed_out": False,
            "error": str(exc),
            "language": language,
            "env_vars_stripped": stripped_count,
        }
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
