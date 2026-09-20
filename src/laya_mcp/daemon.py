"""Persistent laya daemon: the MCP server over HTTP plus warm-model endpoints.

Running ``uv run laya-daemon`` starts the same five-tool MCP server as
``laya-mcp``, but over streamable HTTP, with the model loaded eagerly at
startup and two extra plain-JSON endpoints attached for non-MCP callers:

- ``POST /predict`` — ``{"state": ..., "questions": {...}}`` in, the
  ``Agent.predict`` result out. Intended for hooks and scripts (curl-able).
- ``GET /health`` — readiness probe; 200 once the model is loaded.

Every consumer then shares one warm model:

- MCP clients connect to ``http://HOST:PORT/mcp`` (Polytoken: ``transport:
  http``), getting the full tool surface served in-process.
- The stdio server forwards inference here via ``LAYA_DAEMON_URL`` and falls
  back to its own lazy load when the daemon is down.
- Hooks and scripts POST straight to ``/predict``.

There is no separate daemon app: the routes below are attached to the shared
``laya_mcp.server.mcp`` FastMCP instance, so importing this module is what
equips it. Importing :mod:`laya_mcp.server` alone (the stdio entry point)
never attaches them. Configuration (read at import):

- ``LAYA_DAEMON_HOST`` — bind address (default ``127.0.0.1``)
- ``LAYA_DAEMON_PORT`` — bind port (default ``8742``)
- ``LAYA_MCP_MODEL`` / ``LAYA_MCP_DTYPE`` / ``LAYA_MCP_DEVICE`` — model
  selection, shared with :mod:`laya_mcp.server`.
"""

from __future__ import annotations

import os
from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import server

HOST: str = os.environ.get("LAYA_DAEMON_HOST", "127.0.0.1")
PORT: int = int(os.environ.get("LAYA_DAEMON_PORT", "8742"))


@server.mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    """Readiness: 200 once the model is loaded, 503 before that."""
    if server._agent is None:
        return JSONResponse({"status": "starting"}, status_code=503)
    return JSONResponse({"status": "ok", "model": server.MODEL_ID})


@server.mcp.custom_route("/predict", methods=["POST"])
async def predict(request: Request) -> JSONResponse:
    """Run one typed-decision inference.

    Body: ``{"state": <str|dict|list>, "questions": {...}}``. Returns the
    ``Agent.predict`` result (``{"model", "answers", "usage"}``) unchanged.
    Inference runs in a worker thread under the shared inference lock so
    concurrent requests serialize instead of racing on model state.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "body must be valid JSON"}, status_code=400)
    if not isinstance(body, dict) or "state" not in body:
        return JSONResponse({"error": "'state' is required"}, status_code=400)
    questions = body.get("questions")
    if not isinstance(questions, dict) or not questions:
        return JSONResponse(
            {"error": "'questions' must be a non-empty object"}, status_code=400
        )
    agent = server._agent
    if agent is None:
        return JSONResponse({"error": "model not loaded yet"}, status_code=503)

    def _run() -> dict[str, Any]:
        with server._inference_lock:
            return agent.predict(body["state"], questions)

    return JSONResponse(await run_in_threadpool(_run))


def main() -> None:
    """Load the model once, then serve MCP and JSON over streamable HTTP."""
    # Priming marks the process as owning its model: _daemon_url then
    # ignores ambient LAYA_DAEMON_URL, so a variable exported for stdio
    # servers can never make this daemon forward its own tool calls.
    server._prime_agent(server._load_agent())
    server.mcp.run(transport="http", host=HOST, port=PORT)


if __name__ == "__main__":
    main()
