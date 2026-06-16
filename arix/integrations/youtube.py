"""YouTube integration — search videos, get details, list channel videos."""
from __future__ import annotations
import os
from typing import Any


def is_configured() -> bool:
    return bool(os.environ.get("YOUTUBE_API_KEY"))


def _api_key() -> str:
    return os.environ.get("YOUTUBE_API_KEY", "")


def _not_configured_error() -> dict:
    return {
        "ok": False,
        "error": "YouTube not configured. Add YOUTUBE_API_KEY to Secrets (from console.cloud.google.com → YouTube Data API v3).",
    }


def search_videos(query: str, max_results: int = 10, order: str = "relevance") -> dict:
    if not is_configured():
        return _not_configured_error()
    try:
        import httpx
        resp = httpx.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "q": query,
                "maxResults": max_results,
                "order": order,
                "type": "video",
                "key": _api_key(),
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return {"ok": False, "error": f"YouTube API {resp.status_code}: {resp.text[:300]}"}
        videos = []
        for item in resp.json().get("items", []):
            snip = item.get("snippet", {})
            vid_id = item.get("id", {}).get("videoId", "")
            videos.append({
                "id": vid_id,
                "title": snip.get("title", ""),
                "channel": snip.get("channelTitle", ""),
                "description": snip.get("description", "")[:200],
                "published": snip.get("publishedAt", ""),
                "thumbnail": snip.get("thumbnails", {}).get("medium", {}).get("url", ""),
                "url": f"https://www.youtube.com/watch?v={vid_id}" if vid_id else "",
            })
        return {"ok": True, "videos": videos, "count": len(videos), "query": query}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_video_details(video_id: str) -> dict:
    if not is_configured():
        return _not_configured_error()
    try:
        import httpx
        resp = httpx.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={
                "part": "snippet,statistics,contentDetails",
                "id": video_id,
                "key": _api_key(),
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return {"ok": False, "error": f"YouTube API {resp.status_code}: {resp.text[:300]}"}
        items = resp.json().get("items", [])
        if not items:
            return {"ok": False, "error": "Video not found"}
        item = items[0]
        snip = item.get("snippet", {})
        stats = item.get("statistics", {})
        details = item.get("contentDetails", {})
        return {
            "ok": True,
            "id": video_id,
            "title": snip.get("title", ""),
            "channel": snip.get("channelTitle", ""),
            "description": snip.get("description", "")[:1000],
            "published": snip.get("publishedAt", ""),
            "duration": details.get("duration", ""),
            "views": stats.get("viewCount", ""),
            "likes": stats.get("likeCount", ""),
            "comments": stats.get("commentCount", ""),
            "url": f"https://www.youtube.com/watch?v={video_id}",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def search_channels(query: str, max_results: int = 5) -> dict:
    if not is_configured():
        return _not_configured_error()
    try:
        import httpx
        resp = httpx.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "q": query,
                "maxResults": max_results,
                "type": "channel",
                "key": _api_key(),
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return {"ok": False, "error": f"YouTube API {resp.status_code}: {resp.text[:300]}"}
        channels = []
        for item in resp.json().get("items", []):
            snip = item.get("snippet", {})
            cid = item.get("id", {}).get("channelId", "")
            channels.append({
                "id": cid,
                "name": snip.get("channelTitle", ""),
                "description": snip.get("description", "")[:200],
                "thumbnail": snip.get("thumbnails", {}).get("default", {}).get("url", ""),
                "url": f"https://www.youtube.com/channel/{cid}" if cid else "",
            })
        return {"ok": True, "channels": channels, "count": len(channels)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_setup_instructions() -> str:
    return (
        "To connect YouTube:\n"
        "1. Go to console.cloud.google.com → enable 'YouTube Data API v3'\n"
        "2. Create an API key under Credentials\n"
        "3. Add YOUTUBE_API_KEY to Secrets"
    )
