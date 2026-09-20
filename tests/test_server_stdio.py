"""In-memory client tests plus real stdio integration tests for the server."""

from __future__ import annotations

import sys

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

import laya_mcp.server as server
from conftest import FakeAgent

EXPECTED_TOOLS = {
    "laya_decide",
    "laya_triage",
    "laya_guard",
    "laya_moderate",
    "laya_email",
}

TRIAGE_MESSAGE = "I was charged twice this month and need a refund today or I am cancelling my account."


async def test_list_tools_in_memory() -> None:
    async with Client(server.mcp) as client:
        tools = await client.list_tools()

    assert {tool.name for tool in tools} == EXPECTED_TOOLS


async def test_call_tool_in_memory_uses_fake_agent(fake_agent: FakeAgent) -> None:
    async with Client(server.mcp) as client:
        result = await client.call_tool("laya_triage", {"message": TRIAGE_MESSAGE})

    assert fake_agent.calls[0]["state"] == {"message": TRIAGE_MESSAGE}
    assert result.data == fake_agent.result


async def test_call_decide_in_memory_roundtrips_typed_args(fake_agent: FakeAgent) -> None:
    """laya_decide's dict-typed state and questions survive MCP schema validation."""
    state = {"ticket": "the server is down"}
    questions = {
        "escalate": {
            "type": "noul",
            "instructions": "Should `ticket` be escalated?",
        }
    }

    async with Client(server.mcp) as client:
        result = await client.call_tool("laya_decide", {"state": state, "questions": questions})

    assert fake_agent.calls[0] == {"state": state, "questions": questions}
    assert result.data == fake_agent.result


@pytest.mark.integration
async def test_stdio_server_lists_tools_and_answers() -> None:
    transport = StdioTransport(command=sys.executable, args=["-m", "laya_mcp.server"])

    async with Client(transport) as client:
        tools = await client.list_tools()
        assert {tool.name for tool in tools} == EXPECTED_TOOLS

        result = await client.call_tool("laya_triage", {"message": TRIAGE_MESSAGE})
        answers = result.data["answers"]
        assert set(answers) == {
            "intent",
            "is_urgent",
            "frustration",
            "refund_requested",
            "churn_risk",
        }
        assert result.data["usage"]["output_tokens"] == 0
