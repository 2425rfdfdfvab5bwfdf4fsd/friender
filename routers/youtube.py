"""YouTube router — REST endpoints for the YouTube sidebar panel."""
from __future__ import annotations
from fastapi import APIRouter
from arix.integrations import youtube as _youtube

router = APIRouter(prefix="/api/youtube", tags=["youtube"])


@router.get("/status")
def youtube_status():
    return {"configured": _youtube.is_configured(), "setup": _youtube.get_setup_instructions()}


@router.get("/search")
def youtube_search(q: str, max_results: int = 10):
    return _youtube.search_videos(query=q, max_results=max_results)


@router.get("/video/{video_id}")
def youtube_video(video_id: str):
    return _youtube.get_video_details(video_id=video_id)


@router.get("/channels")
def youtube_channels(q: str, max_results: int = 5):
    return _youtube.search_channels(query=q, max_results=max_results)
