"""Memory API routes — /api/memory/*"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from pacca.app_state import get_agent

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("")
async def get_memory(limit: int = 20, domain: str | None = None):
    agent = get_agent()
    return {
        "recent_tasks": agent.memory.recent_tasks(limit=limit, domain=domain),
        "preferences": agent.memory.get_all_preferences(),
        "task_count": agent.memory.task_count(),
    }


@router.get("/search")
async def search_memory(q: str, top_k: int = 5):
    agent = get_agent()
    return {"query": q, "results": agent.memory.semantic_search(q, top_k=top_k)}


@router.post("/preference")
async def set_preference(body: dict):
    agent = get_agent()
    key = body.get("key", "")
    value = body.get("value")
    if not key:
        raise HTTPException(status_code=400, detail="key required")
    agent.memory.set_preference(key, value)
    return {"status": "ok", "key": key, "value": value}


@router.post("/detect-preferences")
async def detect_implicit_prefs():
    agent = get_agent()
    detected = agent.memory.detect_implicit_preferences()
    return {"detected": detected, "count": len(detected)}


@router.get("/stats")
async def get_memory_stats():
    agent = get_agent()
    try:
        return agent.memory.get_stats()
    except Exception as e:
        return {"error": str(e), "total_tasks": 0, "success_rate": 0,
                "domains": [], "daily_activity": [], "recent_commands": []}


@router.get("/vector")
async def get_vector_stats():
    agent = get_agent()
    try:
        return agent.memory.vector_index_stats()
    except Exception as e:
        return {"error": str(e), "count": 0, "available": False, "provider": "none"}


@router.get("/export")
async def export_memory():
    agent = get_agent()
    records = agent.memory.export_episodic()
    return JSONResponse({
        "version": "8.0.0",
        "exported_at": time.time(),
        "episodic_count": len(records),
        "episodic": records,
    })


@router.post("/import")
async def import_memory(body: dict):
    agent = get_agent()
    records = body.get("episodic", [])
    if not isinstance(records, list):
        raise HTTPException(status_code=400, detail="'episodic' must be a list")
    inserted = agent.memory.import_episodic(records)
    return {"status": "ok", "imported": inserted, "skipped": len(records) - inserted}


@router.delete("/episodic/{row_id}")
async def forget_episodic(row_id: int):
    agent = get_agent()
    if not agent.memory.delete_episodic_by_id(row_id):
        raise HTTPException(status_code=404, detail=f"No episodic entry with id={row_id}")
    return {"status": "ok", "deleted_id": row_id}


@router.get("/weekly")
async def get_weekly_summary(days: int = 7):
    agent = get_agent()
    try:
        return agent.memory.get_weekly_summary(days=days)
    except Exception as e:
        return {"error": str(e), "days": days, "total": 0}


@router.post("/compress")
async def compress_memory(days: int = 7):
    """Summarise episodic records older than `days` days into semantic memory paragraphs."""
    agent = get_agent()
    try:
        llm_fn = None
        if agent.llm_client and agent.llm_client.is_available():
            async def _llm_summarize(prompt: str) -> str:
                return await agent.llm_client.aask(
                    system=(
                        "You are a concise summarizer. Summarize the given list of "
                        "computer-control tasks in 1–2 clear sentences, focusing on "
                        "what was accomplished and any notable patterns."
                    ),
                    user=prompt,
                    max_tokens=200,
                )
            llm_fn = _llm_summarize

        result = agent.memory.compress_old_sessions(days=days, llm_summary_fn=llm_fn)
        return {**result, "days_threshold": days}
    except Exception as e:
        return {"error": str(e), "compressed": 0, "groups": 0}
