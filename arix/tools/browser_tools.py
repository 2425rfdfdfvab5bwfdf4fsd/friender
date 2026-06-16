"""Browser tools — Playwright-powered automation with:
- Gap #4: Vision-grounded coord-click fallback when CSS selector fails
- Gap #11: Stealth mode — randomized typing delays, pre-click jitter, realistic UA rotation
"""
from __future__ import annotations
import asyncio
import json
import os
import random
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any


# ── Stealth configuration ─────────────────────────────────────────────────────

# Rotate through realistic user-agent strings to avoid bot detection
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
]

_STEALTH_MODE = True   # Enable randomized delays and UA rotation

# Module-level LLM client for vision-click fallback (T004)
_llm_client: Any = None


def set_llm_client(client: Any) -> None:
    global _llm_client
    _llm_client = client


def _find_nix_chromium() -> str | None:
    """Locate the Replit/Nix-provided Chromium binary for Playwright."""
    candidates = [
        "/nix/store/kcvsxrmgwp3ffz5jijyy7wn9fcsjl4hz-playwright-browsers-1.55.0-with-cjk"
        "/chromium-1187/chrome-linux/chrome",
    ]
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path

    import glob as _glob
    matches = _glob.glob(
        "/nix/store/*playwright-browsers*/chromium-*/chrome-linux/chrome"
    )
    for path in sorted(matches, reverse=True):
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


_NIX_CHROMIUM = _find_nix_chromium()

Arix_DOWNLOADS = Path.home() / ".arix" / "downloads"

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
    r'^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|0\.0\.0\.0'
    r'|169\.254\.'           # link-local / AWS/GCP metadata IP
    r'|0\d+\.'               # octal IP
    r')',
    re.I,
)
# IPv6 matched on already-decoded hostname (no brackets), case-insensitive
PRIVATE_IPV6_RE = re.compile(
    r'^(::1'                 # loopback
    r'|fe80:'                # link-local
    r'|fc[0-9a-f]{2}:'      # unique-local fc00::/7 (fc)
    r'|fd[0-9a-f]{2}:'      # unique-local fc00::/7 (fd)
    r')',
    re.I,
)
PAYMENT_URL_RE = re.compile(r'(stripe|paypal|braintree|square)\.com/(pay|checkout)', re.I)


def _check_url_safety(url: str) -> tuple[bool, str]:
    if not url:
        return False, "Empty URL"
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in ("file", "data", "javascript", "vbscript"):
        return False, f"{parsed.scheme}:// URLs are blocked"
    if not parsed.scheme.startswith("http"):
        return False, f"Non-HTTP scheme blocked: {parsed.scheme}"
    # Block embedded credentials  (user:pass@host)
    netloc = parsed.netloc
    if "@" in netloc:
        return False, "URLs with embedded credentials are blocked"
    # parsed.hostname handles IPv6 brackets and returns lowercase without brackets
    host = parsed.hostname or ""
    if PRIVATE_IP_RE.match(host) or PRIVATE_IP_RE.match(f"{host}."):
        return False, f"Private/local URL blocked: {host}"
    if PRIVATE_IPV6_RE.match(host):
        return False, f"Private IPv6 URL blocked: {host}"
    if PAYMENT_URL_RE.search(url):
        return False, f"Payment URL blocked: {url}"
    return True, ""


# ── Module-level browser instance for graceful shutdown ──────────────────────

_module_browser: "BrowserController | None" = None


async def close_browser() -> None:
    """Gracefully stop the module-level browser instance (called on server shutdown)."""
    global _module_browser
    if _module_browser is not None:
        try:
            await _module_browser.stop()
        except Exception:
            pass
        _module_browser = None


# ── Vision-click fallback helpers (Gap #4) ────────────────────────────────────

async def _vision_click_fallback(page: Any, description: str) -> dict:
    """Take a screenshot, ask LLM for element coordinates, then coordinate-click.

    Used when CSS/text selectors fail to locate an element.
    """
    if _llm_client is None or not _llm_client.is_available():
        return {"error": "Vision fallback requires LLM client — not configured"}

    Arix_DOWNLOADS.mkdir(parents=True, exist_ok=True)
    screenshot_path = str(Arix_DOWNLOADS / f"vision_click_{int(time.time())}.png")

    try:
        await page.screenshot(path=screenshot_path, full_page=False)
    except Exception as e:
        return {"error": f"Screenshot for vision fallback failed: {e}"}

    question = (
        f"In this browser screenshot, locate the clickable element that best matches: '{description}'. "
        "Return ONLY a JSON object with the element's center pixel coordinates, e.g.: "
        '{"x": 320, "y": 150}. '
        "No other text, no explanation."
    )

    try:
        from arix.tools.vision_tools import _vision_call
        response = await _vision_call(screenshot_path, question)
        m = re.search(r'\{[^}]+\}', response)
        if m:
            coords = json.loads(m.group())
            x = int(float(str(coords.get("x", 0))))
            y = int(float(str(coords.get("y", 0))))
            if x > 0 and y > 0:
                await page.mouse.click(x, y)
                return {
                    "clicked_via_vision": True,
                    "coordinates": {"x": x, "y": y},
                    "description": description,
                    "url": page.url,
                }
        return {"error": "Vision fallback: could not parse coordinates from LLM response",
                "raw_response": response[:200]}
    except Exception as e:
        return {"error": f"Vision click fallback failed: {e}"}


class BrowserController:
    """Playwright browser controller with stealth and vision-click fallback."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._browser = None
        self._page = None
        self._context = None
        self._playwright = None
        self._selected_ua = random.choice(_USER_AGENTS)

    async def start(self) -> None:
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            try:
                launch_kwargs: dict = {"headless": self.headless}
                if _NIX_CHROMIUM:
                    launch_kwargs["executable_path"] = _NIX_CHROMIUM

                # Gap #11: stealth launch args
                if _STEALTH_MODE:
                    launch_kwargs["args"] = [
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--disable-default-apps",
                    ]

                self._browser = await self._playwright.chromium.launch(**launch_kwargs)
            except Exception as launch_err:
                await self._playwright.stop()
                self._playwright = None
                msg = str(launch_err)
                if "Executable doesn't exist" in msg or "playwright install" in msg.lower():
                    raise RuntimeError(
                        "Chromium browser not installed. "
                        "Run: python -m playwright install chromium"
                    ) from launch_err
                raise RuntimeError(f"Browser launch failed: {msg}") from launch_err

            # Gap #11: rotate user agent per session
            self._context = await self._browser.new_context(
                user_agent=self._selected_ua,
                java_script_enabled=True,
                accept_downloads=True,
                locale="en-US",
                viewport={"width": 1280 + random.randint(-40, 40),
                           "height": 800 + random.randint(-20, 20)},
            )

            # Gap #11: hide webdriver property
            if _STEALTH_MODE:
                await self._context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )

            self._page = await self._context.new_page()

            # Gap #11: playwright-stealth for advanced bot detection evasion
            # Suppresses CDP fingerprints, canvas noise, WebGL props, etc.
            if _STEALTH_MODE:
                try:
                    from playwright_stealth import stealth_async
                    await stealth_async(self._page)
                except ImportError:
                    pass  # Falls back to manual add_init_script above
        except ImportError:
            raise RuntimeError(
                "Playwright not installed. Run: pip install playwright && python -m playwright install chromium"
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
            # Gap #11: small random pre-navigation pause
            if _STEALTH_MODE:
                await asyncio.sleep(random.uniform(0.1, 0.4))
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

        Arix_DOWNLOADS.mkdir(parents=True, exist_ok=True)

        try:
            async with self._page.expect_download() as download_info:
                await self._page.goto(url)
            download = await download_info.value
            filename = download.suggested_filename or Path(parsed.path).name or "download"
            dest = Arix_DOWNLOADS / filename
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

    async def click_element(self, selector: str, timeout: int = 10000,
                             description: str | None = None) -> dict:
        """Click an element by CSS selector.

        Gap #4: If CSS selector fails, automatically falls back to vision-grounded
        coordinate clicking — takes a screenshot, asks LLM for coordinates, clicks.
        Gap #11: Adds a small random pre-click delay for more human-like behavior.
        """
        if not self._page:
            return {"error": "Browser not started"}

        # Gap #11: human-like pre-click pause
        if _STEALTH_MODE:
            await asyncio.sleep(random.uniform(0.08, 0.25))

        try:
            await self._page.click(selector, timeout=timeout)
            return {"clicked": selector, "url": self._page.url}
        except Exception as primary_err:
            # Gap #4: Vision fallback when selector fails
            desc = description or selector
            vision_result = await _vision_click_fallback(self._page, desc)
            if "error" not in vision_result:
                vision_result["selector_failed"] = str(primary_err)[:100]
                return vision_result
            # Both failed — return original error enriched with fallback status
            return {
                "error": str(primary_err),
                "selector": selector,
                "vision_fallback_attempted": True,
                "vision_fallback_error": vision_result.get("error", ""),
            }

    async def type_text(self, selector: str, text: str, clear_first: bool = True,
                        timeout: int = 10000) -> dict:
        """Type text into a field.

        Gap #11: Randomized per-keystroke delay (35–80ms) for human-like typing.
        """
        if not self._page:
            return {"error": "Browser not started"}
        try:
            await self._page.wait_for_selector(selector, timeout=timeout)
            if clear_first:
                await self._page.fill(selector, "")
                # Gap #11: brief pause after clearing
                if _STEALTH_MODE:
                    await asyncio.sleep(random.uniform(0.05, 0.15))

            # Gap #11: randomized keystroke delay
            typing_delay = random.randint(35, 80) if _STEALTH_MODE else 30
            await self._page.type(selector, text, delay=typing_delay)

            # Gap #11: brief pause after typing
            if _STEALTH_MODE:
                await asyncio.sleep(random.uniform(0.1, 0.3))

            return {"typed": text[:50], "selector": selector,
                    "stealth": _STEALTH_MODE, "typing_delay_ms": typing_delay}
        except Exception as e:
            return {"error": str(e)}

    async def fill_form(self, fields: list[dict]) -> dict:
        if not self._page:
            return {"error": "Browser not started"}
        results = []
        for field in fields:
            selector = field.get("selector", "")
            value = field.get("value", "")
            field_type = field.get("type", "text")
            try:
                if field_type == "select":
                    await self._page.select_option(selector, value)
                elif field_type == "checkbox":
                    if value:
                        await self._page.check(selector)
                    else:
                        await self._page.uncheck(selector)
                else:
                    await self._page.fill(selector, value)
                    # Gap #11: small inter-field pause
                    if _STEALTH_MODE:
                        await asyncio.sleep(random.uniform(0.1, 0.3))
                results.append({"selector": selector, "ok": True})
            except Exception as e:
                results.append({"selector": selector, "error": str(e)})
        return {"fields_filled": len([r for r in results if r.get("ok")]),
                "results": results}

    async def get_page_source(self) -> dict:
        if not self._page:
            return {"error": "Browser not started"}
        try:
            content = await self._page.content()
            return {"html": content[:32768], "url": self._page.url,
                    "truncated": len(content) > 32768}
        except Exception as e:
            return {"error": str(e)}

    async def wait_for_element(self, selector: str, state: str = "visible",
                                timeout: int = 15000) -> dict:
        if not self._page:
            return {"error": "Browser not started"}
        try:
            await self._page.wait_for_selector(selector, state=state, timeout=timeout)
            return {"found": True, "selector": selector, "state": state}
        except Exception as e:
            return {"found": False, "error": str(e), "selector": selector}

    async def scroll_page(self, direction: str = "down", amount: int = 500) -> dict:
        if not self._page:
            return {"error": "Browser not started"}
        try:
            if direction == "down":
                await self._page.evaluate(f"window.scrollBy(0, {amount})")
            elif direction == "up":
                await self._page.evaluate(f"window.scrollBy(0, -{amount})")
            elif direction == "top":
                await self._page.evaluate("window.scrollTo(0, 0)")
            elif direction == "bottom":
                await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            return {"scrolled": direction, "amount": amount}
        except Exception as e:
            return {"error": str(e)}

    async def go_back(self) -> dict:
        if not self._page:
            return {"error": "Browser not started"}
        try:
            await self._page.go_back(wait_until="domcontentloaded", timeout=15000)
            return {"url": self._page.url, "title": await self._page.title()}
        except Exception as e:
            return {"error": str(e)}

    async def screenshot(self, path: str | None = None) -> dict:
        if not self._page:
            return {"error": "Browser not started"}
        try:
            if path is None:
                Arix_DOWNLOADS.mkdir(parents=True, exist_ok=True)
                path = str(Arix_DOWNLOADS / f"screenshot_{int(time.time())}.png")
            data = await self._page.screenshot(path=path, full_page=False)
            return {"saved": path, "url": self._page.url, "bytes": len(data)}
        except Exception as e:
            return {"error": str(e)}

    async def get_structured_data(self, selector: str | None = None) -> dict:
        if not self._page:
            return {"error": "Browser not started"}
        try:
            script = """(sel) => {
                const root = sel ? document.querySelector(sel) : document;
                if (!root) return {error: 'selector not found'};
                const tables = [];
                root.querySelectorAll('table').forEach(t => {
                    const rows = [];
                    t.querySelectorAll('tr').forEach(r => {
                        const cells = [];
                        r.querySelectorAll('td,th').forEach(c => cells.push(c.innerText.trim()));
                        if (cells.length) rows.push(cells);
                    });
                    if (rows.length) tables.push(rows);
                });
                const lists = [];
                root.querySelectorAll('ul,ol').forEach(l => {
                    const items = [];
                    l.querySelectorAll('li').forEach(i => items.push(i.innerText.trim()));
                    if (items.length) lists.push(items);
                });
                return {tables, lists};
            }"""
            data = await self._page.evaluate(script, selector)
            return {"data": data, "url": self._page.url}
        except Exception as e:
            return {"error": str(e)}


# ── Singleton controller ──────────────────────────────────────────────────────

_browser_controller: BrowserController | None = None


def get_browser_controller() -> BrowserController:
    global _browser_controller
    if _browser_controller is None:
        _browser_controller = BrowserController(headless=True)
    return _browser_controller


# ── Public tool functions ─────────────────────────────────────────────────────

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
                "destination": str(Arix_DOWNLOADS)}
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


async def browser_click(selector: str, description: str | None = None,
                         dry_run: bool = False) -> dict:
    """Click an element. If CSS selector fails, tries vision-based coordinate click."""
    if dry_run:
        return {"dry_run": True, "would_click": selector}
    controller = get_browser_controller()
    if not controller._page:
        return {"error": "No browser page open. Navigate to a URL first."}
    return await controller.click_element(selector, description=description)


async def browser_type_text(selector: str, text: str, clear_first: bool = True,
                             dry_run: bool = False) -> dict:
    if dry_run:
        return {"dry_run": True, "would_type": text[:50], "selector": selector}
    controller = get_browser_controller()
    if not controller._page:
        return {"error": "No browser page open. Navigate to a URL first."}
    return await controller.type_text(selector, text, clear_first)


async def browser_fill_form(fields: list[dict], dry_run: bool = False) -> dict:
    if dry_run:
        return {"dry_run": True, "fields": len(fields)}
    controller = get_browser_controller()
    if not controller._page:
        return {"error": "No browser page open. Navigate to a URL first."}
    return await controller.fill_form(fields)


async def browser_get_page_source(dry_run: bool = False) -> dict:
    if dry_run:
        return {"dry_run": True, "action": "get_page_source"}
    controller = get_browser_controller()
    if not controller._page:
        return {"error": "No browser page open. Navigate to a URL first."}
    return await controller.get_page_source()


async def browser_screenshot(path: str | None = None, dry_run: bool = False) -> dict:
    if dry_run:
        return {"dry_run": True, "action": "screenshot"}
    controller = get_browser_controller()
    if not controller._page:
        return {"error": "No browser page open. Navigate to a URL first."}
    return await controller.screenshot(path)


async def browser_wait_for_element(selector: str, state: str = "visible",
                                    timeout: int = 15000, dry_run: bool = False) -> dict:
    if dry_run:
        return {"dry_run": True, "selector": selector, "state": state}
    controller = get_browser_controller()
    if not controller._page:
        return {"error": "No browser page open. Navigate to a URL first."}
    return await controller.wait_for_element(selector, state, timeout)


async def browser_scroll(direction: str = "down", amount: int = 500,
                          dry_run: bool = False) -> dict:
    if dry_run:
        return {"dry_run": True, "direction": direction}
    controller = get_browser_controller()
    if not controller._page:
        return {"error": "No browser page open. Navigate to a URL first."}
    return await controller.scroll_page(direction, amount)


async def browser_go_back(dry_run: bool = False) -> dict:
    if dry_run:
        return {"dry_run": True, "action": "go_back"}
    controller = get_browser_controller()
    if not controller._page:
        return {"error": "No browser page open. Navigate to a URL first."}
    return await controller.go_back()


async def browser_get_structured_data(selector: str | None = None,
                                       dry_run: bool = False) -> dict:
    if dry_run:
        return {"dry_run": True, "action": "get_structured_data"}
    controller = get_browser_controller()
    if not controller._page:
        return {"error": "No browser page open. Navigate to a URL first."}
    return await controller.get_structured_data(selector)
