"""Core agent API routes — status, tools, sysmon, tasks, audit, settings, trace, skills, reports."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from arix.app_state import get_agent, get_workflow_manager, reset_agent
from arix.config import ArixConfig
from arix.tools.registry import TOOL_REGISTRY
from arix.ui.onboarding import DISCLOSURE_TEXT, is_onboarding_complete, complete_onboarding

router = APIRouter(tags=["agent"])

_VERSION = "9.5.0"


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/api/status")
async def status():
    import os
    agent = get_agent()
    cfg = agent.config
    wm = get_workflow_manager()
    llm_available = agent.llm_client.is_available() if agent.llm_client else False
    return {
        "version": _VERSION,
        "provider": cfg.provider,
        "model": cfg.model,
        "offline_mode": cfg.offline_mode,
        "llm_available": llm_available,
        "llm_error": agent.llm_client.key_error() if agent.llm_client else "No LLM client",
        "onboarding_complete": is_onboarding_complete(),
        "tool_count": len(TOOL_REGISTRY),
        "circuit_breaker": agent.llm_client.circuit_status() if agent.llm_client else {},
        "risk_confirm_threshold": cfg.risk_confirm_threshold,
        "risk_proceed_threshold": cfg.risk_proceed_threshold,
        "max_file_egress_bytes": cfg.max_file_egress_bytes,
        "whatsapp_configured": bool(
            os.environ.get("WHATSAPP_ACCESS_TOKEN") and os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
        ),
        "whatsapp_allowed_count": len({
            n.strip().lstrip("+")
            for n in os.environ.get("WHATSAPP_ALLOWED_NUMBERS", "").split(",")
            if n.strip()
        }),
        "memory_task_count": agent.memory.task_count(),
        "workflow_count": len(wm.list_workflows()) if wm else 0,
        "sandbox": __import__("arix.security.sandbox", fromlist=["get_sandbox_capabilities"]).get_sandbox_capabilities(),
        "whatsapp_secrets": {
            "access_token": bool(os.environ.get("WHATSAPP_ACCESS_TOKEN")),
            "phone_number_id": bool(os.environ.get("WHATSAPP_PHONE_NUMBER_ID")),
            "verify_token": bool(os.environ.get("WHATSAPP_VERIFY_TOKEN")),
            "allowed_numbers": bool(os.environ.get("WHATSAPP_ALLOWED_NUMBERS")),
            "webhook_secret": bool(os.environ.get("WHATSAPP_WEBHOOK_SECRET")),
        },
    }


# ── Cache stats ───────────────────────────────────────────────────────────────

@router.get("/api/cache/stats")
async def cache_stats():
    """Return hit/miss stats for the LLM response cache and tool result cache."""
    from arix.smart_router import get_response_cache
    from arix import tool_cache
    return {
        "response_cache": get_response_cache().stats(),
        "tool_cache": tool_cache.stats(),
    }


@router.post("/api/cache/clear")
async def cache_clear():
    """Clear both caches (useful after config changes)."""
    from arix.smart_router import get_response_cache
    from arix import tool_cache
    get_response_cache().clear()
    tool_cache.invalidate()
    return {"cleared": True}


# ── Tools & disclosure ────────────────────────────────────────────────────────

@router.get("/api/tools")
async def get_tools():
    tools = [
        {
            "name": name,
            "description": meta.description,
            "risk_level": meta.risk_level.value,
            "domain": meta.domain,
            "requires_confirmation": meta.requires_confirmation,
            "reversible": meta.reversible,
            "data_egress": meta.data_egress,
            "undo_supported": meta.undo_supported,
        }
        for name, meta in TOOL_REGISTRY.items()
    ]
    return {"tools": tools}


@router.get("/api/disclosure")
async def get_disclosure():
    return {"text": DISCLOSURE_TEXT}


# ── System monitor ────────────────────────────────────────────────────────────

@router.get("/api/sysmon")
async def get_sysmon():
    try:
        from arix.tools.system_tools import system_monitor
        return await asyncio.to_thread(system_monitor, include_processes=True, top_n_processes=10)
    except Exception as e:
        return {"error": str(e)}


# ── Task history & undo ───────────────────────────────────────────────────────

@router.get("/api/task-history")
async def get_task_history(n: int = 20):
    return {"history": get_agent().task_history.get_recent(n)}


@router.get("/api/undo-history")
async def get_undo_history():
    return {"history": get_agent().undo_manager.history(20)}


@router.post("/api/undo")
async def undo_last():
    return get_agent().undo_manager.undo_last()


# ── Execution trace ───────────────────────────────────────────────────────────

@router.get("/api/trace")
async def list_traces():
    agent = get_agent()
    return {"task_ids": list(reversed(list(agent._trace.keys())))[:20]}


@router.get("/api/trace/{task_id}")
async def get_trace(task_id: str):
    agent = get_agent()
    entries = agent._trace.get(task_id, [])
    return {"task_id": task_id, "entries": entries, "entry_count": len(entries)}


# ── Active goals ──────────────────────────────────────────────────────────────

@router.get("/api/active-goals")
async def get_active_goals():
    try:
        return {"active_goals": get_agent().supervisor.active_goals()}
    except Exception as e:
        return {"active_goals": [], "error": str(e)}


# ── Insights (alias for memory stats) ────────────────────────────────────────

@router.get("/api/insights")
async def get_insights():
    try:
        return get_agent().memory.get_stats()
    except Exception as e:
        return {"error": str(e), "total_tasks": 0, "success_rate": 0,
                "domains": [], "daily_activity": [], "recent_commands": []}


# ── Audit log ─────────────────────────────────────────────────────────────────

@router.get("/api/audit-log")
async def get_audit_log(n: int = 50):
    log_path = Path.home() / ".pacca" / "audit.log"
    if not log_path.exists():
        return {"entries": [], "path": str(log_path)}
    try:
        lines = log_path.read_text().splitlines()
        entries = []
        for line in lines[-n:]:
            try:
                entries.append(json.loads(line))
            except Exception:
                entries.append({"raw": line})
        return {"entries": list(reversed(entries)), "path": str(log_path)}
    except Exception as e:
        return {"entries": [], "error": str(e)}


@router.get("/api/audit/verify")
async def verify_audit_chain():
    from arix.models.audit_log import AuditLogger
    return AuditLogger().verify_chain()


# ── Skills ────────────────────────────────────────────────────────────────────

@router.get("/api/skills")
async def list_skills(search: str = "", limit: int = 20):
    agent = get_agent()
    return {"skills": agent.memory.get_skills(limit=limit, search=search),
            "count": agent.memory.skill_count()}


@router.get("/api/skills/{skill_id}")
async def get_skill(skill_id: int):
    skill = get_agent().memory.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


@router.delete("/api/skills/{skill_id}")
async def delete_skill(skill_id: int):
    deleted = get_agent().memory.delete_skill(skill_id)
    return {"status": "ok" if deleted else "not_found", "id": skill_id}


@router.post("/api/skills/{skill_id}/use")
async def use_skill(skill_id: int):
    agent = get_agent()
    skill = agent.memory.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    agent.memory.mark_skill_used(skill_id)
    return {"skill": skill, "status": "ok"}


# ── Reports ───────────────────────────────────────────────────────────────────

@router.get("/api/reports")
async def list_reports(limit: int = 20, search: str = ""):
    agent = get_agent()
    try:
        return {"reports": agent.memory.get_reports(limit=limit, search=search),
                "total": agent.memory.report_count()}
    except Exception as e:
        return {"reports": [], "total": 0, "error": str(e)}


@router.get("/api/reports/{report_id}")
async def get_report(report_id: int):
    report = get_agent().memory.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return report


@router.delete("/api/reports/{report_id}")
async def delete_report(report_id: int):
    deleted = get_agent().memory.delete_report(report_id)
    return {"status": "ok" if deleted else "not_found", "id": report_id}


# ── Onboarding & settings ─────────────────────────────────────────────────────

@router.post("/api/onboard")
async def onboard(body: dict):
    provider = body.get("provider", "anthropic")
    get_agent().record_provider_consent(provider)
    complete_onboarding(provider)
    return {"status": "ok", "provider": provider}


@router.post("/api/settings")
async def update_settings(body: dict):
    """Update runtime config. Resets the agent so it picks up new settings on next request."""
    cfg = ArixConfig.load()
    field_map = {
        "provider": str,
        "model": str,
        "risk_confirm_threshold": float,
        "risk_proceed_threshold": float,
        "max_file_egress_bytes": int,
    }
    for field, cast in field_map.items():
        if field in body:
            setattr(cfg, field, cast(body[field]))
    cfg.save()
    reset_agent()
    return {
        "status": "ok",
        "config": {
            "provider": cfg.provider,
            "model": cfg.model,
            "risk_confirm_threshold": cfg.risk_confirm_threshold,
            "risk_proceed_threshold": cfg.risk_proceed_threshold,
        },
    }


# ── Providers ─────────────────────────────────────────────────────────────────

@router.get("/api/providers")
async def list_providers():
    """List all 13 supported LLM providers with configuration status and models."""
    from arix.llm_client import list_providers, LLMClient
    providers = list_providers()
    agent = get_agent()
    current_provider = agent.config.provider
    current_model = agent.config.model

    # Check Ollama models dynamically
    ollama_models = []
    try:
        ollama_models = await LLMClient.list_ollama_models()
    except Exception:
        pass

    for p in providers:
        if p["name"] == "ollama":
            p["configured"] = len(ollama_models) > 0
            p["models"] = ollama_models if ollama_models else ["llama3.2", "llama3.1", "mistral"]
            p["ollama_running"] = len(ollama_models) > 0
        p["active"] = p["name"] == current_provider

    return {
        "providers": providers,
        "current_provider": current_provider,
        "current_model": current_model,
        "total": len(providers),
        "configured_count": sum(1 for p in providers if p["configured"]),
    }


@router.post("/api/providers/switch")
async def switch_provider(body: dict):
    """Switch the active LLM provider and model."""
    provider = body.get("provider", "").strip()
    model = body.get("model", "").strip()

    from arix.llm_client import PROVIDER_REGISTRY
    if provider not in PROVIDER_REGISTRY:
        return {"error": f"Unknown provider '{provider}'. Valid: {list(PROVIDER_REGISTRY.keys())}"}

    cfg = ArixConfig.load()
    cfg.provider = provider
    if model:
        cfg.model = model
    else:
        cfg.model = PROVIDER_REGISTRY[provider].get("default_model", cfg.model)
    cfg.save()
    reset_agent()

    return {
        "status": "ok",
        "provider": cfg.provider,
        "model": cfg.model,
        "message": f"Switched to {provider} / {cfg.model}",
    }


# ── Curator endpoints ─────────────────────────────────────────────────────────

@router.get("/api/curator")
async def get_curator_status():
    """Return Skill Curator status and stats."""
    from arix.intelligence.curator import get_curator
    return get_curator().get_status()


@router.get("/api/curator/skills")
async def get_curator_skills():
    """Return all curated skills sorted by score."""
    from arix.intelligence.curator import get_curator
    return {"skills": get_curator().get_all_skills()}


@router.post("/api/curator/run")
async def run_curator_now():
    """Trigger the full 4-stage Curator loop immediately."""
    from arix.intelligence.curator import get_curator
    curator = get_curator()
    agent = get_agent()
    if agent.llm_client:
        curator.set_llm_client(agent.llm_client)
    if agent.memory_manager:
        curator.set_task_history(agent.memory_manager.task_history)
    results = await curator.run_loop()
    return results


@router.delete("/api/curator/skills/{skill_id}")
async def delete_curator_skill(skill_id: str):
    """Remove a skill from the curator library."""
    from arix.intelligence.curator import get_curator
    ok = get_curator().delete_skill(skill_id)
    if not ok:
        raise HTTPException(404, "Skill not found")
    return {"deleted": True, "skill_id": skill_id}


@router.post("/api/curator/skills/{skill_id}/toggle-core")
async def toggle_curator_core(skill_id: str):
    """Toggle a skill's core status (core skills are injected into every planning context)."""
    from arix.intelligence.curator import get_curator
    skill = get_curator().toggle_core(skill_id)
    if skill is None:
        raise HTTPException(404, "Skill not found")
    return skill


# ── Research journal ──────────────────────────────────────────────────────────

@router.get("/api/research/journal")
async def get_research_journal(limit: int = 30):
    """Return the autonomous researcher's full journal of findings with status."""
    from arix.intelligence.autonomous_researcher import get_autonomous_researcher
    researcher = get_autonomous_researcher()
    findings = researcher.get_findings(limit=min(limit, 100))
    status = researcher.get_status()
    return {
        "findings": findings,
        "status": status,
        "total": len(findings),
    }


# ── Researcher interests ──────────────────────────────────────────────────────

@router.get("/api/researcher/interests")
async def get_researcher_interests():
    """Return the autonomous researcher's current seed topics / interest areas."""
    from arix.intelligence.autonomous_researcher import get_autonomous_researcher
    r = get_autonomous_researcher()
    status = r.get_status()
    return {
        "interests": status.get("seed_topics", []),
        "total": len(status.get("seed_topics", [])),
        "status": {
            "running": status.get("running", False),
            "total_sessions": status.get("total_sessions", 0),
            "interval_minutes": status.get("interval_minutes", 45),
        },
    }


@router.post("/api/researcher/interests")
async def add_researcher_interest(body: dict):
    """Add a new seed topic to the autonomous researcher's interest list."""
    topic = (body.get("topic") or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic is required")
    from arix.intelligence.autonomous_researcher import get_autonomous_researcher
    get_autonomous_researcher().add_seed_topic(topic)
    return {"ok": True, "topic": topic}


@router.delete("/api/researcher/interests/{topic}")
async def remove_researcher_interest(topic: str):
    """Remove a seed topic from the autonomous researcher."""
    from arix.intelligence.autonomous_researcher import get_autonomous_researcher
    get_autonomous_researcher().remove_seed_topic(topic)
    return {"ok": True, "topic": topic}


@router.post("/api/researcher/run-now")
async def trigger_researcher_now():
    """Trigger an immediate research session (non-blocking)."""
    from arix.intelligence.autonomous_researcher import get_autonomous_researcher
    get_autonomous_researcher().run_now()
    return {"ok": True, "message": "Research session triggered"}


# ── Ollama model management ───────────────────────────────────────────────────

@router.get("/api/providers/ollama/models")
async def list_ollama_models():
    """List models available in the local Ollama instance."""
    from arix.llm_client import LLMClient
    try:
        models = await LLMClient.list_ollama_models()
        return {"models": models, "count": len(models), "running": len(models) > 0}
    except Exception as e:
        return {"models": [], "count": 0, "running": False, "error": str(e)}


@router.post("/api/providers/ollama/pull")
async def pull_ollama_model(body: dict):
    """Pull (download) an Ollama model by name."""
    import asyncio, os, urllib.request, json as _json
    model = (body.get("model") or "").strip()
    if not model:
        raise HTTPException(status_code=400, detail="model name is required")
    base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

    async def _pull():
        def _do():
            try:
                data = _json.dumps({"name": model, "stream": False}).encode()
                req = urllib.request.Request(
                    f"{base}/api/pull",
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=300) as resp:
                    return _json.loads(resp.read())
            except Exception as exc:
                return {"error": str(exc)}
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _do)

    result = await _pull()
    if "error" in result:
        raise HTTPException(status_code=502, detail=result["error"])
    return {"ok": True, "model": model, "status": result.get("status", "done")}
