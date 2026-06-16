"""Spotify integration — search tracks, control playback, get current track."""
from __future__ import annotations
import base64
import os
import time
from typing import Any

_cached_token: dict = {"token": "", "expires": 0}


def is_configured() -> bool:
    return bool(
        os.environ.get("SPOTIFY_CLIENT_ID")
        and os.environ.get("SPOTIFY_CLIENT_SECRET")
    )


def _get_client_token() -> str | None:
    """Get a Client Credentials token (for search — doesn't require user auth)."""
    global _cached_token
    if _cached_token["token"] and time.time() < _cached_token["expires"]:
        return _cached_token["token"]
    try:
        import httpx
        cid = os.environ.get("SPOTIFY_CLIENT_ID", "")
        csec = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
        creds = base64.b64encode(f"{cid}:{csec}".encode()).decode()
        resp = httpx.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "client_credentials"},
            headers={"Authorization": f"Basic {creds}"},
            timeout=10,
        )
        if resp.status_code == 200:
            d = resp.json()
            _cached_token = {
                "token": d["access_token"],
                "expires": time.time() + d["expires_in"] - 60,
            }
            return _cached_token["token"]
    except Exception:
        pass
    return None


def _user_token() -> str:
    return os.environ.get("SPOTIFY_ACCESS_TOKEN", "")


def _not_configured_error() -> dict:
    return {
        "ok": False,
        "error": "Spotify not configured. Add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to Secrets.",
    }


def search_tracks(query: str, limit: int = 10) -> dict:
    if not is_configured():
        return _not_configured_error()
    token = _get_client_token()
    if not token:
        return {"ok": False, "error": "Failed to get Spotify token."}
    try:
        import httpx
        resp = httpx.get(
            "https://api.spotify.com/v1/search",
            params={"q": query, "type": "track", "limit": limit},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if resp.status_code != 200:
            return {"ok": False, "error": f"Spotify API {resp.status_code}: {resp.text[:300]}"}
        tracks = []
        for t in resp.json().get("tracks", {}).get("items", []):
            artists = ", ".join(a["name"] for a in t.get("artists", []))
            tracks.append({
                "id": t["id"],
                "name": t["name"],
                "artist": artists,
                "album": t.get("album", {}).get("name", ""),
                "duration_ms": t.get("duration_ms", 0),
                "uri": t.get("uri", ""),
                "preview_url": t.get("preview_url", ""),
                "url": t.get("external_urls", {}).get("spotify", ""),
            })
        return {"ok": True, "tracks": tracks, "count": len(tracks)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_current_track() -> dict:
    token = _user_token()
    if not token:
        return {"ok": False, "error": "SPOTIFY_ACCESS_TOKEN not set. User OAuth required for playback control."}
    try:
        import httpx
        resp = httpx.get(
            "https://api.spotify.com/v1/me/player/currently-playing",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code == 204:
            return {"ok": True, "playing": False, "message": "Nothing currently playing."}
        if resp.status_code != 200:
            return {"ok": False, "error": f"Spotify API {resp.status_code}"}
        d = resp.json()
        item = d.get("item", {})
        artists = ", ".join(a["name"] for a in item.get("artists", []))
        return {
            "ok": True,
            "playing": d.get("is_playing", False),
            "track": item.get("name", ""),
            "artist": artists,
            "album": item.get("album", {}).get("name", ""),
            "progress_ms": d.get("progress_ms", 0),
            "duration_ms": item.get("duration_ms", 0),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def play_pause(play: bool = True) -> dict:
    token = _user_token()
    if not token:
        return {"ok": False, "error": "SPOTIFY_ACCESS_TOKEN not set. User OAuth required for playback control."}
    try:
        import httpx
        endpoint = "play" if play else "pause"
        resp = httpx.put(
            f"https://api.spotify.com/v1/me/player/{endpoint}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code in (200, 204):
            return {"ok": True, "action": endpoint}
        return {"ok": False, "error": f"Playback control failed {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_setup_instructions() -> str:
    return (
        "To connect Spotify (search):\n"
        "1. Go to developer.spotify.com/dashboard → create an app\n"
        "2. Copy Client ID and Client Secret → add as SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET in Secrets\n"
        "For playback control (pause/play/skip), also add SPOTIFY_ACCESS_TOKEN (user OAuth token)"
    )
