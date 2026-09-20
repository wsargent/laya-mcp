"""Shared fixtures: a fake agent so tests never load the real MLX model."""

from __future__ import annotations

from typing import Any

import pytest

import laya_mcp.server as server


class FakeAgent:
    """Records predict calls and returns a canned result."""

    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result = result or {
            "model": "laya-rl-agent",
            "answers": {
                "demo": {
                    "type": "noul",
                    "confidence": 0.9,
                    "action": {"act_probability": 1.0},
                    "noul": 0.9,
                }
            },
            "usage": {"input_tokens": 42, "output_tokens": 0},
        }

    def predict(self, state: Any, questions: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"state": state, "questions": questions})
        return self.result


@pytest.fixture
def fake_agent(monkeypatch: pytest.MonkeyPatch) -> FakeAgent:
    """Patch the server so every tool call routes to a FakeAgent."""
    agent = FakeAgent()
    # Ambient daemon forwarding would bypass the fake; scrub it so tests
    # exercise the local path whatever the developer's environment exports.
    monkeypatch.delenv("LAYA_DAEMON_URL", raising=False)
    # _predict routes through _get_agent(); patching the _agent cache too keeps
    # any direct cache readers (the daemon routes) consistent with the fake.
    monkeypatch.setattr(server, "_get_agent", lambda: agent)
    monkeypatch.setattr(server, "_agent", agent)
    return agent
