"""Google Drive routes — /api/drive/*"""
from __future__ import annotations
import asyncio
from fastapi import APIRouter, HTTPException
from arix.integrations import google_drive as _drive

router = APIRouter(prefix="/api/drive", tags=["drive"])


@router.get("/status")
async def drive_status():
    configured = _drive.is_configured()
    return {
        "configured": configured,
        "setup_instructions": "" if configured else _drive.get_setup_instructions(),
    }


@router.get("/files")
async def list_files(folder_id: str = "root", max_results: int = 20):
    return await asyncio.to_thread(_drive.list_files, folder_id=folder_id, max_results=max_results)


@router.get("/search")
async def search_files(q: str = "", max_results: int = 20):
    if not q:
        raise HTTPException(status_code=400, detail="q (query) parameter is required")
    return await asyncio.to_thread(_drive.search_files, query=q, max_results=max_results)


@router.get("/files/{file_id}")
async def read_file(file_id: str, max_chars: int = 8000):
    return await asyncio.to_thread(_drive.read_file, file_id=file_id, max_chars=max_chars)


@router.post("/upload")
async def upload_file(body: dict):
    local_path = body.get("local_path", "").strip()
    if not local_path:
        raise HTTPException(status_code=400, detail="local_path is required")
    return await asyncio.to_thread(
        _drive.upload_file,
        local_path=local_path,
        parent_folder_id=body.get("parent_folder_id", "root"),
        new_name=body.get("new_name", ""),
    )
