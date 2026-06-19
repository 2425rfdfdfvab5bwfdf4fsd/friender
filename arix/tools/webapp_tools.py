"""Web App Automation Tools — browser-based control of popular web applications.

Provides structured, intent-driven automation for social, productivity, and
communication web apps without requiring a native desktop bridge.

All tools route through BrowserController (Playwright + stealth mode) so they
work with the same browser session as the rest of Arix's browser tools.
"""
from __future__ import annotations
import asyncio
from typing import Any, Coroutine

# ── Web app URL map ───────────────────────────────────────────────────────────
# Maps normalised app name → base URL for the web version.
WEB_APP_URLS: dict[str, str] = {
    # Social
    "whatsapp":      "https://web.whatsapp.com",
    "whatsappweb":   "https://web.whatsapp.com",
    "instagram":     "https://www.instagram.com",
    "tiktok":        "https://www.tiktok.com",
    "facebook":      "https://www.facebook.com",
    "twitter":       "https://twitter.com",
    "x":             "https://x.com",
    "linkedin":      "https://www.linkedin.com",
    "snapchat":      "https://web.snapchat.com",
    "telegram":      "https://web.telegram.org",
    "discord":       "https://discord.com/app",
    "reddit":        "https://www.reddit.com",
    "pinterest":     "https://www.pinterest.com",
    # Productivity / Mail
    "gmail":         "https://mail.google.com",
    "googledrive":   "https://drive.google.com",
    "googlesheets":  "https://sheets.google.com",
    "googledocs":    "https://docs.google.com",
    "googleslides":  "https://slides.google.com",
    "googlecalendar":"https://calendar.google.com",
    "googlemaps":    "https://maps.google.com",
    "outlook":       "https://outlook.live.com",
    "onedrive":      "https://onedrive.live.com",
    "notion":        "https://www.notion.so",
    "trello":        "https://trello.com",
    "asana":         "https://app.asana.com",
    "slack":         "https://app.slack.com",
    "zoom":          "https://zoom.us/wc",
    "teams":         "https://teams.microsoft.com",
    "microsoftteams":"https://teams.microsoft.com",
    # Dev / Tools
    "github":        "https://github.com",
    "gitlab":        "https://gitlab.com",
    "stackoverflow": "https://stackoverflow.com",
    "jira":          "https://www.atlassian.com/software/jira",
    "figma":         "https://www.figma.com",
    "canva":         "https://www.canva.com",
    "chatgpt":       "https://chat.openai.com",
    "gemini":        "https://gemini.google.com",
    "claude":        "https://claude.ai",
    # Media
    "youtube":       "https://www.youtube.com",
    "spotify":       "https://open.spotify.com",
    "netflix":       "https://www.netflix.com",
    "twitch":        "https://www.twitch.tv",
    "soundcloud":    "https://soundcloud.com",
    # Shopping
    "amazon":        "https://www.amazon.com",
    "ebay":          "https://www.ebay.com",
    "aliexpress":    "https://www.aliexpress.com",
    # Finance
    "paypal":        "https://www.paypal.com",
    "stripe":        "https://dashboard.stripe.com",
}

# ── Task → URL path mappings for common actions ───────────────────────────────
# app_name → {action → (path, description)}
WEB_APP_ACTION_PATHS: dict[str, dict[str, tuple[str, str]]] = {
    "linkedin": {
        "post":        ("/feed/", "Open LinkedIn feed to create a post"),
        "jobs":        ("/jobs/", "Open LinkedIn job search"),
        "network":     ("/mynetwork/", "Open LinkedIn network"),
        "messages":    ("/messaging/", "Open LinkedIn messages"),
        "profile":     ("/in/me/", "Open your LinkedIn profile"),
        "notifications":("/notifications/", "Open LinkedIn notifications"),
    },
    "instagram": {
        "home":        ("/", "Open Instagram home feed"),
        "explore":     ("/explore/", "Open Instagram explore"),
        "reels":       ("/reels/", "Open Instagram reels"),
        "messages":    ("/direct/inbox/", "Open Instagram DMs"),
        "notifications":("/accounts/activity/", "Open Instagram notifications"),
        "profile":     ("/accounts/edit/", "Open Instagram profile"),
    },
    "tiktok": {
        "home":        ("/", "Open TikTok home"),
        "following":   ("/following", "Open TikTok following feed"),
        "live":        ("/live", "Open TikTok live"),
        "messages":    ("/messages", "Open TikTok messages"),
        "upload":      ("/upload", "Open TikTok upload page"),
    },
    "youtube": {
        "home":        ("/", "Open YouTube home"),
        "subscriptions":("/feed/subscriptions", "Open YouTube subscriptions"),
        "history":     ("/feed/history", "Open YouTube watch history"),
        "liked":       ("/playlist?list=LL", "Open liked videos"),
        "studio":      ("https://studio.youtube.com", "Open YouTube Studio"),
        "upload":      ("https://studio.youtube.com/channel/UC/videos/upload", "Upload to YouTube"),
    },
    "gmail": {
        "inbox":       ("/mail/u/0/#inbox", "Open Gmail inbox"),
        "compose":     ("/mail/u/0/#compose", "Compose new email"),
        "sent":        ("/mail/u/0/#sent", "Open sent mail"),
        "drafts":      ("/mail/u/0/#drafts", "Open drafts"),
        "starred":     ("/mail/u/0/#starred", "Open starred emails"),
    },
    "github": {
        "repos":       ("/", "Open GitHub home / repos"),
        "notifications":("/notifications", "Open GitHub notifications"),
        "pulls":       ("/pulls", "Open pull requests"),
        "issues":      ("/issues", "Open issues"),
        "explore":     ("/explore", "Explore GitHub"),
    },
    "twitter": {
        "home":        ("/home", "Open Twitter/X home"),
        "notifications":("/notifications", "Open Twitter/X notifications"),
        "messages":    ("/messages", "Open Twitter/X DMs"),
        "explore":     ("/explore", "Open Twitter/X explore"),
        "compose":     ("/compose/tweet", "Compose a tweet"),
    },
    "x": {
        "home":        ("/home", "Open X home"),
        "notifications":("/notifications", "Open X notifications"),
        "messages":    ("/messages", "Open X DMs"),
        "compose":     ("/compose/tweet", "Compose a post"),
    },
}


def _normalize_app_name(name: str) -> str:
    return name.lower().replace(" ", "").replace("-", "").replace("_", "")


async def open_web_app(
    app_name: str,
    action: str = "home",
    search_query: str = "",
) -> dict:
    """Open any web app in the browser by name.

    Args:
        app_name: App name (e.g. "WhatsApp", "LinkedIn", "TikTok", "Gmail")
        action: Optional action / section to navigate to (e.g. "messages", "jobs", "compose")
        search_query: If provided, navigate to the search results for this query

    Returns a dict with url, app_name, action, and opened status.
    """
    from arix.tools.browser_tools import get_browser_controller  # lazy import
    norm = _normalize_app_name(app_name)

    # Resolve base URL
    base_url = WEB_APP_URLS.get(norm)
    if not base_url:
        # Try partial match
        for key, url in WEB_APP_URLS.items():
            if norm in key or key in norm:
                base_url = url
                norm = key
                break

    if not base_url:
        return {
            "error": (
                f"App '{app_name}' not in the web app directory. "
                "Try using browser_open_url with the full URL instead."
            ),
            "available_apps": sorted(WEB_APP_URLS.keys()),
        }

    # Resolve action path
    final_url = base_url.rstrip("/")
    action_desc = f"Open {app_name}"

    norm_action = action.lower().strip() if action else "home"
    action_map = WEB_APP_ACTION_PATHS.get(norm, {})

    if norm_action and norm_action != "home" and action_map:
        path_info = action_map.get(norm_action)
        if path_info:
            path, action_desc = path_info
            if path.startswith("http"):
                final_url = path
            else:
                final_url = base_url.rstrip("/") + path

    # Append search query if provided
    if search_query:
        search_encodings: dict[str, str] = {
            "linkedin":  f"/search/results/all/?keywords={search_query.replace(' ', '+')}",
            "instagram": f"/explore/search/keyword/?q={search_query.replace(' ', '+')}",
            "tiktok":    f"/search?q={search_query.replace(' ', '+')}",
            "youtube":   f"/results?search_query={search_query.replace(' ', '+')}",
            "twitter":   f"/search?q={search_query.replace(' ', '+')}",
            "x":         f"/search?q={search_query.replace(' ', '+')}",
            "reddit":    f"/search/?q={search_query.replace(' ', '+')}",
            "github":    f"/search?q={search_query.replace(' ', '+')}",
        }
        if norm in search_encodings:
            final_url = WEB_APP_URLS[norm].rstrip("/") + search_encodings[norm]
        else:
            final_url = f"{base_url}?q={search_query.replace(' ', '+')}"
        action_desc = f"Search {app_name} for '{search_query}'"

    ctrl = get_browser_controller()
    if not ctrl._page:
        await ctrl.start()
    result = await ctrl.navigate(final_url)
    if isinstance(result, dict) and result.get("error"):
        return result

    return {
        "opened": final_url,
        "app_name": app_name,
        "action": action or "home",
        "description": action_desc,
        "note": (
            "App opened in browser. If you need to interact with its elements "
            "(click buttons, fill forms, type text), use browser_click, "
            "browser_type_text, or desktop_find_and_click."
        ),
    }


async def navigate_web_app(
    app_name: str,
    task: str,
    params: dict | None = None,
) -> dict:
    """Navigate to a specific section of a web app and optionally perform a task.

    This is a higher-level wrapper that understands natural-language task descriptions.

    Args:
        app_name: The app to open (e.g. "LinkedIn", "Gmail", "TikTok")
        task: What to do (e.g. "send message", "search jobs", "compose email")
        params: Optional parameters like {"to": "John", "query": "python developer"}

    Returns open/navigation result.
    """
    params = params or {}
    task_low = task.lower().strip()
    norm = _normalize_app_name(app_name)

    # Infer action from task description
    action_map = WEB_APP_ACTION_PATHS.get(norm, {})
    matched_action = "home"
    for action_key in action_map:
        if action_key in task_low:
            matched_action = action_key
            break

    # Common cross-app action mapping
    if not matched_action or matched_action == "home":
        for kw, action in [
            ("message",    "messages"),
            ("dm",         "messages"),
            ("post",       "post"),
            ("job",        "jobs"),
            ("search",     "home"),
            ("compose",    "compose"),
            ("upload",     "upload"),
            ("notification","notifications"),
            ("inbox",      "inbox"),
            ("explore",    "explore"),
            ("profile",    "profile"),
        ]:
            if kw in task_low:
                matched_action = action
                break

    search_q = params.get("query", "") or params.get("search", "")

    return await open_web_app(app_name=app_name, action=matched_action, search_query=search_q)


def list_available_web_apps() -> dict:
    """Return all web apps Arix can navigate to."""
    by_category: dict[str, list[str]] = {
        "Social": ["whatsapp", "instagram", "tiktok", "facebook", "twitter", "linkedin",
                   "snapchat", "telegram", "discord", "reddit"],
        "Productivity": ["gmail", "googledrive", "googlesheets", "googledocs", "outlook",
                         "onedrive", "notion", "trello", "asana", "googlecalendar"],
        "Communication": ["slack", "zoom", "teams"],
        "Media": ["youtube", "spotify", "netflix", "twitch", "soundcloud"],
        "Development": ["github", "gitlab", "stackoverflow", "figma", "canva"],
        "AI Assistants": ["chatgpt", "gemini", "claude"],
        "Shopping": ["amazon", "ebay", "aliexpress"],
    }
    return {"apps": by_category, "total": len(WEB_APP_URLS)}
