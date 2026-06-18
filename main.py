"""Arix v8.0 — FastAPI application factory.

Responsibilities of this file are intentionally narrow:
  - Create the FastAPI app
  - Register middleware (auth + rate limiting)
  - Mount static files and include all routers
  - Manage application lifespan (workflow scheduler, browser cleanup)
  - Serve the root HTML page and favicon

All route handlers live in the routers/ package; shared singletons live in
arix/app_state.py.
"""
from __future__ import annotations

import collections
import os
import time as _time
from contextlib import asynccontextmanager
from pathlib import Path

# Load .env before anything else so API keys are visible to all modules
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from arix.app_state import get_agent, set_workflow_manager
from arix.workflows.workflow_manager import WorkflowManager

from routers import (
    agent_api,
    bridge,
    calendar,
    canvas,
    channels,
    curator,
    drive,
    gmail,
    hands,
    intelligence,
    knowledge,
    marketplace,
    mcp,
    memory,
    multi_agent,
    notion,
    personal,
    plugins,
    research_mode,
    skillhub,
    slack,
    spotify,
    trello,
    vision,
    whatsapp,
    workflows,
    workspaces,
    ws,
    youtube,
)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app_: FastAPI):
    wm = WorkflowManager()
    wm.start_scheduler()
    set_workflow_manager(wm)

    # Auto-detect Ollama if no cloud API keys are configured
    try:
        from arix.config import auto_detect_and_switch_ollama, ArixConfig
        _cfg = ArixConfig.load()
        switched = await auto_detect_and_switch_ollama(_cfg)
        if switched:
            import logging
            logging.getLogger(__name__).info("Auto-switched to Ollama (local LLM)")
    except Exception as _e:
        import logging
        logging.getLogger(__name__).debug("Ollama auto-detect skipped: %s", _e)

    # Wire agent's run_command into the channel manager so bots can call it
    try:
        from arix.channels.channel_manager import get_channel_manager
        from arix.app_state import get_agent

        async def _channel_run_fn(command: str) -> str:
            agent = get_agent()
            chunks = []
            async for chunk in agent.run_command(command):
                if isinstance(chunk, str):
                    chunks.append(chunk)
                elif hasattr(chunk, "text"):
                    chunks.append(chunk.text)
            return "".join(chunks) or "(done)"

        mgr = get_channel_manager()
        mgr.set_command_fn(_channel_run_fn)

        # Wire autonomous researcher
        from arix.intelligence.autonomous_researcher import get_autonomous_researcher
        from arix.intelligence.parallel_dispatch import get_dispatcher
        _agent_instance = get_agent()
        _researcher = get_autonomous_researcher()
        _researcher.set_command_fn(_channel_run_fn)
        if hasattr(_agent_instance, 'llm_client'):
            _researcher.set_llm_client(_agent_instance.llm_client)
            _dispatcher = get_dispatcher()
            _dispatcher.set_command_fn(_channel_run_fn)
            _dispatcher.set_llm_client(_agent_instance.llm_client)
        if hasattr(_agent_instance, 'memory'):
            _researcher.set_memory_manager(_agent_instance.memory)

        # Auto-start any bots configured via environment variables
        import os
        if os.environ.get("TELEGRAM_BOT_TOKEN"):
            await mgr.start_telegram(os.environ["TELEGRAM_BOT_TOKEN"])
        if os.environ.get("DISCORD_BOT_TOKEN"):
            await mgr.start_discord(os.environ["DISCORD_BOT_TOKEN"])
        if os.environ.get("MATRIX_ACCESS_TOKEN"):
            await mgr.start_matrix(
                homeserver=os.environ.get("MATRIX_HOMESERVER", "https://matrix.org"),
                user_id=os.environ.get("MATRIX_USER_ID", ""),
                access_token=os.environ["MATRIX_ACCESS_TOKEN"],
            )
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning("Channel autostart skipped: %s", _e)

    yield
    wm.stop_scheduler()
    try:
        from arix.tools.browser_tools import close_browser
        await close_browser()
    except Exception:
        pass


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Arix", version="9.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Auth middleware ───────────────────────────────────────────────────────────

_ADMIN_TOKEN: str = os.environ.get("Arix_ADMIN_TOKEN", "")
_PUBLIC_PATHS = frozenset({"/", "/favicon.ico", "/webhook/whatsapp"})


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if not _ADMIN_TOKEN:
        return await call_next(request)
    path = request.url.path
    if path in _PUBLIC_PATHS or path.startswith("/static/"):
        return await call_next(request)
    # WebSocket upgrades are authenticated inside their own handler
    if request.headers.get("upgrade", "").lower() == "websocket":
        return await call_next(request)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != _ADMIN_TOKEN:
        return JSONResponse(
            {"error": "Unauthorized — set Authorization: Bearer <Arix_ADMIN_TOKEN>"},
            status_code=401,
        )
    return await call_next(request)


# ── Rate-limit middleware (sliding window per IP) ─────────────────────────────

_rate_buckets: dict[str, collections.deque] = collections.defaultdict(collections.deque)
_RATE_WINDOW = 60.0  # seconds


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else "unknown"
    )


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    try:
        limit = get_agent().config.api_rate_limit_per_minute
    except Exception:
        limit = 0
    if limit <= 0 or request.url.path.startswith("/static/") or request.url.path == "/favicon.ico":
        return await call_next(request)

    ip = _get_client_ip(request)
    now = _time.monotonic()
    bucket = _rate_buckets[ip]

    while bucket and now - bucket[0] > _RATE_WINDOW:
        bucket.popleft()

    if len(bucket) >= limit:
        retry_after = int(_RATE_WINDOW - (now - bucket[0])) + 1
        return JSONResponse(
            {"error": "Rate limit exceeded", "retry_after_seconds": retry_after},
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )

    bucket.append(now)
    return await call_next(request)


# ── Core routes ───────────────────────────────────────────────────────────────

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    ico = Path("static/favicon.ico")
    return FileResponse(str(ico)) if ico.exists() else JSONResponse({}, status_code=204)


@app.get("/", response_class=HTMLResponse)
async def index():
    return Path("templates/index.html").read_text()


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(agent_api.router)
app.include_router(bridge.router)
app.include_router(calendar.router)
app.include_router(canvas.router)
app.include_router(channels.router)
app.include_router(curator.router)
app.include_router(drive.router)
app.include_router(gmail.router)
app.include_router(hands.router)
app.include_router(intelligence.router)
app.include_router(knowledge.router)
app.include_router(mcp.router)
app.include_router(memory.router)
app.include_router(multi_agent.router)
app.include_router(notion.router)
app.include_router(personal.router)
app.include_router(plugins.router)
app.include_router(skillhub.router)
app.include_router(slack.router)
app.include_router(spotify.router)
app.include_router(trello.router)
app.include_router(vision.router)
app.include_router(whatsapp.router)
app.include_router(workflows.router)
app.include_router(ws.router)
app.include_router(youtube.router)
app.include_router(research_mode.router)
app.include_router(marketplace.router)
app.include_router(workspaces.router)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        reload=False,
        log_level="info",
    )
