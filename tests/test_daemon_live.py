"""Integration tests: the real daemon process, real model, HTTP + CLI."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from typing import Any

import httpx
import pytest
from click.testing import CliRunner
from laya_mlx import triage_questions

import laya_mcp.cli as cli_mod

EXPECTED_TRIAGE_ANSWERS = {
    "intent",
    "is_urgent",
    "frustration",
    "refund_requested",
    "churn_risk",
}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def live_daemon() -> Any:
    """Spawn laya_mcp.daemon on a free port; yield its base URL."""
    port = _free_port()
    env = {**os.environ, "LAYA_DAEMON_PORT": str(port)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "laya_mcp.daemon"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 90  # model load on first run
    try:
        while True:
            try:
                if httpx.get(f"{base}/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            assert proc.poll() is None, "daemon exited during startup"
            assert time.monotonic() < deadline, "daemon never became healthy"
            time.sleep(0.5)
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.mark.integration
def test_predict_endpoint_answers(live_daemon: str) -> None:
    response = httpx.post(
        f"{live_daemon}/predict",
        json={
            "state": {"message": "I was charged twice and need a refund today."},
            "questions": triage_questions(),
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    assert data["model"]
    assert set(data["answers"]) == EXPECTED_TRIAGE_ANSWERS
    assert data["usage"]["output_tokens"] == 0


@pytest.mark.integration
def test_cli_over_daemon_mcp_endpoint(live_daemon: str) -> None:
    result = CliRunner().invoke(
        cli_mod.main,
        ["--url", f"{live_daemon}/mcp", "triage", "refund me today please"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert set(data["answers"]) == EXPECTED_TRIAGE_ANSWERS
