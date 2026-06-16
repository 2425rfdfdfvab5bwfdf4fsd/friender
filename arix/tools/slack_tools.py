"""Slack tools — wrappers for agent dispatch."""
from __future__ import annotations
from arix.integrations import slack as _slack


async def slack_list_channels(limit: int = 20, dry_run: bool = False) -> dict:
    """List all Slack channels in the workspace."""
    if dry_run:
        return {"dry_run": True, "action": "slack_list_channels"}
    import asyncio
    return await asyncio.to_thread(_slack.list_channels, limit=limit)


async def slack_send_message(channel: str, text: str, thread_ts: str = "", dry_run: bool = False) -> dict:
    """Send a message to a Slack channel or thread."""
    if dry_run:
        return {"dry_run": True, "action": "slack_send_message", "channel": channel, "text": text}
    import asyncio
    return await asyncio.to_thread(_slack.send_message, channel=channel, text=text, thread_ts=thread_ts)


async def slack_get_messages(channel: str, limit: int = 20, dry_run: bool = False) -> dict:
    """Get recent messages from a Slack channel."""
    if dry_run:
        return {"dry_run": True, "action": "slack_get_messages", "channel": channel}
    import asyncio
    return await asyncio.to_thread(_slack.get_messages, channel=channel, limit=limit)


async def slack_search(query: str, count: int = 10, dry_run: bool = False) -> dict:
    """Search Slack messages across all channels."""
    if dry_run:
        return {"dry_run": True, "action": "slack_search", "query": query}
    import asyncio
    return await asyncio.to_thread(_slack.search_messages, query=query, count=count)
