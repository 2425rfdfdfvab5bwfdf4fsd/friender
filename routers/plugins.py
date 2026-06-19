"""Plugin/Custom Tool Builder routes — /api/plugins/*

Plugins are user-defined custom tools stored as JSON in ~/.arix/plugins/.
Each plugin has a name, description, trigger phrases, and an action (HTTP endpoint or shell command).
"""
from __future__ import annotations
import json
import uuid
import time
from pathlib import Path
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/plugins", tags=["plugins"])

_PLUGINS_DIR = Path.home() / ".arix" / "plugins"


def _ensure_dir() -> None:
    _PLUGINS_DIR.mkdir(parents=True, exist_ok=True)


def _load_all() -> list[dict]:
    _ensure_dir()
    plugins = []
    for f in sorted(_PLUGINS_DIR.glob("*.json")):
        try:
            plugins.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return plugins


def _load_one(plugin_id: str) -> dict | None:
    _ensure_dir()
    f = _PLUGINS_DIR / f"{plugin_id}.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save(plugin: dict) -> None:
    _ensure_dir()
    pid = plugin["id"]
    (_PLUGINS_DIR / f"{pid}.json").write_text(json.dumps(plugin, indent=2))


def _delete(plugin_id: str) -> bool:
    f = _PLUGINS_DIR / f"{plugin_id}.json"
    if f.exists():
        f.unlink()
        return True
    return False


@router.get("")
async def list_plugins():
    return {"plugins": _load_all(), "count": len(_load_all())}


@router.get("/{plugin_id}")
async def get_plugin(plugin_id: str):
    p = _load_one(plugin_id)
    if not p:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return p


@router.post("")
async def create_plugin(body: dict):
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    plugin = {
        "id": str(uuid.uuid4())[:8],
        "name": name,
        "description": body.get("description", ""),
        "trigger_phrases": body.get("trigger_phrases", []),
        "action_type": body.get("action_type", "http"),
        "action": body.get("action", ""),
        "method": body.get("method", "POST"),
        "headers": body.get("headers", {}),
        "payload_template": body.get("payload_template", ""),
        "icon": body.get("icon", "🔌"),
        "enabled": body.get("enabled", True),
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    _save(plugin)
    return {"ok": True, "plugin": plugin}


@router.put("/{plugin_id}")
async def update_plugin(plugin_id: str, body: dict):
    p = _load_one(plugin_id)
    if not p:
        raise HTTPException(status_code=404, detail="Plugin not found")
    updatable = ["name", "description", "trigger_phrases", "action_type", "action",
                 "method", "headers", "payload_template", "icon", "enabled"]
    for key in updatable:
        if key in body:
            p[key] = body[key]
    p["updated_at"] = time.time()
    _save(p)
    return {"ok": True, "plugin": p}


@router.delete("/{plugin_id}")
async def delete_plugin(plugin_id: str):
    if not _delete(plugin_id):
        raise HTTPException(status_code=404, detail="Plugin not found")
    return {"ok": True, "deleted": plugin_id}


@router.post("/{plugin_id}/test")
async def test_plugin(plugin_id: str):
    """Test-fire a plugin action."""
    p = _load_one(plugin_id)
    if not p:
        raise HTTPException(status_code=404, detail="Plugin not found")
    if p.get("action_type") == "http":
        import httpx
        import asyncio
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                method = p.get("method", "POST").upper()
                url = p.get("action", "")
                if not url:
                    return {"ok": False, "error": "No action URL configured"}
                headers = p.get("headers", {})
                payload = p.get("payload_template", "")
                if method == "GET":
                    r = await client.get(url, headers=headers)
                else:
                    r = await client.post(url, content=payload, headers=headers)
                return {"ok": True, "status": r.status_code, "response": r.text[:500]}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": f"Action type '{p.get('action_type')}' not testable via API"}
