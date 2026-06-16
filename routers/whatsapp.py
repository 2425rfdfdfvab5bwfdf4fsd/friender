"""WhatsApp webhook and test routes."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from pacca.app_state import get_agent

router = APIRouter(tags=["whatsapp"])

# Maps sender E.164 number → pending confirmation info {"task_id", "conf_id"}
_wa_pending: dict[str, dict] = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _wa_configured() -> bool:
    return bool(
        os.environ.get("WHATSAPP_ACCESS_TOKEN")
        and os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    )


def _wa_allowed_numbers() -> set[str]:
    raw = os.environ.get("WHATSAPP_ALLOWED_NUMBERS", "")
    return {n.strip().lstrip("+") for n in raw.split(",") if n.strip()}


def _wa_is_allowed(phone: str) -> bool:
    allowed = _wa_allowed_numbers()
    return bool(allowed) and phone.lstrip("+") in allowed


def _wa_verify_signature(body: bytes, signature: str) -> bool:
    secret = os.environ.get("WHATSAPP_WEBHOOK_SECRET", "")
    if not secret:
        return True
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


async def _wa_send_reply(to: str, text: str) -> None:
    from pacca.tools.whatsapp_tools import send_whatsapp_message
    await asyncio.to_thread(send_whatsapp_message, to=to, message=text)


async def _run_wa_command(command: str, sender: str) -> None:
    """Execute an agent command triggered from WhatsApp and send results back."""
    agent = get_agent()
    output_lines: list[str] = []

    try:
        async for event in agent.run_command(command):
            etype, data = event.type, event.data
            if etype == "error":
                output_lines.append(f"❌ {data.get('message', 'Error')}")
            elif etype == "plan":
                steps = data.get("steps", [])
                output_lines.append(f"📋 Plan: {len(steps)} step(s), risk {data.get('risk_score', 0):.0f}")
            elif etype == "confirmation_required":
                await _wa_send_reply(
                    sender,
                    f"⚠️ Arix needs your approval:\n{data.get('message', '')}\n\n"
                    "Reply *YES* to proceed or *NO* to cancel.",
                )
                _wa_pending[sender] = {
                    "task_id": data.get("task_id", ""),
                    "conf_id": data.get("confirmation_id", ""),
                }
            elif etype == "step_complete":
                tool = data.get("tool", "")
                result = data.get("result", {})
                if "error" not in result:
                    output_lines.append(f"✓ {tool}: done")
                else:
                    output_lines.append(f"✗ {tool}: {result['error'][:80]}")
            elif etype == "step_error":
                output_lines.append(f"⚠ Step error: {data.get('error', '')[:80]}")
            elif etype == "completed":
                output_lines.append(f"✅ Done — {data.get('steps_executed', 0)} step(s) executed.")
            elif etype == "cancelled":
                output_lines.append("🚫 Task cancelled.")
            elif etype == "dry_run_complete":
                output_lines.append(
                    f"🔍 Dry-run: {data.get('steps', 0)} step(s) planned, risk {data.get('risk_score', 0):.0f}."
                )
    except Exception as e:
        output_lines.append(f"❌ Internal error: {e}")
    finally:
        _wa_pending.pop(sender, None)

    summary = "\n".join(output_lines) or "Task complete."
    if len(summary) > 4000:
        summary = summary[:3950] + "\n…(truncated)"
    await _wa_send_reply(sender, summary)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/webhook/whatsapp")
async def whatsapp_verify(request: Request):
    """Meta webhook verification handshake."""
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    expected = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
    if mode == "subscribe" and token == expected and challenge and expected:
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/webhook/whatsapp")
async def whatsapp_receive(request: Request):
    """Receive inbound WhatsApp messages and route them to the agent."""
    body_bytes = await request.body()
    if not _wa_verify_signature(body_bytes, request.headers.get("X-Hub-Signature-256", "")):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    try:
        messages = payload["entry"][0]["changes"][0]["value"].get("messages", [])
        for msg in messages:
            sender: str = msg["from"]
            if msg.get("type") != "text":
                continue
            text: str = msg["text"]["body"].strip()

            if sender in _wa_pending:
                pending = _wa_pending.pop(sender, None)
                if pending:
                    get_agent().confirm(pending["task_id"], pending["conf_id"], text)
                continue

            if not _wa_is_allowed(sender):
                await _wa_send_reply(sender, "⛔ Unauthorized — your number is not in Arix's allowed list.")
                continue

            asyncio.create_task(_run_wa_command(text, sender))

    except (KeyError, IndexError):
        pass

    return {"status": "ok"}


@router.get("/api/whatsapp-test")
async def whatsapp_test():
    """Test the WhatsApp API connection using the configured credentials."""
    from pacca.tools.whatsapp_tools import wa_token, wa_phone_id, wa_is_configured, WA_API_BASE
    if not wa_is_configured():
        return {"ok": False, "error": "Not configured — set WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID"}
    try:
        import httpx
        token = wa_token()
        phone_id = wa_phone_id()

        def _call():
            return httpx.get(
                f"{WA_API_BASE}/{phone_id}",
                params={"fields": "verified_name,display_phone_number,quality_rating"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )

        resp = await asyncio.to_thread(_call)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "ok": True,
                "phone": data.get("display_phone_number", ""),
                "name": data.get("verified_name", ""),
                "quality": data.get("quality_rating", ""),
                "phone_number_id": phone_id,
            }
        return {"ok": False, "error": f"API returned {resp.status_code}", "detail": resp.text[:300]}
    except ImportError:
        return {"ok": False, "error": "httpx not installed — run: pip install httpx"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
