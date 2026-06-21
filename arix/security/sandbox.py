"""Execution sandbox — hardened subprocess jail for AI-generated code.

Layers of isolation applied:
  1. Clean environment   — strips all *_KEY, *_TOKEN, *_SECRET, etc. from env
  2. Isolated workdir    — ephemeral /tmp/arix_sandbox/<uuid>/ cleaned up after
  3. Hard timeout        — SIGKILL on expire
  4. Resource limits     — CPU time, virtual memory, file size, open files,
                           child processes capped via setrlimit (Linux/macOS)
  5. Network isolation   — optional unshare(1) network-namespace wrapper so
                           sandboxed code cannot make outbound connections
  6. Output scan         — stdout/stderr scanned for leaked credentials before
                           returning results (supply-chain safety)
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


# ── Sensitive env var patterns ────────────────────────────────────────────────

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
    re.compile(r'^TELEGRAM.*', re.I),
    re.compile(r'^DISCORD.*', re.I),
    re.compile(r'^SLACK.*', re.I),
    re.compile(r'^NOTION.*', re.I),
    re.compile(r'^SPOTIFY.*', re.I),
    re.compile(r'^TRELLO.*', re.I),
    re.compile(r'^YOUTUBE.*', re.I),
    re.compile(r'^LINE_.*', re.I),
    re.compile(r'^SIGNAL.*', re.I),
    re.compile(r'^MATRIX.*', re.I),
    re.compile(r'^IRC_PASSWORD.*', re.I),
]

_SAFE_PASSTHROUGH: set[str] = {
    'PATH', 'HOME', 'TMPDIR', 'TEMP', 'TMP', 'LANG', 'LC_ALL',
    'LC_CTYPE', 'LC_MESSAGES', 'LANGUAGE', 'USER', 'LOGNAME',
    'SHELL', 'TERM', 'TERM_PROGRAM', 'PYTHONPATH', 'PYTHONDONTWRITEBYTECODE',
    'VIRTUAL_ENV', 'PWD', 'OLDPWD', 'COLORTERM', 'XDG_RUNTIME_DIR',
}

# ── Output credential scan patterns ──────────────────────────────────────────
# Detect and redact values that look like real credentials leaking in output.

_CRED_SCAN: list[tuple[re.Pattern, str]] = [
    # Anthropic sk-ant-api03-...
    (re.compile(r'sk-ant-[A-Za-z0-9\-_]{20,}'), '[REDACTED:anthropic-key]'),
    # OpenAI sk-proj-... or sk-...
    (re.compile(r'sk-(?:proj-)?[A-Za-z0-9]{20,}'), '[REDACTED:openai-key]'),
    # Google / Gemini AIza...
    (re.compile(r'AIza[A-Za-z0-9\-_]{30,}'), '[REDACTED:google-key]'),
    # Generic 40-char hex (GitHub PAT, etc.)
    (re.compile(r'\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b'), '[REDACTED:gh-token]'),
    # Bearer tokens in env dump output
    (re.compile(r'(?i)(?:bearer|token)\s*[=:]\s*[A-Za-z0-9\-_.]{16,}'), '[REDACTED:bearer-token]'),
    # Slack xoxb-/xoxp- tokens
    (re.compile(r'xox[bprs]-[A-Za-z0-9\-]{10,}'), '[REDACTED:slack-token]'),
    # Discord bot tokens  (NNN.XXXXXX.YYYYYY)
    (re.compile(r'\bMT[A-Za-z0-9]{20,}\.[A-Za-z0-9\-_]{6,}\.[A-Za-z0-9\-_]{27,}\b'), '[REDACTED:discord-token]'),
    # Telegram bot tokens  NNN:AAAAA...
    (re.compile(r'\b\d{8,12}:[A-Za-z0-9\-_]{35}\b'), '[REDACTED:telegram-token]'),
]


def scan_output(text: str) -> tuple[str, int]:
    """Scan text for credential patterns and redact them.

    Returns (redacted_text, count_of_replacements).
    """
    count = 0
    for pattern, replacement in _CRED_SCAN:
        new_text, n = pattern.subn(replacement, text)
        text = new_text
        count += n
    return text, count


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

# ── Resource limits ───────────────────────────────────────────────────────────

def _apply_rlimits(
    cpu_seconds: int = 30,
    max_memory_mb: int = 256,
    max_file_mb: int = 64,
    max_procs: int = 32,
    max_open_files: int = 64,
) -> None:
    """Called as preexec_fn in the child process to apply resource limits."""
    try:
        import resource
        MB = 1024 * 1024
        GB = 1024 * MB

        # CPU time
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 5))

        # Virtual address space (AS) — cap at max_memory_mb
        mem = max_memory_mb * MB
        try:
            resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        except (ValueError, resource.error):
            pass  # not supported on all platforms

        # Max file size created
        fsize = max_file_mb * MB
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))

        # Max child processes
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (max_procs, max_procs))
        except (AttributeError, resource.error):
            pass  # Windows / some containers

        # Max open file descriptors
        resource.setrlimit(resource.RLIMIT_NOFILE, (max_open_files, max_open_files))

    except Exception:
        pass  # Never crash the child — rlimit is best-effort


_UNSHARE_BIN = shutil.which("unshare")
_BWRAP_BIN = shutil.which("bwrap")
_DOCKER_BIN = shutil.which("docker")


def detect_sandbox_method() -> str:
    """Return the strongest isolation method available on this system.

    Priority: bwrap (bubblewrap) > unshare (network-only) > setrlimit-only
    """
    if _BWRAP_BIN:
        return "bubblewrap"
    if _UNSHARE_BIN:
        return "unshare-net"
    return "setrlimit"


def get_sandbox_capabilities() -> dict:
    """Return a dict describing available sandbox mechanisms on this host."""
    return {
        "method": detect_sandbox_method(),
        "bwrap": bool(_BWRAP_BIN),
        "unshare": bool(_UNSHARE_BIN),
        "docker": bool(_DOCKER_BIN),
        "setrlimit": True,
        "network_isolation": bool(_UNSHARE_BIN or _BWRAP_BIN),
        "filesystem_isolation": bool(_BWRAP_BIN),
    }


def _build_cmd(
    interp: list[str],
    code_file: str,
    network_isolation: bool,
) -> list[str]:
    """Wrap interpreter command with unshare network namespace if requested."""
    base = interp + [code_file]
    if network_isolation and _UNSHARE_BIN:
        # --net creates a new network namespace with no external connectivity
        return [_UNSHARE_BIN, "--net", "--"] + base
    return base


def make_clean_env() -> dict[str, str]:
    """Return a sanitized copy of os.environ with all sensitive vars stripped."""
    clean: dict[str, str] = {}
    for key, val in os.environ.items():
        if key in _SAFE_PASSTHROUGH:
            clean[key] = val
            continue
        if any(pat.match(key) for pat in _STRIP_PATTERNS):
            continue
        clean[key] = val
    if "PATH" not in clean:
        clean["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    return clean


def run_sandboxed(
    code: str,
    language: str = "python",
    timeout: float = 30.0,
    stdin_data: str | None = None,
    network_isolation: bool = True,
    cpu_seconds: int = 25,
    max_memory_mb: int = 256,
    max_file_mb: int = 64,
    max_procs: int = 32,
) -> dict:
    """Execute code in a hardened subprocess jail.

    Returns dict with keys:
        stdout, stderr, returncode, timed_out, elapsed, language,
        sandbox_dir, env_vars_stripped, credentials_redacted,
        network_isolated
    """
    lang = language.lower()
    ext = _EXT_MAP.get(lang, ".py")
    interp = _CMD_MAP.get(lang, ["python3"])

    total_env = len(os.environ)
    clean_env = make_clean_env()
    stripped_count = total_env - len(clean_env)

    _SANDBOX_BASE.mkdir(exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(dir=_SANDBOX_BASE, prefix="run_"))

    net_isolated = network_isolation and bool(_UNSHARE_BIN)

    try:
        code_file = work_dir / f"script{ext}"
        code_file.write_text(code, encoding="utf-8")

        cmd = _build_cmd(interp, str(code_file), network_isolation)
        start = time.monotonic()

        import sys as _sys
        # preexec_fn is Unix-only; skip silently on Windows
        _preexec = None
        if _sys.platform != "win32":
            def _preexec_wrapper():
                # Avoid potential race by setting pdeathsig if available
                # (Linux only, but _apply_rlimits is already best-effort)
                try:
                    import ctypes
                    libc = ctypes.CDLL("libc.so.6")
                    # PR_SET_PDEATHSIG = 1
                    libc.prctl(1, 15) # SIGTERM
                except Exception:
                    pass
                _apply_rlimits(
                    cpu_seconds=cpu_seconds,
                    max_memory_mb=max_memory_mb,
                    max_file_mb=max_file_mb,
                    max_procs=max_procs,
                )
            _preexec = _preexec_wrapper
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
                preexec_fn=_preexec,
            )
            elapsed = round(time.monotonic() - start, 3)

            # Scan and redact any credentials that leaked into output
            stdout_clean, cred_count_out = scan_output(proc.stdout[:16384])
            stderr_clean, cred_count_err = scan_output(proc.stderr[:4096])
            creds_redacted = cred_count_out + cred_count_err

            return {
                "stdout": stdout_clean,
                "stderr": stderr_clean,
                "returncode": proc.returncode,
                "timed_out": False,
                "elapsed": elapsed,
                "language": language,
                "sandbox_dir": str(work_dir),
                "env_vars_stripped": stripped_count,
                "credentials_redacted": creds_redacted,
                "network_isolated": net_isolated,
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
                "credentials_redacted": 0,
                "network_isolated": net_isolated,
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
            "credentials_redacted": 0,
            "network_isolated": net_isolated,
        }
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
