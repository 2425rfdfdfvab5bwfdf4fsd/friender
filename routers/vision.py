"""Vision router — accepts a base64 image from the browser and calls the LLM vision API."""
from __future__ import annotations
import base64
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/vision", tags=["vision"])


class VisionRequest(BaseModel):
    image_b64: str
    question: str = "Describe what you see in this screenshot in detail."
    media_type: str = "image/png"


@router.post("/analyze")
async def vision_analyze(req: VisionRequest):
    """Receive a base64 screenshot from the browser, call the LLM vision API, return analysis."""
    try:
        from arix.tools.vision_tools import _vision_call, _llm_client

        if _llm_client is None or not _llm_client.is_available():
            return {
                "ok": False,
                "error": "No API key configured. Add ANTHROPIC_API_KEY or OPENAI_API_KEY to Secrets to enable Vision.",
            }

        # Decode base64 → temp PNG file
        img_data = base64.b64decode(req.image_b64)
        suffix = ".png" if "png" in req.media_type else ".jpg"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        tmp.write(img_data)
        tmp.flush()
        tmp.close()

        analysis = await _vision_call(tmp.name, req.question, apply_pii_redaction=False)

        # Clean up temp file
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except Exception:
            pass

        return {"ok": True, "analysis": analysis}

    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/status")
def vision_status():
    try:
        from arix.tools.vision_tools import _llm_client
        available = _llm_client is not None and _llm_client.is_available()
        return {"ok": True, "available": available}
    except Exception:
        return {"ok": True, "available": False}
