"""Desktop tools — control the user's local computer via the bridge agent.

These tools route commands through BridgeManager → local_bridge/bridge_agent.py
running on the user's machine, which executes them with pyautogui.

All tools are async; they block until the bridge responds or times out.
"""
from __future__ import annotations

import asyncio
import base64
import json
from typing import Any


def _bridge():
    from pacca.bridge_manager import get_bridge
    return get_bridge()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _not_connected() -> dict:
    return {
        "ok": False,
        "error": (
            "Local bridge not connected.\n"
            "Run  python local_bridge/bridge_agent.py  on your computer first,\n"
            "then try again."
        ),
    }


def _fmt(result: dict) -> str:
    """Convert a bridge result dict to a human-readable string."""
    if not result.get("ok"):
        return f"❌ {result.get('error', 'Unknown error')}"
    msg = result.get("message", "")
    data = result.get("data")
    if data:
        return f"{msg}\n{json.dumps(data, indent=2)}" if msg else json.dumps(data, indent=2)
    return msg or "✅ Done"


# ── Tools ─────────────────────────────────────────────────────────────────────

async def desktop_screenshot(region: str | None = None) -> dict:
    """Take a screenshot of the local desktop.

    Args:
        region: Optional "x,y,width,height" to capture a sub-region.
    Returns dict with keys:
        ok: bool
        image_b64: base64-encoded PNG string
        width, height: pixel dimensions
        message: status string
    """
    b = _bridge()
    if not b.is_connected:
        return _not_connected()
    args: dict[str, Any] = {}
    if region:
        args["region"] = region
    result = await b.send_command("desktop_screenshot", args)
    if result.get("ok") and result.get("image_b64"):
        result["message"] = f"Screenshot captured ({result.get('width', '?')}×{result.get('height', '?')} px)"
    return result


async def desktop_click(
    x: int | None = None,
    y: int | None = None,
    description: str | None = None,
    button: str = "left",
    clicks: int = 1,
) -> dict:
    """Click at screen coordinates or find an element by description.

    Args:
        x, y: Pixel coordinates (required if description not given).
        description: Natural-language description of what to click. When given,
            PACCA takes a screenshot and uses AI vision to find the element.
        button: "left" | "right" | "middle"
        clicks: 1 for single-click, 2 for double-click.
    """
    b = _bridge()
    if not b.is_connected:
        return _not_connected()

    if description and (x is None or y is None):
        coords = await _vision_find(description)
        if coords is None:
            return {"ok": False, "error": f"Could not find '{description}' on screen"}
        x, y = coords

    if x is None or y is None:
        return {"ok": False, "error": "Either (x, y) or description must be provided"}

    result = await b.send_command("desktop_click", {
        "x": int(x), "y": int(y), "button": button, "clicks": int(clicks),
    })
    result.setdefault("message", f"Clicked ({x}, {y}) with {button} button × {clicks}")
    return result


async def desktop_double_click(
    x: int | None = None,
    y: int | None = None,
    description: str | None = None,
) -> dict:
    """Double-click at coordinates or on a described UI element."""
    return await desktop_click(x=x, y=y, description=description, clicks=2)


async def desktop_right_click(
    x: int | None = None,
    y: int | None = None,
    description: str | None = None,
) -> dict:
    """Right-click at coordinates or on a described UI element."""
    return await desktop_click(x=x, y=y, description=description, button="right")


async def desktop_type_text(text: str, interval: float = 0.03) -> dict:
    """Type text at the current cursor position.

    Args:
        text: The string to type (unicode supported).
        interval: Seconds between keystrokes (0.03 = human-like pace).
    """
    b = _bridge()
    if not b.is_connected:
        return _not_connected()
    result = await b.send_command("desktop_type_text", {"text": text, "interval": interval})
    result.setdefault("message", f"Typed {len(text)} characters")
    return result


async def desktop_key(keys: str) -> dict:
    """Press a keyboard shortcut or key combination.

    Args:
        keys: Key name or combo, e.g. "ctrl+c", "alt+tab", "enter",
              "cmd+space", "f5", "ctrl+shift+t".
              Use "+" to join modifier keys with the main key.
    """
    b = _bridge()
    if not b.is_connected:
        return _not_connected()
    result = await b.send_command("desktop_key", {"keys": keys})
    result.setdefault("message", f"Pressed: {keys}")
    return result


async def desktop_scroll(
    x: int,
    y: int,
    direction: str = "down",
    amount: int = 3,
) -> dict:
    """Scroll the mouse wheel at a position.

    Args:
        x, y: Pixel coordinates to scroll at.
        direction: "up" or "down".
        amount: Number of scroll clicks (3 = one standard page scroll).
    """
    b = _bridge()
    if not b.is_connected:
        return _not_connected()
    result = await b.send_command("desktop_scroll", {
        "x": int(x), "y": int(y), "direction": direction, "amount": int(amount),
    })
    result.setdefault("message", f"Scrolled {direction} at ({x}, {y})")
    return result


async def desktop_move_mouse(x: int, y: int, duration: float = 0.2) -> dict:
    """Move the mouse cursor to a position without clicking.

    Args:
        x, y: Target pixel coordinates.
        duration: Seconds to take for the movement (smooth human-like move).
    """
    b = _bridge()
    if not b.is_connected:
        return _not_connected()
    result = await b.send_command("desktop_move_mouse", {
        "x": int(x), "y": int(y), "duration": duration,
    })
    result.setdefault("message", f"Mouse moved to ({x}, {y})")
    return result


async def desktop_drag(
    from_x: int,
    from_y: int,
    to_x: int,
    to_y: int,
    duration: float = 0.5,
    button: str = "left",
) -> dict:
    """Click-and-drag from one position to another.

    Args:
        from_x, from_y: Start coordinates.
        to_x, to_y: End coordinates.
        duration: Seconds for the drag movement.
        button: Mouse button to hold ("left" | "right").
    """
    b = _bridge()
    if not b.is_connected:
        return _not_connected()
    result = await b.send_command("desktop_drag", {
        "from_x": int(from_x), "from_y": int(from_y),
        "to_x": int(to_x), "to_y": int(to_y),
        "duration": duration, "button": button,
    })
    result.setdefault("message", f"Dragged ({from_x},{from_y}) → ({to_x},{to_y})")
    return result


async def desktop_find_and_click(description: str, button: str = "left") -> dict:
    """Take a screenshot, use AI vision to find the described element, then click it.

    This is the primary "human-like" tool — give it a natural-language
    description of what to click and PACCA handles the rest.

    Args:
        description: E.g. "the blue Submit button", "Chrome's address bar",
                     "the Trash icon on the desktop", "the Close tab × button".
        button: "left" | "right" | "middle"
    """
    b = _bridge()
    if not b.is_connected:
        return _not_connected()

    ss = await b.send_command("desktop_screenshot", {})
    if not ss.get("ok"):
        return {"ok": False, "error": f"Screenshot failed: {ss.get('error')}"}

    image_b64 = ss.get("image_b64", "")
    coords = await _vision_find_from_b64(description, image_b64)
    if coords is None:
        return {"ok": False, "error": f"Could not locate '{description}' on screen"}

    x, y = coords
    result = await b.send_command("desktop_click", {
        "x": int(x), "y": int(y), "button": button, "clicks": 1,
    })
    result["found_at"] = {"x": x, "y": y}
    result.setdefault("message", f"Found '{description}' at ({x},{y}) and clicked")
    return result


async def desktop_read_screen(region: str | None = None) -> dict:
    """Screenshot the desktop and extract all visible text (OCR via AI vision).

    Args:
        region: Optional "x,y,width,height" to restrict to a sub-region.
    Returns dict with:
        ok: bool
        text: extracted text string
        image_b64: raw screenshot (base64 PNG)
    """
    b = _bridge()
    if not b.is_connected:
        return _not_connected()

    args: dict[str, Any] = {}
    if region:
        args["region"] = region
    ss = await b.send_command("desktop_screenshot", args)
    if not ss.get("ok"):
        return ss

    image_b64 = ss.get("image_b64", "")
    text = await _vision_ocr(image_b64)
    return {"ok": True, "text": text, "image_b64": image_b64, "message": "Screen text extracted"}


# ── Vision helpers (calls LLM with the screenshot) ────────────────────────────

async def _vision_find(description: str) -> tuple[int, int] | None:
    """Take a fresh screenshot and find the element using AI vision."""
    b = _bridge()
    ss = await b.send_command("desktop_screenshot", {})
    if not ss.get("ok"):
        return None
    return await _vision_find_from_b64(description, ss.get("image_b64", ""))


async def _vision_find_from_b64(description: str, image_b64: str) -> tuple[int, int] | None:
    """Ask the LLM vision model to find pixel coordinates of a described element."""
    try:
        from pacca.llm_client import LLMClient
        import os

        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return None

        client = LLMClient()
        if not client.is_available():
            return None

        prompt = (
            f"Look at this screenshot and find: {description}\n"
            "Reply with ONLY: x=NNN y=NNN (the pixel coordinates of the center of the element).\n"
            "If you cannot find it, reply: NOT_FOUND"
        )
        response = await asyncio.to_thread(
            client.vision_query, prompt, image_b64
        )
        if not response or "NOT_FOUND" in response:
            return None

        import re
        m = re.search(r"x=(\d+)\s+y=(\d+)", response)
        if m:
            return int(m.group(1)), int(m.group(2))
        return None
    except Exception:
        return None


async def _vision_ocr(image_b64: str) -> str:
    """Ask the LLM to extract all text from the screenshot."""
    try:
        from pacca.llm_client import LLMClient
        import os

        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return "[OCR requires an LLM API key]"

        client = LLMClient()
        if not client.is_available():
            return "[LLM not available for OCR]"

        prompt = (
            "Extract ALL visible text from this screenshot.\n"
            "Return it as plain text, preserving logical groupings.\n"
            "Do not add any commentary — text only."
        )
        return await asyncio.to_thread(client.vision_query, prompt, image_b64) or ""
    except Exception:
        return "[OCR failed]"
