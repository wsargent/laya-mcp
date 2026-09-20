"""Tests for the Code Mode transform wiring (LAYA_MCP_CODE_MODE)."""

from __future__ import annotations

import sys

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

import laya_mcp.server as server

EXECUTE_FANOUT = '''
r = await call_tool("laya_triage", {"message": "I was charged twice, refund me today"})
return {"intent": r["answers"]["intent"]["choice"]}
'''


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("true", True),
        ("YES", True),
        (" on ", True),
        ("", False),
        ("0", False),
        ("no", False),
        ("off", False),
    ],
)
def test_env_flag_parsing(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: bool
) -> None:
    monkeypatch.setenv("LAYA_TEST_FLAG", value)
    assert server._env_flag("LAYA_TEST_FLAG") is expected


def test_env_flag_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LAYA_TEST_FLAG", raising=False)
    assert server._env_flag("LAYA_TEST_FLAG") is False


@pytest.mark.integration
async def test_stdio_code_mode_swaps_surface() -> None:
    """With the flag on, the laya_* tools are replaced by Code Mode meta-tools."""
    transport = StdioTransport(
        sys.executable,
        ["-m", "laya_mcp.server"],
        env={"LAYA_MCP_CODE_MODE": "1"},
    )

    async with Client(transport) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools}

        assert not any(name.startswith("laya_") for name in names)
        assert {"search", "get_schema", "execute"} <= names

        result = await client.call_tool("execute", {"code": EXECUTE_FANOUT})
        assert result.data == {"intent": "refund"}


@pytest.mark.integration
async def test_stdio_default_surface_unchanged() -> None:
    """Without the flag, the five laya tools are still exposed directly."""
    transport = StdioTransport(sys.executable, ["-m", "laya_mcp.server"])

    async with Client(transport) as client:
        tools = await client.list_tools()

    names = {tool.name for tool in tools}
    assert names == {
        "laya_decide",
        "laya_triage",
        "laya_guard",
        "laya_moderate",
        "laya_email",
    }
    assert "execute" not in names
