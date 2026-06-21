"""Google Drive integration — list, read, upload, search files via Drive API."""
from __future__ import annotations
import base64
import json
import os
from pathlib import Path
from typing import Any


def is_configured() -> bool:
    return bool(
        os.environ.get("GOOGLE_DRIVE_CLIENT_ID")
        and os.environ.get("GOOGLE_DRIVE_CLIENT_SECRET")
        and os.environ.get("GOOGLE_DRIVE_REFRESH_TOKEN")
    )


def _get_access_token() -> str | None:
    try:
        import httpx
        resp = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": os.environ["GOOGLE_DRIVE_CLIENT_ID"],
                "client_secret": os.environ["GOOGLE_DRIVE_CLIENT_SECRET"],
                "refresh_token": os.environ["GOOGLE_DRIVE_REFRESH_TOKEN"],
                "grant_type": "refresh_token",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("access_token")
        else:
            import logging
            logging.getLogger(__name__).warning("Drive token refresh failed: %d %s", resp.status_code, resp.text)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Drive token refresh exception: %s", e)
    return None


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _not_configured_error() -> dict:
    return {
        "ok": False,
        "error": (
            "Google Drive not configured. Add GOOGLE_DRIVE_CLIENT_ID, "
            "GOOGLE_DRIVE_CLIENT_SECRET, GOOGLE_DRIVE_REFRESH_TOKEN to Secrets."
        ),
    }


def list_files(folder_id: str = "root", max_results: int = 20, page_token: str = "") -> dict:
    if not is_configured():
        return _not_configured_error()
    token = _get_access_token()
    if not token:
        return {"ok": False, "error": "Failed to get Drive access token."}
    try:
        import httpx
        params: dict[str, Any] = {
            "q": f"'{folder_id}' in parents and trashed=false",
            "pageSize": max_results,
            "fields": "nextPageToken,files(id,name,mimeType,size,modifiedTime,webViewLink,parents)",
            "orderBy": "modifiedTime desc",
        }
        if page_token:
            params["pageToken"] = page_token
        resp = httpx.get(
            "https://www.googleapis.com/drive/v3/files",
            params=params,
            headers=_headers(token),
            timeout=15,
        )
        if resp.status_code != 200:
            return {"ok": False, "error": f"Drive API error {resp.status_code}: {resp.text[:300]}"}
        data = resp.json()
        files = []
        for f in data.get("files", []):
            size_bytes = int(f.get("size", 0)) if f.get("size") else 0
            files.append({
                "id": f["id"],
                "name": f["name"],
                "type": f.get("mimeType", ""),
                "size_kb": round(size_bytes / 1024, 1) if size_bytes else 0,
                "modified": f.get("modifiedTime", ""),
                "url": f.get("webViewLink", ""),
                "is_folder": f.get("mimeType") == "application/vnd.google-apps.folder",
            })
        return {
            "ok": True,
            "files": files,
            "count": len(files),
            "next_page_token": data.get("nextPageToken", ""),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def search_files(query: str, max_results: int = 20) -> dict:
    if not is_configured():
        return _not_configured_error()
    token = _get_access_token()
    if not token:
        return {"ok": False, "error": "Failed to get Drive access token."}
    try:
        import httpx
        escaped = query.replace("'", "\\'")
        params: dict[str, Any] = {
            "q": f"name contains '{escaped}' and trashed=false",
            "pageSize": max_results,
            "fields": "files(id,name,mimeType,size,modifiedTime,webViewLink)",
        }
        resp = httpx.get(
            "https://www.googleapis.com/drive/v3/files",
            params=params,
            headers=_headers(token),
            timeout=15,
        )
        if resp.status_code != 200:
            return {"ok": False, "error": f"Drive API error {resp.status_code}: {resp.text[:300]}"}
        data = resp.json()
        files = []
        for f in data.get("files", []):
            size_bytes = int(f.get("size", 0)) if f.get("size") else 0
            files.append({
                "id": f["id"],
                "name": f["name"],
                "type": f.get("mimeType", ""),
                "size_kb": round(size_bytes / 1024, 1) if size_bytes else 0,
                "modified": f.get("modifiedTime", ""),
                "url": f.get("webViewLink", ""),
            })
        return {"ok": True, "files": files, "count": len(files), "query": query}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def read_file(file_id: str, max_chars: int = 8000) -> dict:
    if not is_configured():
        return _not_configured_error()
    token = _get_access_token()
    if not token:
        return {"ok": False, "error": "Failed to get Drive access token."}
    try:
        import httpx
        meta_resp = httpx.get(
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            params={"fields": "id,name,mimeType,size"},
            headers=_headers(token),
            timeout=10,
        )
        if meta_resp.status_code != 200:
            return {"ok": False, "error": f"File not found: {meta_resp.status_code}"}
        meta = meta_resp.json()
        mime = meta.get("mimeType", "")

        google_export_map = {
            "application/vnd.google-apps.document": "text/plain",
            "application/vnd.google-apps.spreadsheet": "text/csv",
            "application/vnd.google-apps.presentation": "text/plain",
        }
        if mime in google_export_map:
            export_mime = google_export_map[mime]
            dl_resp = httpx.get(
                f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
                params={"mimeType": export_mime},
                headers=_headers(token),
                timeout=30,
            )
        else:
            dl_resp = httpx.get(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                params={"alt": "media"},
                headers=_headers(token),
                timeout=30,
            )

        if dl_resp.status_code != 200:
            return {"ok": False, "error": f"Download failed {dl_resp.status_code}: {dl_resp.text[:200]}"}

        content = dl_resp.text[:max_chars]
        truncated = len(dl_resp.text) > max_chars
        return {
            "ok": True,
            "id": file_id,
            "name": meta.get("name", ""),
            "mime_type": mime,
            "content": content,
            "truncated": truncated,
            "chars_read": len(content),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def upload_file(local_path: str, parent_folder_id: str = "root", new_name: str = "") -> dict:
    if not is_configured():
        return _not_configured_error()
    token = _get_access_token()
    if not token:
        return {"ok": False, "error": "Failed to get Drive access token."}
    p = Path(local_path).expanduser().resolve()
    if not p.exists():
        return {"ok": False, "error": f"Local file not found: {p}"}
    try:
        import httpx
        import mimetypes
        fname = new_name or p.name
        mime_type = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
        metadata = json.dumps({"name": fname, "parents": [parent_folder_id]})
        content = p.read_bytes()
        boundary = "==boundary=="
        body = (
            f"--{boundary}\r\n"
            f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{metadata}\r\n"
            f"--{boundary}\r\n"
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--".encode()
        resp = httpx.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
            content=body,
            headers={
                **_headers(token),
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
            timeout=60,
        )
        if resp.status_code in (200, 201):
            d = resp.json()
            return {"ok": True, "id": d.get("id"), "name": d.get("name"), "uploaded": str(p)}
        return {"ok": False, "error": f"Upload failed {resp.status_code}: {resp.text[:300]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_setup_instructions() -> str:
    return (
        "To connect Google Drive:\n"
        "1. Go to console.cloud.google.com → create OAuth2 credentials\n"
        "2. Add Drive API scope: https://www.googleapis.com/auth/drive\n"
        "3. Set environment secrets: GOOGLE_DRIVE_CLIENT_ID, GOOGLE_DRIVE_CLIENT_SECRET, "
        "GOOGLE_DRIVE_REFRESH_TOKEN\n"
        "   (use OAuth Playground at developers.google.com/oauthplayground to get refresh token)"
    )
