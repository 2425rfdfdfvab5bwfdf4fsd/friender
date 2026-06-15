"""Vision tools — screenshot analysis and image understanding via LLM vision APIs."""
from __future__ import annotations
import base64
import time
from pathlib import Path

from pacca.tools.browser_tools import get_browser_controller, PACCA_DOWNLOADS

_llm_client = None

SUPPORTED_MEDIA = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".gif": "image/gif",
    ".webp": "image/webp",
}


def set_llm_client(client) -> None:
    global _llm_client
    _llm_client = client


def _encode_image(path: str) -> tuple[str, str]:
    """Read and base64-encode an image file. Returns (b64_data, media_type)."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"Image not found: {p}")
    ext = p.suffix.lower()
    media_type = SUPPORTED_MEDIA.get(ext, "image/png")
    data = base64.standard_b64encode(p.read_bytes()).decode("utf-8")
    return data, media_type


async def _vision_call(image_path: str, question: str) -> str:
    """Send an image to the configured LLM provider for visual analysis."""
    if _llm_client is None:
        raise RuntimeError("LLM client not configured — cannot perform vision analysis")

    if not _llm_client.is_available():
        err = _llm_client.key_error() or "LLM not available"
        raise RuntimeError(f"Vision analysis requires a working API key. {err}")

    b64, media_type = _encode_image(image_path)
    provider = _llm_client.provider
    api_key = _llm_client.api_key

    if not api_key:
        raise RuntimeError(f"No API key for provider '{provider}'")

    if provider == "anthropic":
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
        msg = await client.messages.create(
            model=_llm_client.model,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": question},
                ],
            }],
        )
        return msg.content[0].text

    elif provider in ("openai", "gemini"):
        import openai as _openai
        if provider == "gemini":
            client = _openai.AsyncOpenAI(
                api_key=api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            )
            model = _llm_client.model
        else:
            client = _openai.AsyncOpenAI(api_key=api_key)
            model = "gpt-4o"

        response = await client.chat.completions.create(
            model=model,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{b64}"},
                    },
                    {"type": "text", "text": question},
                ],
            }],
        )
        return response.choices[0].message.content

    elif provider == "ollama":
        import httpx
        async with httpx.AsyncClient(timeout=60) as http:
            r = await http.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": _llm_client.model,
                    "stream": False,
                    "messages": [{
                        "role": "user",
                        "content": question,
                        "images": [b64],
                    }],
                },
            )
            r.raise_for_status()
            return r.json()["message"]["content"]

    else:
        raise ValueError(f"Vision not supported for provider: {provider}")


async def analyze_image(image_path: str, question: str = "Describe everything you see in this image in detail.",
                         dry_run: bool = False) -> dict:
    """Analyze any image file using AI vision and return a detailed description."""
    p = Path(image_path).expanduser().resolve()
    if dry_run:
        return {"dry_run": True, "would_analyze": str(p), "question": question}

    if not p.exists():
        return {"error": f"Image file not found: {p}"}

    ext = p.suffix.lower()
    if ext not in SUPPORTED_MEDIA:
        return {"error": f"Unsupported image format '{ext}'. Supported: {', '.join(SUPPORTED_MEDIA)}"}

    try:
        analysis = await _vision_call(str(p), question)
        return {
            "image": str(p),
            "question": question,
            "analysis": analysis,
            "provider": getattr(_llm_client, "provider", "unknown"),
        }
    except Exception as e:
        return {"error": str(e), "image": str(p)}


async def capture_and_analyze(question: str = "Describe what is shown on this browser page in detail.",
                               dry_run: bool = False) -> dict:
    """Take a screenshot of the current browser page and analyze it with AI vision."""
    if dry_run:
        return {"dry_run": True, "action": "capture_and_analyze", "question": question}

    controller = get_browser_controller()
    if not controller._page:
        return {"error": "No browser page open. Use browser_open_url first."}

    PACCA_DOWNLOADS.mkdir(parents=True, exist_ok=True)
    screenshot_path = str(PACCA_DOWNLOADS / f"vision_{int(time.time())}.png")

    try:
        await controller._page.screenshot(path=screenshot_path, full_page=False)
    except Exception as e:
        return {"error": f"Screenshot failed: {e}"}

    try:
        analysis = await _vision_call(screenshot_path, question)
        return {
            "screenshot": screenshot_path,
            "page_url": controller._page.url,
            "question": question,
            "analysis": analysis,
            "provider": getattr(_llm_client, "provider", "unknown"),
        }
    except Exception as e:
        return {"error": str(e), "screenshot": screenshot_path}
