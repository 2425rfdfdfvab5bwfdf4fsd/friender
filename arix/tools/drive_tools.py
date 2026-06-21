"""Google Drive tools — wrappers around arix.integrations.google_drive for agent dispatch."""
from __future__ import annotations
from arix.integrations import google_drive as _drive


async def drive_list_files(
    folder_id: str = "root",
    max_results: int = 20,
    dry_run: bool = False,
) -> dict:
    """List files and folders in a Google Drive folder (default: root)."""
    if not _drive.is_configured():
        return {"ok": False, "error": "Google Drive is not connected. Add credentials in the Drive panel."}
    if dry_run:
        return {"dry_run": True, "action": "drive_list_files", "folder_id": folder_id}
    import asyncio
    return await asyncio.to_thread(_drive.list_files, folder_id=folder_id, max_results=max_results)


async def drive_search_files(query: str, max_results: int = 20, dry_run: bool = False) -> dict:
    """Search for files in Google Drive by name."""
    if not _drive.is_configured():
        return {"ok": False, "error": "Google Drive is not connected. Add credentials in the Drive panel."}
    if dry_run:
        return {"dry_run": True, "action": "drive_search_files", "query": query}
    import asyncio
    return await asyncio.to_thread(_drive.search_files, query=query, max_results=max_results)


async def drive_read_file(file_id: str, max_chars: int = 8000, dry_run: bool = False) -> dict:
    """Read the text content of a Google Drive file (Docs, Sheets, plain text, etc.)."""
    if not _drive.is_configured():
        return {"ok": False, "error": "Google Drive is not connected. Add credentials in the Drive panel."}
    if dry_run:
        return {"dry_run": True, "action": "drive_read_file", "file_id": file_id}
    import asyncio
    return await asyncio.to_thread(_drive.read_file, file_id=file_id, max_chars=max_chars)


async def drive_upload_file(
    local_path: str,
    parent_folder_id: str = "root",
    new_name: str = "",
    dry_run: bool = False,
) -> dict:
    """Upload a local file to Google Drive."""
    if not _drive.is_configured():
        return {"ok": False, "error": "Google Drive is not connected. Add credentials in the Drive panel."}
    if dry_run:
        return {"dry_run": True, "action": "drive_upload_file", "local_path": local_path}
    import asyncio
    return await asyncio.to_thread(
        _drive.upload_file,
        local_path=local_path,
        parent_folder_id=parent_folder_id,
        new_name=new_name,
    )
