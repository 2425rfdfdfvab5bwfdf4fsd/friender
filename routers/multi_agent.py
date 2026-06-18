"""Multi-Agent Router REST API."""
from __future__ import annotations

from fastapi import APIRouter

from arix.intelligence.multi_agent_router import get_router, AGENT_ROLES

router = APIRouter(prefix="/api/agents", tags=["multi_agent"])


@router.get("")
async def list_agents():
    r = get_router()
    return {
        "roles": [
            {
                "name": role.name,
                "icon": role.icon,
                "description": role.description,
                "tool_domains": role.tool_domains,
            }
            for role in AGENT_ROLES
        ],
        "active_sessions": r.get_all_sessions(),
        "routing_history": r.get_routing_history(10),
    }


@router.get("/sessions")
async def get_sessions():
    return {"sessions": get_router().get_all_sessions()}


@router.get("/history")
async def get_routing_history(limit: int = 20):
    return {"history": get_router().get_routing_history(limit)}


@router.post("/detect")
async def detect_role(body: dict):
    command = body.get("command", "")
    r = get_router()
    role, method = await r.route(command)
    return {
        "command": command,
        "role": role.name if role else "general",
        "icon": role.icon if role else "🤖",
        "method": method,
    }
