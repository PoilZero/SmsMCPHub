from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastmcp import Client

from smsmcphub.domain.models import IncomingMessage
from smsmcphub.mcp.server import create_mcp_server


@pytest.mark.asyncio
async def test_fastmcp_tools_are_discoverable_and_callable(service):
    service.ingest(
        "smsforwarder",
        [
            IncomingMessage(
                sender="10086",
                body="验证码 654321",
                received_at=datetime.now(UTC),
                dedupe_key="mcp-event-1",
            )
        ],
    )
    mcp = create_mcp_server(service)
    assert "verification codes" in mcp.instructions
    tools = await mcp.get_tools()
    assert set(tools) == {
        "sms_search",
        "sms_get",
        "sms_latest",
        "sms_conversations",
    }
    assert all(tool.annotations.readOnlyHint for tool in tools.values())

    async with Client(mcp) as client:
        result = await client.call_tool("sms_search", {"keyword": "654321"})
        assert result.data["messages"][0]["body"] == "验证码 654321"
        assert result.content[0].text == "Found 1 SMS message."
        latest = await client.call_tool("sms_latest", {"keyword": "654321"})
        assert latest.data["found"] is True
        assert latest.content[0].text == "Found the latest matching SMS."
