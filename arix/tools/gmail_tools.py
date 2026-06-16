"""Gmail tools — wrappers around arix.integrations.gmail for agent dispatch."""
from __future__ import annotations
from arix.integrations import gmail as _gmail


async def gmail_list_emails(
    max_results: int = 10,
    label: str = "INBOX",
    query: str = "",
    dry_run: bool = False,
) -> dict:
    """List emails from Gmail inbox (or any label/query)."""
    if dry_run:
        return {"dry_run": True, "action": "gmail_list_emails", "label": label, "max_results": max_results}
    import asyncio
    return await asyncio.to_thread(_gmail.list_emails, max_results=max_results, label_ids=label, query=query)


async def gmail_read_email(message_id: str, dry_run: bool = False) -> dict:
    """Read the full body of a Gmail message by ID."""
    if dry_run:
        return {"dry_run": True, "action": "gmail_read_email", "message_id": message_id}
    import asyncio
    return await asyncio.to_thread(_gmail.read_email, message_id=message_id)


async def gmail_send_email(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    html: bool = False,
    dry_run: bool = False,
) -> dict:
    """Send an email via Gmail."""
    if dry_run:
        return {"dry_run": True, "action": "gmail_send_email", "to": to, "subject": subject}
    import asyncio
    return await asyncio.to_thread(_gmail.send_email, to=to, subject=subject, body=body, cc=cc, html=html)


async def gmail_search_emails(query: str, max_results: int = 10, dry_run: bool = False) -> dict:
    """Search Gmail using Gmail query syntax (e.g. 'from:boss@co.com is:unread')."""
    if dry_run:
        return {"dry_run": True, "action": "gmail_search_emails", "query": query}
    import asyncio
    return await asyncio.to_thread(_gmail.search_emails, query=query, max_results=max_results)


async def gmail_delete_email(message_id: str, dry_run: bool = False) -> dict:
    """Permanently delete a Gmail message by ID."""
    if dry_run:
        return {"dry_run": True, "action": "gmail_delete_email", "message_id": message_id}
    import asyncio
    return await asyncio.to_thread(_gmail.delete_email, message_id=message_id)
