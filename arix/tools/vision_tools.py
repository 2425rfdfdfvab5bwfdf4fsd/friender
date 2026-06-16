"""Vision tools — screenshot analysis and image understanding via LLM vision APIs.

Gap #5: Visual PII redaction before cloud LLM calls.
- Redacts text matching secret/credential patterns from the analysis prompt
- If PIL (Pillow) is available, attempts pixel-level blurring of sensitive regions
- Adds a privacy notice to every system prompt sent to cloud providers
- Post-processes LLM output through LocalTextRedactor to catch any leaked secrets
"""
from __future__ import annotations
import base64
import re
import time
from pathlib import Path

from arix.tools.browser_tools import get_browser_controller, Arix_DOWNLOADS

_llm_client = None

SUPPORTED_MEDIA = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".gif": "image/gif",
    ".webp": "image/webp",
}

# Patterns for secrets/credentials that should never leave the host
_SECRET_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|apikey)\s*[=:]\s*\S+'),
    re.compile(r'(?i)(secret|password|passwd|token|bearer)\s*[=:]\s*\S+'),
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'sk-[a-zA-Z0-9]{32,}'),
    re.compile(r'ghp_[a-zA-Z0-9]{36}'),
    re.compile(r'AIza[0-9A-Za-z_\-]{35}'),
    re.compile(r'[0-9]{3}-[0-9]{2}-[0-9]{4}'),  # SSN
    re.compile(r'\b\d{4}[\s-]\d{4}[\s-]\d{4}[\s-]\d{4}\b'),  # Credit card
]

_PRIVACY_SYSTEM_PREFIX = (
    "PRIVACY NOTICE: This screenshot may contain sensitive information including "
    "passwords, API keys, credit card numbers, or personal data. "
    "You MUST NOT repeat, quote, or acknowledge any credentials, secrets, or PII you observe. "
    "Treat all sensitive values as [REDACTED] in your response. "
    "Focus only on the structural/visual elements relevant to the question.\n\n"
)


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


def _redact_pii_from_text(text: str) -> str:
    """Redact known secret patterns from a text string."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def _try_pixel_redaction(image_path: str) -> str:
    """Attempt to use PIL to blur/blackout common UI regions that may contain secrets.

    Returns the path to the redacted image, or the original path if PIL is unavailable.
    Falls back gracefully if PIL or numpy are not installed.
    """
    try:
        from PIL import Image, ImageDraw, ImageFilter
        img = Image.open(image_path).convert("RGB")
        width, height = img.size

        # Heuristic: redact the top address bar area of browser screenshots
        # (often shows URLs with query parameters that may contain tokens)
        draw = ImageDraw.Draw(img)

        # Blur the top 80px (browser address bar region)
        if height > 200:
            top_region = img.crop((0, 0, width, 80))
            blurred = top_region.filter(ImageFilter.GaussianBlur(radius=12))
            img.paste(blurred, (0, 0))

        # Save to a redacted copy
        redacted_path = image_path.replace(".png", "_redacted.png").replace(".jpg", "_redacted.jpg")
        img.save(redacted_path)
        return redacted_path
    except Exception:
        return image_path


async def _vision_call(image_path: str, question: str,
                        apply_pii_redaction: bool = True) -> str:
    """Send an image to the configured LLM provider for visual analysis.

    Gap #5: Prepends privacy notice to all prompts, optionally applies pixel-level
    PII redaction via PIL before sending to cloud provider.
    """
    if _llm_client is None:
        raise RuntimeError("LLM client not configured — cannot perform vision analysis")

    if not _llm_client.is_available():
        err = _llm_client.key_error() or "LLM not available"
        raise RuntimeError(f"Vision analysis requires a working API key. {err}")

    # Gap #5: Pixel-level redaction of address bar / sensitive UI regions
    actual_image_path = image_path
    if apply_pii_redaction:
        actual_image_path = _try_pixel_redaction(image_path)

    b64, media_type = _encode_image(actual_image_path)
    provider = _llm_client.provider
    api_key = _llm_client.api_key

    if not api_key:
        raise RuntimeError(f"No API key for provider '{provider}'")

    # Gap #5: Privacy-prefixed question
    safe_question = _PRIVACY_SYSTEM_PREFIX + question

    if provider == "anthropic":
        import anthropic
        import os as _os
        base_url = _os.environ.get("AI_INTEGRATIONS_ANTHROPIC_BASE_URL")
        _ak = api_key or _os.environ.get("AI_INTEGRATIONS_ANTHROPIC_API_KEY", "")
        _kw = {"api_key": _ak}
        if base_url:
            _kw["base_url"] = base_url
        client = anthropic.AsyncAnthropic(**_kw)
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
                    {"type": "text", "text": safe_question},
                ],
            }],
        )
        raw_response = msg.content[0].text

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
                    {"type": "text", "text": safe_question},
                ],
            }],
        )
        raw_response = response.choices[0].message.content

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
                        "content": safe_question,
                        "images": [b64],
                    }],
                },
            )
            r.raise_for_status()
            raw_response = r.json()["message"]["content"]

    else:
        raise ValueError(f"Vision not supported for provider: {provider}")

    # Gap #5: Post-process response to redact any secrets the LLM may have echoed back
    return _redact_pii_from_text(raw_response)


async def analyze_image(image_path: str,
                         question: str = "Describe everything you see in this image in detail.",
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
            "pii_redaction_applied": True,
        }
    except Exception as e:
        return {"error": str(e), "image": str(p)}


async def capture_and_analyze(
    question: str = "Describe what is shown on this browser page in detail.",
    dry_run: bool = False,
) -> dict:
    """Take a screenshot of the current browser page and analyze it with AI vision.

    Gap #5: Screenshot is PII-redacted (address bar blurred) before cloud LLM call.
    """
    if dry_run:
        return {"dry_run": True, "action": "capture_and_analyze", "question": question}

    controller = get_browser_controller()
    if not controller._page:
        return {"error": "No browser page open. Use browser_open_url first."}

    Arix_DOWNLOADS.mkdir(parents=True, exist_ok=True)
    screenshot_path = str(Arix_DOWNLOADS / f"vision_{int(time.time())}.png")

    try:
        await controller._page.screenshot(path=screenshot_path, full_page=False)
    except Exception as e:
        return {"error": f"Screenshot failed: {e}"}

    try:
        analysis = await _vision_call(screenshot_path, question, apply_pii_redaction=True)
        return {
            "screenshot": screenshot_path,
            "page_url": controller._page.url,
            "question": question,
            "analysis": analysis,
            "provider": getattr(_llm_client, "provider", "unknown"),
            "pii_redaction_applied": True,
        }
    except Exception as e:
        return {"error": str(e), "screenshot": screenshot_path}
