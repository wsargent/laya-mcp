"""In-memory client tests plus real stdio integration tests for the server."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

import laya_mcp.server as server

EXPECTED_TOOLS = {
    "laya_decide",
    "laya_triage",
    "laya_guard",
    "laya_moderate",
    "laya_email",
}

TRIAGE_MESSAGE = (
    "I was charged twice this month and need a refund today "
    "or I am cancelling my account."
)


async def test_list_tools_in_memory() -> None:
    async with Client(server.mcp) as client:
        tools = await client.list_tools()

    assert {tool.name for tool in tools} == EXPECTED_TOOLS


async def test_call_tool_in_memory_uses_fake_agent(fake_agent) -> None:  # type: ignore[no-untyped-def]
    async with Client(server.mcp) as client:
        result = await client.call_tool("laya_triage", {"message": TRIAGE_MESSAGE})

    assert fake_agent.calls[0]["state"] == {"message": TRIAGE_MESSAGE}
    assert result.data == fake_agent.result


@pytest.mark.integration
async def test_stdio_server_lists_tools_and_answers() -> None:
    python = str(Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python")
    transport = StdioTransport(command=python, args=["-m", "laya_mcp.server"])

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
