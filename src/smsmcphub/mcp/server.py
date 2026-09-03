from __future__ import annotations

from datetime import datetime

from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult

from smsmcphub.domain.models import (
    ConversationQuery,
    MessageQuery,
    MessageStatus,
)
from smsmcphub.domain.service import MessageService


def create_mcp_server(service: MessageService) -> FastMCP:
    mcp = FastMCP("SmsMCPHub")

    @mcp.tool
    def sms_search(
        sender: str | None = None,
        recipient: str | None = None,
        keyword: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        status: MessageStatus | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> ToolResult:
        """Search received SMS messages by sender, text, status, or time range."""
        query = MessageQuery(
            sender=sender,
            recipient=recipient,
            keyword=keyword,
            since=since,
            until=until,
            status=status,
            limit=limit,
            cursor=cursor,
        )
        result = service.search(query)
        data = {
            "messages": [_message_summary(message) for message in result.messages],
            "next_cursor": result.next_cursor,
        }
        count = len(result.messages)
        summary = f"Found {count} SMS message{'s' if count != 1 else ''}."
        return ToolResult(content=summary, structured_content=data)

    @mcp.tool
    def sms_get(message_id: str) -> ToolResult:
        """Get one SMS message by its SmsMCPHub ID."""
        message = service.get(message_id)
        if message is None:
            return ToolResult(
                content="SMS message not found.",
                structured_content={"found": False, "message": None},
            )
        return ToolResult(
            content=f"Found SMS message {message.id}.",
            structured_content={"found": True, "message": message.model_dump(mode="json")},
        )

    @mcp.tool
    def sms_latest(
        sender: str | None = None,
        keyword: str | None = None,
        within_minutes: int = 10,
    ) -> ToolResult:
        """Return the newest matching SMS within the requested time window."""
        result = service.latest(sender=sender, keyword=keyword, within_minutes=within_minutes)
        data = {
            "found": result.found,
            "message": _message_summary(result.message) if result.message else None,
        }
        summary = "Found the latest matching SMS." if result.found else "No matching SMS found."
        return ToolResult(content=summary, structured_content=data)

    @mcp.tool
    def sms_conversations(limit: int = 20, cursor: str | None = None) -> ToolResult:
        """List SMS conversations ordered by their latest message."""
        result = service.conversations(ConversationQuery(limit=limit, cursor=cursor))
        data = result.model_dump(mode="json")
        count = len(result.conversations)
        summary = f"Found {count} SMS conversation{'s' if count != 1 else ''}."
        return ToolResult(content=summary, structured_content=data)

    return mcp


def _message_summary(message) -> dict[str, str | None]:
    return {
        "id": message.id,
        "sender": message.sender,
        "recipient": message.recipient,
        "body": message.body,
        "received_at": message.received_at.isoformat().replace("+00:00", "Z"),
        "source": message.source,
        "status": message.status.value,
    }
