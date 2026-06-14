"""Browser tools — browser_open_url, browser_web_search, browser_extract_page_text,
browser_download_file, browser_tab_management."""
from __future__ import annotations
import os
import re
import urllib.parse
from pathlib import Path
from typing import Any

PACCA_DOWNLOADS = Path.home() / ".pacca" / "downloads"

EXEC_EXTENSIONS = {
    ".exe", ".sh", ".bat", ".ps1", ".cmd", ".vbs",
    ".dmg", ".pkg", ".deb", ".rpm", ".msi",
}
ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".7z", ".rar", ".bz2"}
SAFE_EXTENSIONS = {
    ".pdf", ".txt", ".csv", ".json", ".xml", ".html",
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".mp4", ".mp3",
    ".docx", ".xlsx", ".pptx",
}

PRIVATE_IP_RE = re.compile(
    r'^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|0\.0\.0\.0)'
)
PAYMENT_URL_RE = re.compile(r'(stripe|paypal|braintree|square)\.com/(pay|checkout)', re.I)


def _check_url_safety(url: str) -> tuple[bool, str]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "file":
        return False, "file:// URLs are blocked"
    host = parsed.netloc.split(":")[0].lower()
    if PRIVATE_IP_RE.match(host):
        return False, f"Private/local URL blocked: {host}"
    if PAYMENT_URL_RE.search(url):
        return False, f"Payment URL blocked: {url}"
    return True, ""


class BrowserController:
    """Thin wrapper around Playwright for isolated browser control."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._browser = None
        self._page = None
        self._context = None
        self._playwright = None

    async def start(self) -> None:
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
            self._context = await self._browser.new_context(
                user_agent="PACCA/5.2 (automated; no-credentials)",
                java_script_enabled=True,
                accept_downloads=True,
                locale="en-US",
            )
            self._page = await self._context.new_page()
        except ImportError:
            raise RuntimeError(
                "Playwright not installed. Run: playwright install chromium"
            )

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def navigate(self, url: str) -> dict:
        safe, reason = _check_url_safety(url)
        if not safe:
            return {"error": reason, "blocked": True}
        if not self._page:
            return {"error": "Browser not started"}
        try:
            response = await self._page.goto(url, timeout=30000,
                                              wait_until="domcontentloaded")
            title = await self._page.title()
            return {
                "url": self._page.url,
                "title": title,
                "status": response.status if response else None,
            }
        except Exception as e:
            return {"error": str(e)}

    async def extract_text(self) -> dict:
        if not self._page:
            return {"error": "Browser not started"}
        try:
            text = await self._page.evaluate("""() => {
                const scripts = document.querySelectorAll('script, style, nav, footer, header');
                scripts.forEach(s => s.remove());
                return document.body ? document.body.innerText : '';
            }""")
            return {"text": text[:32768], "url": self._page.url,
                    "truncated": len(text) > 32768}
        except Exception as e:
            return {"error": str(e)}

    async def search_web(self, query: str, engine: str = "duckduckgo") -> dict:
        engines = {
            "duckduckgo": f"https://duckduckgo.com/?q={urllib.parse.quote(query)}",
            "bing": f"https://www.bing.com/search?q={urllib.parse.quote(query)}",
        }
        url = engines.get(engine, engines["duckduckgo"])
        nav_result = await self.navigate(url)
        if "error" in nav_result:
            return nav_result
        text_result = await self.extract_text()
        return {
            "query": query,
            "engine": engine,
            "url": nav_result.get("url"),
            "text": text_result.get("text", "")[:8000],
        }

    async def download_file(self, url: str) -> dict:
        safe, reason = _check_url_safety(url)
        if not safe:
            return {"error": reason, "blocked": True}

        parsed = urllib.parse.urlparse(url)
        ext = Path(parsed.path).suffix.lower()

        if ext in EXEC_EXTENSIONS:
            return {
                "requires_confirmation": True,
                "warning": f"Executable file type ({ext}) — requires YES to download",
                "url": url,
            }
        if ext in ARCHIVE_EXTENSIONS:
            return {
                "requires_confirmation": True,
                "warning": f"Archive file type ({ext}) — requires YES to download",
                "url": url,
            }

        if not self._page:
            return {"error": "Browser not started"}

        PACCA_DOWNLOADS.mkdir(parents=True, exist_ok=True)

        try:
            async with self._page.expect_download() as download_info:
                await self._page.goto(url)
            download = await download_info.value
            filename = download.suggested_filename or Path(parsed.path).name or "download"
            dest = PACCA_DOWNLOADS / filename
            await download.save_as(str(dest))
            return {
                "downloaded": str(dest),
                "filename": filename,
                "url": url,
            }
        except Exception as e:
            return {"error": str(e)}

    async def manage_tabs(self, action: str, url: str | None = None) -> dict:
        if not self._context:
            return {"error": "Browser not started"}
        try:
            if action == "new":
                page = await self._context.new_page()
                self._page = page
                if url:
                    await self.navigate(url)
                return {"action": "new_tab", "tab_count": len(self._context.pages)}
            elif action == "close":
                if self._page:
                    await self._page.close()
                    pages = self._context.pages
                    self._page = pages[-1] if pages else None
                return {"action": "close_tab", "remaining": len(self._context.pages)}
            elif action == "list":
                pages = self._context.pages
                return {"tabs": [{"url": p.url} for p in pages],
                        "count": len(pages)}
            else:
                return {"error": f"Unknown tab action: {action}"}
        except Exception as e:
            return {"error": str(e)}


_browser_controller: BrowserController | None = None


def get_browser_controller() -> BrowserController:
    global _browser_controller
    if _browser_controller is None:
        _browser_controller = BrowserController(headless=True)
    return _browser_controller


async def browser_open_url(url: str, dry_run: bool = False) -> dict:
    safe, reason = _check_url_safety(url)
    if not safe:
        return {"error": reason, "blocked": True}
    if dry_run:
        return {"dry_run": True, "would_navigate": url}
    controller = get_browser_controller()
    if not controller._page:
        await controller.start()
    return await controller.navigate(url)


async def browser_web_search(query: str, engine: str = "duckduckgo",
                              dry_run: bool = False) -> dict:
    if dry_run:
        return {"dry_run": True, "query": query}
    controller = get_browser_controller()
    if not controller._page:
        await controller.start()
    return await controller.search_web(query, engine)


async def browser_extract_page_text(dry_run: bool = False) -> dict:
    if dry_run:
        return {"dry_run": True, "action": "extract_page_text"}
    controller = get_browser_controller()
    if not controller._page:
        return {"error": "No browser page open. Navigate to a URL first."}
    return await controller.extract_text()


async def browser_download_file(url: str, dry_run: bool = False) -> dict:
    if dry_run:
        return {"dry_run": True, "would_download": url,
                "destination": str(PACCA_DOWNLOADS)}
    controller = get_browser_controller()
    if not controller._page:
        await controller.start()
    return await controller.download_file(url)


async def browser_tab_management(action: str, url: str | None = None,
                                  dry_run: bool = False) -> dict:
    if dry_run:
        return {"dry_run": True, "action": action}
    controller = get_browser_controller()
    if not controller._context:
        await controller.start()
    return await controller.manage_tabs(action, url)
