"""App tools — open_known_app, close_app, list_running_apps."""
from __future__ import annotations
import os
import platform
import subprocess
import sys
from pathlib import Path

import psutil

KNOWN_APP_DIRECTORIES: dict[str, list[str]] = {
    "darwin": ["/Applications/", str(Path.home() / "Applications") + "/",
               "/System/Applications/"],
    "win32": [
        r"C:\Program Files\\",
        r"C:\Program Files (x86)\\",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\\"),
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\\"),
    ],
    "linux": ["/usr/bin/", "/usr/local/bin/", "/opt/", str(Path.home() / ".local/bin") + "/"],
}

COMMON_APP_NAMES: dict[str, dict[str, str]] = {
    "darwin": {
        "chrome": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "firefox": "/Applications/Firefox.app/Contents/MacOS/firefox",
        "safari": "/Applications/Safari.app/Contents/MacOS/Safari",
        "vscode": "/Applications/Visual Studio Code.app/Contents/MacOS/Electron",
        "terminal": "/System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal",
        "calculator": "/System/Applications/Calculator.app/Contents/MacOS/Calculator",
        "finder": "/System/Library/CoreServices/Finder.app/Contents/MacOS/Finder",
        "notes": "/System/Applications/Notes.app/Contents/MacOS/Notes",
        "textedit": "/System/Applications/TextEdit.app/Contents/MacOS/TextEdit",
    },
    "linux": {
        "chrome": "/usr/bin/google-chrome",
        "chromium": "/usr/bin/chromium-browser",
        "firefox": "/usr/bin/firefox",
        "gedit": "/usr/bin/gedit",
        "nautilus": "/usr/bin/nautilus",
        "calculator": "/usr/bin/gnome-calculator",
        "terminal": "/usr/bin/gnome-terminal",
    },
    "win32": {
        "notepad": r"C:\Windows\System32\notepad.exe",
        "calculator": r"C:\Windows\System32\calc.exe",
        "explorer": r"C:\Windows\explorer.exe",
        "cmd": r"C:\Windows\System32\cmd.exe",
        "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    },
}


def _platform_key() -> str:
    s = sys.platform
    if s == "darwin":
        return "darwin"
    if s == "win32":
        return "win32"
    return "linux"


def _resolve_app_name(name: str) -> tuple[str | None, str | None]:
    pk = _platform_key()
    lower = name.lower().replace(" ", "").replace("-", "")
    known = COMMON_APP_NAMES.get(pk, {})
    for key, path in known.items():
        if lower in key or key in lower:
            if os.path.exists(path):
                return path, None
    dirs = KNOWN_APP_DIRECTORIES.get(pk, [])
    for d in dirs:
        expanded = os.path.expandvars(d)
        if os.path.isdir(expanded):
            for item in os.listdir(expanded):
                if name.lower() in item.lower():
                    candidate = os.path.join(expanded, item)
                    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                        return candidate, None
    return None, f"Application '{name}' not found in known app directories"


def open_known_app(name: str, dry_run: bool = False) -> dict:
    path, error = _resolve_app_name(name)
    if error:
        return {"error": error, "blocked": True}
    if dry_run:
        return {"dry_run": True, "would_open": path, "app_name": name}
    try:
        pk = _platform_key()
        if pk == "darwin":
            app_bundle = path
            while not app_bundle.endswith(".app") and app_bundle != "/":
                app_bundle = os.path.dirname(app_bundle)
            if app_bundle.endswith(".app"):
                subprocess.Popen(["open", app_bundle])
            else:
                subprocess.Popen([path])
        elif pk == "win32":
            os.startfile(path)
        else:
            subprocess.Popen([path])
        return {"opened": path, "app_name": name}
    except Exception as e:
        return {"error": str(e)}


def close_app(name: str, dry_run: bool = False) -> dict:
    matches = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if name.lower() in proc.info["name"].lower():
                matches.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if not matches:
        return {"error": f"No running process found matching '{name}'"}
    if dry_run:
        return {"dry_run": True, "would_close": [p.info["name"] for p in matches]}
    results = []
    errors = []
    for proc in matches:
        try:
            proc.terminate()
            results.append({"pid": proc.pid, "name": proc.info["name"]})
        except Exception as e:
            errors.append(str(e))
    return {"closed": results, "errors": errors}


def list_running_apps() -> dict:
    apps = []
    seen_names: set[str] = set()
    for proc in psutil.process_iter(["pid", "name", "status", "cpu_percent", "memory_info"]):
        try:
            name = proc.info["name"]
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            mem_mb = (proc.info["memory_info"].rss / 1024 / 1024
                      if proc.info["memory_info"] else 0)
            apps.append({
                "pid": proc.info["pid"],
                "name": name,
                "status": proc.info["status"],
                "memory_mb": round(mem_mb, 1),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    apps.sort(key=lambda x: x["name"].lower())
    return {"apps": apps, "count": len(apps)}
