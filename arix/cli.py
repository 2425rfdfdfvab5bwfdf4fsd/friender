"""Arix command-line interface.

Usage:
    arix serve          Start the Arix web server (default)
    arix doctor         Run system health checks
    arix init           Interactive first-run setup wizard
    arix version        Print version and exit
"""
from __future__ import annotations
import os
import sys
import shutil
import subprocess
from pathlib import Path

VERSION = "8.0.0"
Arix_DIR = Path.home() / ".arix"


def _print(msg: str, *, ok: bool | None = None) -> None:
    if ok is True:
        prefix = "\033[32m✓\033[0m"
    elif ok is False:
        prefix = "\033[31m✗\033[0m"
    else:
        prefix = "\033[33m•\033[0m"
    print(f"  {prefix}  {msg}")


def cmd_version() -> None:
    print(f"Arix v{VERSION}")


def cmd_doctor() -> None:
    print(f"\nArix v{VERSION} — System Health Check")
    print("=" * 50)
    errors = 0

    # Python version
    major, minor = sys.version_info[:2]
    ok = major == 3 and minor >= 11
    _print(f"Python {major}.{minor}  (need 3.11+)", ok=ok)
    if not ok:
        errors += 1

    # Playwright
    try:
        import playwright  # noqa: F401
        _print("playwright installed", ok=True)
    except ImportError:
        _print("playwright not installed — browser tools disabled (pip install playwright)", ok=None)

    # Config file
    cfg_path = Arix_DIR / "config.json"
    if cfg_path.exists():
        mode = oct(os.stat(cfg_path).st_mode)[-3:]
        ok = mode == "600"
        _print(f"Config file {cfg_path}  (permissions: {mode})", ok=ok)
        if not ok:
            errors += 1
            _print("  → fix: chmod 600 ~/.arix/config.json", ok=None)
    else:
        _print(f"Config file not found — will be created on first run ({cfg_path})", ok=None)

    # Audit log
    audit_path = Arix_DIR / "audit.log"
    if audit_path.exists():
        mode = oct(os.stat(audit_path).st_mode)[-3:]
        ok = mode == "600"
        _print(f"Audit log {audit_path}  (permissions: {mode})", ok=ok)
        if not ok:
            errors += 1
    else:
        _print("Audit log not yet created (normal on first run)", ok=None)

    # Memory DB
    mem_db = Arix_DIR / "memory.db"
    if mem_db.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(mem_db))
            conn.execute("SELECT 1").fetchone()
            conn.close()
            _print(f"Memory DB {mem_db}  accessible", ok=True)
        except Exception as e:
            _print(f"Memory DB error: {e}", ok=False)
            errors += 1
    else:
        _print("Memory DB not yet created (normal on first run)", ok=None)

    # API keys
    has_key = False
    for env, label in [
        ("AI_INTEGRATIONS_ANTHROPIC_API_KEY", "Anthropic (Replit integration)"),
        ("ANTHROPIC_API_KEY", "Anthropic (manual)"),
        ("OPENAI_API_KEY", "OpenAI"),
        ("GEMINI_API_KEY", "Gemini"),
    ]:
        if os.environ.get(env):
            _print(f"LLM key: {label}", ok=True)
            has_key = True
            break
    if not has_key:
        _print("No LLM API key found — running in demo/heuristic mode", ok=None)

    # Arix_ADMIN_TOKEN
    if os.environ.get("Arix_ADMIN_TOKEN"):
        _print("Arix_ADMIN_TOKEN set — API authentication enabled", ok=True)
    else:
        _print("Arix_ADMIN_TOKEN not set — API is unauthenticated (fine for local use)", ok=None)

    # Allowed path prefixes
    try:
        from arix.config import ArixConfig
        cfg = ArixConfig.load()
        if cfg.allowed_path_prefixes:
            _print(f"Allowed paths: {', '.join(cfg.allowed_path_prefixes[:3])}{'…' if len(cfg.allowed_path_prefixes) > 3 else ''}", ok=True)
        else:
            _print("No allowed_path_prefixes configured — defaults to $HOME and CWD", ok=None)
    except Exception as e:
        _print(f"Could not load config: {e}", ok=False)

    print()
    if errors:
        print(f"  ⚠  {errors} issue(s) found. Fix them before deploying publicly.")
    else:
        print("  ✓  All checks passed.")
    print()


def cmd_init() -> None:
    print(f"\nArix v{VERSION} — First-Run Setup")
    print("=" * 50)
    Arix_DIR.mkdir(parents=True, exist_ok=True)

    from arix.config import ArixConfig, CONFIG_FILE
    cfg = ArixConfig.load()

    # LLM provider
    print("\n[1/4] LLM Provider")
    print("  1) Anthropic Claude (recommended)")
    print("  2) OpenAI GPT")
    print("  3) Offline / demo mode")
    choice = input("  Choice [1]: ").strip() or "1"
    if choice == "2":
        cfg.provider = "openai"
        cfg.model = "gpt-4o"
    elif choice == "3":
        cfg.offline_mode = True
    else:
        cfg.provider = "anthropic"

    # Allowed paths
    print("\n[2/4] Allowed Paths")
    home = str(Path.home())
    default_paths = [home, os.getcwd()]
    print(f"  Default: {', '.join(default_paths)}")
    extra = input("  Add extra paths (comma-separated, or ENTER to skip): ").strip()
    if extra:
        for p in extra.split(","):
            p = p.strip()
            if p and Path(p).is_dir():
                default_paths.append(p)
    cfg.allowed_path_prefixes = list(dict.fromkeys(default_paths))

    # Dry-run mode
    print("\n[3/4] Safety Defaults")
    dry = input("  Enable dry-run mode by default? (preview plans before execution) [Y/n]: ").strip().lower()
    cfg.dry_run_mode = dry not in ("n", "no")

    # Headless browser
    print("\n[4/4] Browser")
    headless = input("  Run browser in headless mode? [Y/n]: ").strip().lower()
    cfg.browser_headless = headless not in ("n", "no")

    cfg.save()
    print(f"\n  ✓  Config saved to {CONFIG_FILE}")
    print("     Run 'arix doctor' to verify your setup.")
    print("     Run 'arix serve' to start Arix.\n")


def cmd_serve(host: str = "0.0.0.0", port: int = 5000) -> None:
    import uvicorn
    uvicorn.run("main:app", host=host, port=port, reload=False)


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "serve"

    if cmd in ("version", "--version", "-v"):
        cmd_version()
    elif cmd == "doctor":
        cmd_doctor()
    elif cmd == "init":
        cmd_init()
    elif cmd == "serve":
        host = "0.0.0.0"
        port = 5000
        for i, a in enumerate(args[1:], 1):
            if a.startswith("--host="):
                host = a.split("=", 1)[1]
            elif a.startswith("--port="):
                port = int(a.split("=", 1)[1])
        cmd_serve(host=host, port=port)
    else:
        print(f"Unknown command: {cmd!r}")
        print("Usage: arix [serve|doctor|init|version]")
        sys.exit(1)


if __name__ == "__main__":
    main()
