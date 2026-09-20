"""Unit tests for the daemon HTTP surface and the server's daemon fallback."""

# White-box tests: they exercise the server's private agent/lock state.
# pyright: reportPrivateUsage=false
from __future__ import annotations

from typing import Any

import pytest
from laya_mlx import triage_questions
from starlette.testclient import TestClient

import laya_mcp.server as server
from conftest import FakeAgent

VALID_QUESTIONS = {"q": {"type": "noul", "instructions": "Is `state` about X?"}}


@pytest.fixture
def daemon_client(fake_agent: FakeAgent) -> Any:
    """TestClient against the daemon HTTP surface with a FakeAgent installed."""
    # Importing laya_mcp.daemon attaches the routes to the shared server app.
    import laya_mcp.daemon  # noqa: F401  # pyright: ignore[reportUnusedImport] — side-effect import

    app = server.mcp.http_app()
    client = TestClient(app)
    yield client, fake_agent


def test_health_ok_when_loaded(daemon_client: Any) -> None:
    client, _ = daemon_client
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["model"] == server.MODEL_ID


def test_health_starting_when_model_not_loaded(daemon_client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = daemon_client
    monkeypatch.setattr(server, "_agent", None)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "starting"


def test_predict_passes_state_and_questions_through(daemon_client: Any) -> None:
    client, agent = daemon_client
    state = {"command": "rm -rf /tmp/laya-gate-test"}
    response = client.post("/predict", json={"state": state, "questions": VALID_QUESTIONS})
    assert response.status_code == 200
    assert response.json() == agent.result
    assert agent.calls == [{"state": state, "questions": VALID_QUESTIONS}]


def test_predict_accepts_string_state(daemon_client: Any) -> None:
    client, agent = daemon_client
    response = client.post("/predict", json={"state": "plain text", "questions": VALID_QUESTIONS})
    assert response.status_code == 200
    assert agent.calls[0]["state"] == "plain text"


def test_predict_holds_inference_lock(daemon_client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    client, agent = daemon_client
    original_result = agent.result

    def assert_locked(state: Any, questions: dict[str, Any]) -> dict[str, Any]:
        assert server._inference_lock.locked(), "predict ran without the lock"
        agent.calls.append({"state": state, "questions": questions})
        return original_result

    monkeypatch.setattr(agent, "predict", assert_locked)
    response = client.post("/predict", json={"state": "x", "questions": VALID_QUESTIONS})
    assert response.status_code == 200
    assert len(agent.calls) == 1


def test_predict_503_when_model_not_loaded(daemon_client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = daemon_client
    monkeypatch.setattr(server, "_agent", None)
    response = client.post("/predict", json={"state": "x", "questions": VALID_QUESTIONS})
    assert response.status_code == 503


def test_predict_rejects_bad_bodies(daemon_client: Any) -> None:
    client, _ = daemon_client
    # invalid JSON
    response = client.post("/predict", content=b"not json", headers={"content-type": "application/json"})
    assert response.status_code == 400
    # missing state
    assert client.post("/predict", json={"questions": VALID_QUESTIONS}).status_code == 400
    # questions missing / empty / not an object
    assert client.post("/predict", json={"state": "x"}).status_code == 400
    assert client.post("/predict", json={"state": "x", "questions": {}}).status_code == 400
    assert client.post("/predict", json={"state": "x", "questions": ["q"]}).status_code == 400


# ---------------------------------------------------------------------------
# server.py daemon-first fallback
# ---------------------------------------------------------------------------


def test_daemon_url_env_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LAYA_DAEMON_URL", raising=False)
    assert server._daemon_url() is None
    monkeypatch.setenv("LAYA_DAEMON_URL", "   ")
    assert server._daemon_url() is None
    monkeypatch.setenv("LAYA_DAEMON_URL", "http://127.0.0.1:8742")
    assert server._daemon_url() == "http://127.0.0.1:8742"


def test_predict_uses_daemon_when_available(fake_agent: FakeAgent, monkeypatch: pytest.MonkeyPatch) -> None:
    canned = {
        "model": "laya-daemon",
        "answers": {"demo": {"type": "noul", "noul": 0.1}},
        "usage": {"input_tokens": 1, "output_tokens": 0},
    }
    seen: dict[str, Any] = {}

    def fake_post(url: str, state: Any, questions: dict[str, Any]) -> dict[str, Any]:
        seen.update(url=url, state=state, questions=questions)
        return canned

    monkeypatch.setenv("LAYA_DAEMON_URL", "http://daemon.test:1234/")
    monkeypatch.setattr(server, "_predict_via_daemon", fake_post)

    result = server.laya_triage("hello")

    assert result is canned
    assert seen["url"] == "http://daemon.test:1234/"
    assert seen["state"] == {"message": "hello"}
    assert fake_agent.calls == []


def test_predict_falls_back_when_daemon_errors(fake_agent: FakeAgent, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url: str, state: Any, questions: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("daemon on fire")

    monkeypatch.setenv("LAYA_DAEMON_URL", "http://127.0.0.1:8742")
    monkeypatch.setattr(server, "_predict_via_daemon", boom)

    result = server.laya_triage("hello")

    assert result is fake_agent.result
    assert len(fake_agent.calls) == 1


def test_predict_falls_back_to_local_when_daemon_unreachable(
    fake_agent: FakeAgent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A set URL with nothing listening must degrade to the local agent."""
    monkeypatch.setenv("LAYA_DAEMON_URL", "http://127.0.0.1:9")  # nothing listens

    result = server.laya_triage("hello")

    assert result is fake_agent.result
    assert len(fake_agent.calls) == 1


def test_primed_process_never_forwards(monkeypatch: pytest.MonkeyPatch) -> None:
    """A primed process (the daemon) owns its model: ambient forwarding env is ignored.

    This pins the /mcp surface, not just the main() entrypoint: even when the
    shared app is served without daemon.main(), a primed process must route
    inference locally no matter what LAYA_DAEMON_URL says.
    """
    agent = FakeAgent()
    monkeypatch.setenv("LAYA_DAEMON_URL", "http://127.0.0.1:9")

    def must_not_forward(url: str, state: Any, questions: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("primed process attempted to forward inference")

    monkeypatch.setattr(server, "_predict_via_daemon", must_not_forward)

    server._prime_agent(agent)
    try:
        result = server.laya_triage("hello")
    finally:
        server._daemon_owned = False
        server._agent = None

    assert result is agent.result
    assert agent.calls == [{"state": {"message": "hello"}, "questions": triage_questions()}]
