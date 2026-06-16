"""Notion integration — search pages, read blocks, create pages via Notion API."""
from __future__ import annotations
import os
from typing import Any


def is_configured() -> bool:
    return bool(os.environ.get("NOTION_API_KEY") or os.environ.get("NOTION_TOKEN"))


def _api_key() -> str:
    return os.environ.get("NOTION_API_KEY") or os.environ.get("NOTION_TOKEN") or ""


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def _not_configured_error() -> dict:
    return {
        "ok": False,
        "error": "Notion not configured. Add NOTION_API_KEY to Secrets (get it from notion.so/my-integrations).",
    }


def search_pages(query: str = "", max_results: int = 10) -> dict:
    if not is_configured():
        return _not_configured_error()
    try:
        import httpx
        payload: dict[str, Any] = {"page_size": max_results}
        if query:
            payload["query"] = query
        resp = httpx.post(
            "https://api.notion.com/v1/search",
            json=payload,
            headers=_headers(),
            timeout=15,
        )
        if resp.status_code != 200:
            return {"ok": False, "error": f"Notion API {resp.status_code}: {resp.text[:300]}"}
        data = resp.json()
        results = []
        for item in data.get("results", []):
            obj_type = item.get("object", "")
            title = ""
            if obj_type == "page":
                props = item.get("properties", {})
                for k, v in props.items():
                    if v.get("type") == "title":
                        parts = v.get("title", [])
                        title = "".join(p.get("plain_text", "") for p in parts)
                        break
                if not title:
                    title = item.get("url", "Untitled")
            elif obj_type == "database":
                title_list = item.get("title", [])
                title = "".join(t.get("plain_text", "") for t in title_list) or "Untitled Database"
            results.append({
                "id": item["id"],
                "type": obj_type,
                "title": title or "Untitled",
                "url": item.get("url", ""),
                "created": item.get("created_time", ""),
                "edited": item.get("last_edited_time", ""),
            })
        return {"ok": True, "results": results, "count": len(results)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def read_page(page_id: str) -> dict:
    if not is_configured():
        return _not_configured_error()
    try:
        import httpx
        page_resp = httpx.get(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=_headers(),
            timeout=10,
        )
        if page_resp.status_code != 200:
            return {"ok": False, "error": f"Page fetch failed {page_resp.status_code}"}

        blocks_resp = httpx.get(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            params={"page_size": 50},
            headers=_headers(),
            timeout=15,
        )
        page_data = page_resp.json()
        props = page_data.get("properties", {})
        title = ""
        for k, v in props.items():
            if v.get("type") == "title":
                title = "".join(p.get("plain_text", "") for p in v.get("title", []))
                break

        content_lines = []
        if blocks_resp.status_code == 200:
            for block in blocks_resp.json().get("results", []):
                btype = block.get("type", "")
                bdata = block.get(btype, {})
                rich = bdata.get("rich_text", [])
                text = "".join(r.get("plain_text", "") for r in rich)
                if text:
                    prefix = {"heading_1": "# ", "heading_2": "## ", "heading_3": "### ",
                              "bulleted_list_item": "• ", "numbered_list_item": "1. ",
                              "to_do": "[ ] ", "quote": "> ", "code": "```\n"}.get(btype, "")
                    suffix = "\n```" if btype == "code" else ""
                    content_lines.append(f"{prefix}{text}{suffix}")

        return {
            "ok": True,
            "id": page_id,
            "title": title or "Untitled",
            "url": page_data.get("url", ""),
            "content": "\n".join(content_lines)[:6000],
            "created": page_data.get("created_time", ""),
            "edited": page_data.get("last_edited_time", ""),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def create_page(title: str, content: str = "", parent_page_id: str = "") -> dict:
    if not is_configured():
        return _not_configured_error()
    try:
        import httpx
        parent: dict[str, Any]
        if parent_page_id:
            parent = {"type": "page_id", "page_id": parent_page_id}
        else:
            parent = {"type": "workspace", "workspace": True}

        children = []
        for line in content.split("\n"):
            if not line.strip():
                continue
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": line[:2000]}}]},
            })

        payload = {
            "parent": parent,
            "properties": {
                "title": {"title": [{"type": "text", "text": {"content": title}}]},
            },
            "children": children[:100],
        }
        resp = httpx.post(
            "https://api.notion.com/v1/pages",
            json=payload,
            headers=_headers(),
            timeout=15,
        )
        if resp.status_code in (200, 201):
            d = resp.json()
            return {"ok": True, "id": d["id"], "url": d.get("url", ""), "title": title}
        return {"ok": False, "error": f"Notion create failed {resp.status_code}: {resp.text[:300]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def append_to_page(page_id: str, content: str) -> dict:
    if not is_configured():
        return _not_configured_error()
    try:
        import httpx
        children = []
        for line in content.split("\n"):
            if not line.strip():
                continue
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": line[:2000]}}]},
            })
        resp = httpx.patch(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            json={"children": children[:100]},
            headers=_headers(),
            timeout=15,
        )
        if resp.status_code == 200:
            return {"ok": True, "page_id": page_id, "blocks_added": len(children)}
        return {"ok": False, "error": f"Append failed {resp.status_code}: {resp.text[:300]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_setup_instructions() -> str:
    return (
        "To connect Notion:\n"
        "1. Go to notion.so/my-integrations → create a new integration\n"
        "2. Copy the 'Internal Integration Token'\n"
        "3. Add NOTION_API_KEY to Secrets\n"
        "4. Share each Notion page/database with your integration in Notion"
    )
