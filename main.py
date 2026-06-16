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
    drive,
    gmail,
    intelligence,
    memory,
    notion,
    personal,
    plugins,
    slack,
    spotify,
    trello,
    whatsapp,
    workflows,
    ws,
    youtube,
)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app_: FastAPI):
    wm = WorkflowManager()
    wm.start_scheduler()
    set_workflow_manager(wm)
    yield
    wm.stop_scheduler()
    try:
        from arix.tools.browser_tools import close_browser
        await close_browser()
    except Exception:
        pass


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Arix", version="8.0.0", lifespan=lifespan)
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
    limit = get_agent().config.api_rate_limit_per_minute
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
app.include_router(drive.router)
app.include_router(gmail.router)
app.include_router(intelligence.router)
app.include_router(memory.router)
app.include_router(notion.router)
app.include_router(personal.router)
app.include_router(plugins.router)
app.include_router(slack.router)
app.include_router(spotify.router)
app.include_router(trello.router)
app.include_router(whatsapp.router)
app.include_router(workflows.router)
app.include_router(ws.router)
app.include_router(youtube.router)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        reload=False,
        log_level="info",
    )
