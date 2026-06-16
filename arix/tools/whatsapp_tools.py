"""WhatsApp tool — send_whatsapp_message via Meta WhatsApp Cloud API."""
from __future__ import annotations
import os

WA_API_BASE = "https://graph.facebook.com/v21.0"
MAX_MESSAGE_LENGTH = 4096


def wa_token() -> str:
    return os.environ.get("WHATSAPP_ACCESS_TOKEN", "")


def wa_phone_id() -> str:
    return os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")


def wa_is_configured() -> bool:
    return bool(wa_token() and wa_phone_id())


def send_whatsapp_message(to: str, message: str, dry_run: bool = False) -> dict:
    """Send a WhatsApp text message to a phone number via Meta Cloud API.

    Args:
        to:      Recipient phone number in E.164 format (e.g. 14155551234 or +14155551234).
        message: Text body to send (max 4096 chars).
        dry_run: If True, preview the send without making the API call.
    """
    token = wa_token()
    phone_id = wa_phone_id()

    if not token or not phone_id:
        return {
            "error": (
                "WhatsApp not configured. "
                "Set WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID "
                "environment variables in Replit Secrets."
            ),
            "setup_url": "https://developers.facebook.com/apps/",
        }

    to_clean = to.strip().lstrip("+").replace(" ", "").replace("-", "")
    if not to_clean.isdigit():
        return {
            "error": f"Invalid phone number: {to!r}. Use E.164 e.g. 14155551234"
        }

    if len(message) > MAX_MESSAGE_LENGTH:
        message = message[: MAX_MESSAGE_LENGTH - 30] + "\n…(message truncated)"

    if dry_run:
        return {
            "dry_run": True,
            "would_send_to": f"+{to_clean}",
            "message_preview": message[:120] + ("…" if len(message) > 120 else ""),
            "message_length": len(message),
        }

    try:
        import httpx

        resp = httpx.post(
            f"{WA_API_BASE}/{phone_id}/messages",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to_clean,
                "type": "text",
                "text": {"body": message, "preview_url": False},
            },
            timeout=30.0,
        )

        if resp.status_code == 200:
            data = resp.json()
            msgs = data.get("messages", [])
            msg_id = msgs[0].get("id", "") if msgs else ""
            return {
                "sent": True,
                "to": f"+{to_clean}",
                "message_id": msg_id,
                "message_length": len(message),
            }
        else:
            return {
                "error": f"WhatsApp API {resp.status_code}",
                "detail": resp.text[:400],
            }

    except ImportError:
        return {"error": "httpx not installed. Run: pip install httpx"}
    except Exception as e:
        return {"error": str(e)}
