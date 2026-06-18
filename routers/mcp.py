"""MCP Server management REST API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, Optional

from arix.mcp_client import get_mcp_manager

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class AddServerRequest(BaseModel):
    name: str
    transport: str                 # "stdio" | "http"
    command: Optional[str] = None
    url: Optional[str] = None
    env: Optional[Dict[str, str]] = None


class CallToolRequest(BaseModel):
    server_id: str
    tool_name: str
    arguments: Dict[str, Any] = {}


@router.get("/servers")
async def list_servers():
    return {"servers": get_mcp_manager().list_servers()}


@router.post("/servers")
async def add_server(req: AddServerRequest):
    return get_mcp_manager().add_server(
        name=req.name,
        transport=req.transport,
        command=req.command,
        url=req.url,
        env=req.env,
    )


@router.delete("/servers/{server_id}")
async def remove_server(server_id: str):
    ok = get_mcp_manager().remove_server(server_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Server {server_id} not found")
    return {"ok": True, "server_id": server_id}


@router.post("/servers/{server_id}/connect")
async def connect_server(server_id: str):
    return await get_mcp_manager().connect_server(server_id)


@router.post("/servers/{server_id}/disconnect")
async def disconnect_server(server_id: str):
    return await get_mcp_manager().disconnect_server(server_id)


@router.get("/tools")
async def list_tools():
    return {"tools": get_mcp_manager().get_all_tools()}


@router.post("/call")
async def call_tool(req: CallToolRequest):
    return await get_mcp_manager().call_tool(
        server_id=req.server_id,
        tool_name=req.tool_name,
        arguments=req.arguments,
    )
