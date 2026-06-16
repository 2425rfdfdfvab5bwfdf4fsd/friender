"""App tools — open_known_app, close_app, list_running_apps, find_installed_app."""
from __future__ import annotations
import os
import platform
import subprocess
import sys
from pathlib import Path

import psutil

KNOWN_APP_DIRECTORIES: dict[str, list[str]] = {
    "darwin": ["/Applications/", str(Path.home() / "Applications") + "/",
               "/System/Applications/", "/System/Applications/Utilities/"],
    "win32": [
        r"C:\Program Files\\",
        r"C:\Program Files (x86)\\",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\\"),
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\\"),
    ],
    "linux": ["/usr/bin/", "/usr/local/bin/", "/opt/",
              str(Path.home() / ".local/bin") + "/",
              "/snap/bin/", "/usr/games/"],
}

# Comprehensive app name → executable path mapping per platform.
# Keys are lowercase, no-spaces normalised names.
COMMON_APP_NAMES: dict[str, dict[str, str]] = {
    "darwin": {
        # Browsers
        "chrome":           "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "googlechrome":     "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "firefox":          "/Applications/Firefox.app/Contents/MacOS/firefox",
        "safari":           "/Applications/Safari.app/Contents/MacOS/Safari",
        "brave":            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "edge":             "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "opera":            "/Applications/Opera.app/Contents/MacOS/Opera",
        # Productivity / Office
        "excel":            "/Applications/Microsoft Excel.app/Contents/MacOS/Microsoft Excel",
        "microsoftexcel":   "/Applications/Microsoft Excel.app/Contents/MacOS/Microsoft Excel",
        "word":             "/Applications/Microsoft Word.app/Contents/MacOS/Microsoft Word",
        "microsoftword":    "/Applications/Microsoft Word.app/Contents/MacOS/Microsoft Word",
        "powerpoint":       "/Applications/Microsoft PowerPoint.app/Contents/MacOS/Microsoft PowerPoint",
        "outlook":          "/Applications/Microsoft Outlook.app/Contents/MacOS/Microsoft Outlook",
        "onenote":          "/Applications/Microsoft OneNote.app/Contents/MacOS/Microsoft OneNote",
        "teams":            "/Applications/Microsoft Teams.app/Contents/MacOS/Teams",
        "microsoftteams":   "/Applications/Microsoft Teams.app/Contents/MacOS/Teams",
        "numbers":          "/Applications/Numbers.app/Contents/MacOS/Numbers",
        "pages":            "/Applications/Pages.app/Contents/MacOS/Pages",
        "keynote":          "/Applications/Keynote.app/Contents/MacOS/Keynote",
        # Dev tools
        "vscode":           "/Applications/Visual Studio Code.app/Contents/MacOS/Electron",
        "visualstudiocode": "/Applications/Visual Studio Code.app/Contents/MacOS/Electron",
        "pycharm":          "/Applications/PyCharm.app/Contents/MacOS/pycharm",
        "intellij":         "/Applications/IntelliJ IDEA.app/Contents/MacOS/idea",
        "xcode":            "/Applications/Xcode.app/Contents/MacOS/Xcode",
        "terminal":         "/System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal",
        "iterm":            "/Applications/iTerm.app/Contents/MacOS/iTerm2",
        "iterm2":           "/Applications/iTerm.app/Contents/MacOS/iTerm2",
        "postman":          "/Applications/Postman.app/Contents/MacOS/Postman",
        "githubdesktop":    "/Applications/GitHub Desktop.app/Contents/MacOS/GitHub Desktop",
        # Communication
        "slack":            "/Applications/Slack.app/Contents/MacOS/Slack",
        "zoom":             "/Applications/zoom.us.app/Contents/MacOS/zoom.us",
        "discord":          "/Applications/Discord.app/Contents/MacOS/Discord",
        "telegram":         "/Applications/Telegram.app/Contents/MacOS/Telegram",
        "whatsapp":         "/Applications/WhatsApp.app/Contents/MacOS/WhatsApp",
        "skype":            "/Applications/Skype.app/Contents/MacOS/Skype",
        "signal":           "/Applications/Signal.app/Contents/MacOS/Signal",
        "facetime":         "/System/Applications/FaceTime.app/Contents/MacOS/FaceTime",
        "messages":         "/System/Applications/Messages.app/Contents/MacOS/Messages",
        # Media / Creative
        "obs":              "/Applications/OBS.app/Contents/MacOS/OBS",
        "obsstudio":        "/Applications/OBS.app/Contents/MacOS/OBS",
        "spotify":          "/Applications/Spotify.app/Contents/MacOS/Spotify",
        "vlc":              "/Applications/VLC.app/Contents/MacOS/VLC",
        "itunes":           "/System/Applications/Music.app/Contents/MacOS/Music",
        "music":            "/System/Applications/Music.app/Contents/MacOS/Music",
        "quicktime":        "/System/Applications/QuickTime Player.app/Contents/MacOS/QuickTime Player",
        "photoshop":        "/Applications/Adobe Photoshop 2025/Adobe Photoshop 2025.app/Contents/MacOS/Adobe Photoshop 2025",
        "lightroom":        "/Applications/Adobe Lightroom Classic/Adobe Lightroom Classic.app/Contents/MacOS/lightroom",
        "premiere":         "/Applications/Adobe Premiere Pro 2025/Adobe Premiere Pro 2025.app/Contents/MacOS/Adobe Premiere Pro 2025",
        "finalcut":         "/Applications/Final Cut Pro.app/Contents/MacOS/Final Cut Pro",
        "audacity":         "/Applications/Audacity.app/Contents/MacOS/Audacity",
        "figma":            "/Applications/Figma.app/Contents/MacOS/Figma",
        "sketch":           "/Applications/Sketch.app/Contents/MacOS/Sketch",
        # Utilities
        "finder":           "/System/Library/CoreServices/Finder.app/Contents/MacOS/Finder",
        "calculator":       "/System/Applications/Calculator.app/Contents/MacOS/Calculator",
        "notes":            "/System/Applications/Notes.app/Contents/MacOS/Notes",
        "textedit":         "/System/Applications/TextEdit.app/Contents/MacOS/TextEdit",
        "preview":          "/System/Applications/Preview.app/Contents/MacOS/Preview",
        "activitymonitor":  "/System/Applications/Utilities/Activity Monitor.app/Contents/MacOS/Activity Monitor",
        "systempreferences":"/System/Applications/System Preferences.app/Contents/MacOS/System Preferences",
        "systemsettings":   "/System/Applications/System Settings.app/Contents/MacOS/System Settings",
        "appstore":         "/System/Applications/App Store.app/Contents/MacOS/App Store",
        "docker":           "/Applications/Docker.app/Contents/MacOS/Docker",
    },
    "linux": {
        # Browsers
        "chrome":           "/usr/bin/google-chrome",
        "googlechrome":     "/usr/bin/google-chrome",
        "chromium":         "/usr/bin/chromium-browser",
        "firefox":          "/usr/bin/firefox",
        "brave":            "/usr/bin/brave-browser",
        "edge":             "/usr/bin/microsoft-edge",
        "opera":            "/usr/bin/opera",
        # Dev
        "vscode":           "/usr/bin/code",
        "visualstudiocode": "/usr/bin/code",
        "terminal":         "/usr/bin/gnome-terminal",
        "konsole":          "/usr/bin/konsole",
        "pycharm":          "/opt/pycharm/bin/pycharm.sh",
        "intellij":         "/opt/idea/bin/idea.sh",
        # Office
        "libreoffice":      "/usr/bin/libreoffice",
        "libreofficewriter":"/usr/bin/lowriter",
        "libreofficeimpress":"/usr/bin/loimpress",
        "libreofficecalc":  "/usr/bin/localc",
        "excel":            "/usr/bin/libreoffice",  # best effort on Linux
        # Communication
        "slack":            "/usr/bin/slack",
        "zoom":             "/usr/bin/zoom",
        "discord":          "/usr/bin/discord",
        "telegram":         "/usr/bin/telegram-desktop",
        "skype":            "/usr/bin/skype",
        "signal":           "/usr/bin/signal-desktop",
        # Media
        "obs":              "/usr/bin/obs",
        "obsstudio":        "/usr/bin/obs",
        "vlc":              "/usr/bin/vlc",
        "spotify":          "/usr/bin/spotify",
        "audacity":         "/usr/bin/audacity",
        "gimp":             "/usr/bin/gimp",
        "inkscape":         "/usr/bin/inkscape",
        # Utilities
        "calculator":       "/usr/bin/gnome-calculator",
        "nautilus":         "/usr/bin/nautilus",
        "gedit":            "/usr/bin/gedit",
        "files":            "/usr/bin/nautilus",
        "docker":           "/usr/bin/docker",
        "postman":          "/opt/Postman/Postman",
    },
    "win32": {
        # Browsers
        "chrome":           r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "googlechrome":     r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "firefox":          r"C:\Program Files\Mozilla Firefox\firefox.exe",
        "edge":             r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "microsoftedge":    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "brave":            os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        "opera":            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\opera.exe"),
        # Microsoft Office
        "excel":            os.path.expandvars(r"%PROGRAMFILES%\Microsoft Office\root\Office16\EXCEL.EXE"),
        "microsoftexcel":   os.path.expandvars(r"%PROGRAMFILES%\Microsoft Office\root\Office16\EXCEL.EXE"),
        "word":             os.path.expandvars(r"%PROGRAMFILES%\Microsoft Office\root\Office16\WINWORD.EXE"),
        "microsoftword":    os.path.expandvars(r"%PROGRAMFILES%\Microsoft Office\root\Office16\WINWORD.EXE"),
        "powerpoint":       os.path.expandvars(r"%PROGRAMFILES%\Microsoft Office\root\Office16\POWERPNT.EXE"),
        "outlook":          os.path.expandvars(r"%PROGRAMFILES%\Microsoft Office\root\Office16\OUTLOOK.EXE"),
        "onenote":          os.path.expandvars(r"%PROGRAMFILES%\Microsoft Office\root\Office16\ONENOTE.EXE"),
        "teams":            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Teams\Update.exe"),
        "microsoftteams":   os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Teams\Update.exe"),
        # Dev
        "vscode":           os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
        "visualstudiocode": os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
        "notepad":          r"C:\Windows\System32\notepad.exe",
        "notepadplusplus":  os.path.expandvars(r"%PROGRAMFILES%\Notepad++\notepad++.exe"),
        "pycharm":          os.path.expandvars(r"%LOCALAPPDATA%\Programs\PyCharm Community Edition\bin\pycharm64.exe"),
        "terminal":         r"C:\Windows\System32\cmd.exe",
        "cmd":              r"C:\Windows\System32\cmd.exe",
        "powershell":       r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        "windowsterminal":  os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe"),
        "postman":          os.path.expandvars(r"%LOCALAPPDATA%\Postman\Postman.exe"),
        "githubdesktop":    os.path.expandvars(r"%LOCALAPPDATA%\GitHubDesktop\GitHubDesktop.exe"),
        # Communication
        "discord":          os.path.expandvars(r"%LOCALAPPDATA%\Discord\Update.exe"),
        "slack":            os.path.expandvars(r"%LOCALAPPDATA%\slack\slack.exe"),
        "zoom":             os.path.expandvars(r"%LOCALAPPDATA%\Zoom\bin\Zoom.exe"),
        "skype":            os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Skype\Skype.exe"),
        "telegram":         os.path.expandvars(r"%APPDATA%\Telegram Desktop\Telegram.exe"),
        "whatsapp":         os.path.expandvars(r"%LOCALAPPDATA%\WhatsApp\WhatsApp.exe"),
        "signal":           os.path.expandvars(r"%LOCALAPPDATA%\Programs\signal-desktop\Signal.exe"),
        # Media / Creative
        "obs":              r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
        "obsstudio":        r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
        "vlc":              r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        "spotify":          os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe"),
        "audacity":         r"C:\Program Files\Audacity\audacity.exe",
        "winamp":           r"C:\Program Files\Winamp\winamp.exe",
        "handbrake":        r"C:\Program Files\HandBrake\HandBrake.exe",
        "davinciresolve":   r"C:\Program Files\Blackmagic Design\DaVinci Resolve\Resolve.exe",
        # Adobe (common install paths)
        "photoshop":        r"C:\Program Files\Adobe\Adobe Photoshop 2025\Photoshop.exe",
        "premiere":         r"C:\Program Files\Adobe\Adobe Premiere Pro 2025\Adobe Premiere Pro.exe",
        "aftereffects":     r"C:\Program Files\Adobe\Adobe After Effects 2025\AfterFX.exe",
        "illustrator":      r"C:\Program Files\Adobe\Adobe Illustrator 2025\Support Files\Contents\Windows\Illustrator.exe",
        "lightroom":        r"C:\Program Files\Adobe\Adobe Lightroom Classic\lightroom.exe",
        "acrobat":          r"C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe",
        # Gaming
        "steam":            r"C:\Program Files (x86)\Steam\steam.exe",
        "epicgames":        os.path.expandvars(r"%LOCALAPPDATA%\EpicGamesLauncher\Portal\Binaries\Win64\EpicGamesLauncher.exe"),
        # Utilities
        "calculator":       r"C:\Windows\System32\calc.exe",
        "explorer":         r"C:\Windows\explorer.exe",
        "taskmanager":      r"C:\Windows\System32\taskmgr.exe",
        "paint":            r"C:\Windows\System32\mspaint.exe",
        "paint3d":          os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\PaintStudio3D.exe"),
        "snip":             r"C:\Windows\System32\SnippingTool.exe",
        "7zip":             r"C:\Program Files\7-Zip\7z.exe",
        "winrar":           r"C:\Program Files\WinRAR\WinRAR.exe",
        "winzip":           r"C:\Program Files\WinZip\winzip64.exe",
        "docker":           os.path.expandvars(r"%PROGRAMFILES%\Docker\Docker\Docker Desktop.exe"),
        "filezilla":        r"C:\Program Files\FileZilla FTP Client\filezilla.exe",
        "putty":            r"C:\Program Files\PuTTY\putty.exe",
        "wireshark":        r"C:\Program Files\Wireshark\Wireshark.exe",
        "virtualbox":       r"C:\Program Files\Oracle\VirtualBox\VirtualBox.exe",
        "notepad":          r"C:\Windows\System32\notepad.exe",
    },
}

# Web fallbacks: when a desktop app isn't found, open this URL instead
WEB_FALLBACKS: dict[str, str] = {
    "tiktok":       "https://www.tiktok.com",
    "instagram":    "https://www.instagram.com",
    "facebook":     "https://www.facebook.com",
    "twitter":      "https://x.com",
    "x":            "https://x.com",
    "linkedin":     "https://www.linkedin.com",
    "snapchat":     "https://web.snapchat.com",
    "reddit":       "https://www.reddit.com",
    "gmail":        "https://mail.google.com",
    "googledrive":  "https://drive.google.com",
    "googlesheets": "https://sheets.google.com",
    "googledocs":   "https://docs.google.com",
    "outlook":      "https://outlook.live.com",
    "slack":        "https://app.slack.com",
    "zoom":         "https://zoom.us/wc",
    "discord":      "https://discord.com/app",
    "telegram":     "https://web.telegram.org",
    "whatsapp":     "https://web.whatsapp.com",
    "spotify":      "https://open.spotify.com",
    "youtube":      "https://www.youtube.com",
    "netflix":      "https://www.netflix.com",
    "github":       "https://github.com",
    "notion":       "https://www.notion.so",
    "figma":        "https://www.figma.com",
    "canva":        "https://www.canva.com",
    "chatgpt":      "https://chat.openai.com",
    "gemini":       "https://gemini.google.com",
    "claude":       "https://claude.ai",
    "amazon":       "https://www.amazon.com",
    "trello":       "https://trello.com",
    "asana":        "https://app.asana.com",
}


def _platform_key() -> str:
    s = sys.platform
    if s == "darwin":
        return "darwin"
    if s == "win32":
        return "win32"
    return "linux"


def _normalize(name: str) -> str:
    return name.lower().replace(" ", "").replace("-", "").replace("_", "")


def _resolve_app_name(name: str) -> tuple[str | None, str | None]:
    """Return (executable_path, error_message)."""
    pk = _platform_key()
    norm = _normalize(name)
    known = COMMON_APP_NAMES.get(pk, {})

    # Exact / substring match in hardcoded list
    for key, path in known.items():
        if norm == key or norm in key or key in norm:
            if os.path.exists(path):
                return path, None

    # Scan known app directories for a matching executable / bundle
    dirs = KNOWN_APP_DIRECTORIES.get(pk, [])
    for d in dirs:
        expanded = os.path.expandvars(d)
        if not os.path.isdir(expanded):
            continue
        try:
            for item in os.listdir(expanded):
                if name.lower() in item.lower():
                    candidate = os.path.join(expanded, item)
                    # Accept .app bundles (macOS) or executable files
                    if pk == "darwin" and candidate.endswith(".app"):
                        return candidate, None
                    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                        return candidate, None
        except PermissionError:
            continue

    # Try the system PATH
    try:
        import shutil as _shutil
        which = _shutil.which(norm) or _shutil.which(name.lower())
        if which:
            return which, None
    except Exception:
        pass

    return None, f"Application '{name}' not found on this system"


def _open_executable(path: str, name: str) -> dict:
    """Launch an app from an executable or .app bundle path."""
    pk = _platform_key()
    try:
        if pk == "darwin":
            # Walk up to find the .app bundle
            app_bundle = path
            while not app_bundle.endswith(".app") and app_bundle != "/":
                app_bundle = os.path.dirname(app_bundle)
            if app_bundle.endswith(".app"):
                subprocess.Popen(["open", app_bundle])
            else:
                subprocess.Popen([path])
        elif pk == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen([path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"opened": path, "app_name": name, "method": "executable"}
    except Exception as e:
        return {"error": str(e)}


def open_known_app(name: str, dry_run: bool = False) -> dict:
    """Open any installed application by name.

    If the desktop app is not found, automatically falls back to opening the
    web version in the default browser (for social/web apps).

    Args:
        name: Natural-language app name (e.g. "OBS Studio", "WhatsApp", "Excel")
        dry_run: If True, report what would be opened without actually opening it.
    """
    path, error = _resolve_app_name(name)
    norm = _normalize(name)

    # If not found locally, try the web fallback
    if error or not path:
        web_url = WEB_FALLBACKS.get(norm)
        if not web_url:
            # Try partial key match
            for key, url in WEB_FALLBACKS.items():
                if norm in key or key in norm:
                    web_url = url
                    break

        if web_url:
            if dry_run:
                return {
                    "dry_run": True,
                    "app_name": name,
                    "method": "web_fallback",
                    "would_open": web_url,
                    "note": f"Desktop app not found — would open web version at {web_url}",
                }
            # Open web version via browser tool
            try:
                from arix.tools.browser_tools import BrowserController
                import asyncio as _asyncio
                ctrl = BrowserController()
                result = _asyncio.run(ctrl.navigate(web_url))
                return {
                    "opened": web_url,
                    "app_name": name,
                    "method": "web_fallback",
                    "note": f"Desktop app not installed — opened web version instead ({web_url})",
                }
            except Exception as e:
                return {"error": f"Desktop not found and web fallback failed: {e}"}

        return {"error": error or f"App '{name}' not found and no web version available"}

    if dry_run:
        return {"dry_run": True, "would_open": path, "app_name": name}

    return _open_executable(path, name)


def find_installed_apps(query: str = "", limit: int = 20) -> dict:
    """Search for installed applications by name.

    Args:
        query: Optional search term to filter results.
        limit: Maximum number of results to return.

    Returns a list of found app names and paths.
    """
    pk = _platform_key()
    dirs = KNOWN_APP_DIRECTORIES.get(pk, [])
    found = []
    seen: set[str] = set()

    # Check hardcoded list first
    known = COMMON_APP_NAMES.get(pk, {})
    for key, path in known.items():
        if os.path.exists(path):
            if not query or query.lower() in key:
                if key not in seen:
                    seen.add(key)
                    found.append({"name": key, "path": path, "source": "known"})

    # Scan app directories
    for d in dirs:
        expanded = os.path.expandvars(d)
        if not os.path.isdir(expanded):
            continue
        try:
            for item in sorted(os.listdir(expanded)):
                candidate = os.path.join(expanded, item)
                item_norm = _normalize(item.replace(".app", "").replace(".exe", ""))
                if item_norm in seen:
                    continue
                is_app = (pk == "darwin" and item.endswith(".app")) or (
                    pk != "darwin" and os.path.isfile(candidate) and os.access(candidate, os.X_OK)
                )
                if not is_app:
                    continue
                display = item.replace(".app", "").replace(".exe", "")
                if not query or query.lower() in display.lower():
                    seen.add(item_norm)
                    found.append({"name": display, "path": candidate, "source": "scan"})
        except PermissionError:
            continue

    return {"apps": found[:limit], "total": len(found), "platform": pk}


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
