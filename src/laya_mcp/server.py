"""Laya MCP server: typed-decision inference from laya-mlx exposed over fastmcp.

The server defines five tools:

- ``laya_decide``   — generic: caller supplies the state and the question spec.
- ``laya_triage``   — support-ticket triage (state key ``message``).
- ``laya_guard``    — prompt safety guard (state key ``prompt``).
- ``laya_moderate`` — content moderation (state key ``post``).
- ``laya_email``    — inbound email triage (state key ``body``).

Setting ``LAYA_MCP_CODE_MODE=1`` swaps this surface for FastMCP's Code Mode
transform: clients get discovery/execute meta-tools and ship one Python
snippet that chains ``await call_tool(...)`` server-side, instead of making
many round-trips.

When ``LAYA_DAEMON_URL`` points at a running :mod:`laya_mcp.daemon`, inference
is forwarded there so every process shares one warm model; otherwise the MLX
agent is loaded lazily on first inference in this process (never at import
time), so server startup and tool listing are instant. Inference is
single-flight via a module-level lock because ``Agent.predict`` is not
documented as thread-safe.
"""

from __future__ import annotations

import os
import threading
from typing import Any

import httpx
from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration (read once at import; env vars override defaults)
# ---------------------------------------------------------------------------

MODEL_ID: str = os.environ.get("LAYA_MCP_MODEL", "convaiinnovations/laya")
DTYPE: str = os.environ.get("LAYA_MCP_DTYPE", "float16")
_DEVICE_ENV: str = os.environ.get("LAYA_MCP_DEVICE", "").strip()
DEVICE: str | None = _DEVICE_ENV or None


def _env_flag(name: str) -> bool:
    """Parse a boolean-ish environment variable."""
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


# Code Mode is opt-in: it replaces the five-tool surface with discovery and
# execute meta-tools, which would break clients expecting the laya_* tools.
CODE_MODE: bool = _env_flag("LAYA_MCP_CODE_MODE")
CODE_MODE_MAX_CALLS: int = int(os.environ.get("LAYA_CODE_MODE_MAX_CALLS", "50"))


def _make_mcp() -> FastMCP:
    """Build the server app, applying the Code Mode transform when enabled.

    With ``LAYA_MCP_CODE_MODE`` set, a client sends one Python snippet to the
    ``execute`` meta-tool; the snippet chains ``await call_tool(...)`` calls
    server-side (sandboxed, capped by ``LAYA_CODE_MODE_MAX_CALLS``), so a
    whole fan-out costs a single round-trip.
    """
    transforms: list[Any] = []
    if CODE_MODE:
        from fastmcp.experimental.transforms.code_mode import CodeMode

        transforms.append(CodeMode(max_tool_calls=CODE_MODE_MAX_CALLS))
    return FastMCP("laya", transforms=transforms)


mcp = _make_mcp()

# ---------------------------------------------------------------------------
# Agent management
# ---------------------------------------------------------------------------

_agent: Any | None = None
_agent_lock = threading.Lock()
_inference_lock = threading.Lock()
# True once this process has been primed with its own model (the daemon).
# A process that owns its model must never forward inference elsewhere,
# regardless of ambient LAYA_DAEMON_URL, so embedding or re-serving the
# shared app without daemon.main() cannot make it forward to itself.
_daemon_owned: bool = False


def _load_agent() -> Any:
    """Import laya_mlx and load the agent.

    The import happens here, not at module import time, so that loading this
    module (e.g. for tool listing or tests) never pulls in MLX.
    """
    import laya_mlx

    return laya_mlx.load(
        model_id_or_path=MODEL_ID,
        dtype=DTYPE,
        device=DEVICE,
    )


def _get_agent() -> Any:
    """Return the process-wide agent, loading it on first use (thread-safe)."""
    global _agent
    if _agent is None:
        with _agent_lock:
            if _agent is None:
                _agent = _load_agent()
    return _agent


def _prime_agent(agent: Any) -> None:  # pyright: ignore[reportUnusedFunction]  # used as server._prime_agent by daemon.py and tests
    """Install an already-loaded agent, bypassing lazy loading (daemon use).

    Priming also marks the process as owning its model: from then on
    ``_daemon_url`` reports no daemon, so the daemon's own tool calls can
    never be forwarded to itself or elsewhere.
    """
    global _agent, _daemon_owned
    with _agent_lock:
        _agent = agent
        _daemon_owned = True


def _predict_local(state: Any, questions: dict[str, Any]) -> dict[str, Any]:
    """Run one inference against the local agent, serialized by lock."""
    with _inference_lock:
        return _get_agent().predict(state, questions)


def _daemon_url() -> str | None:
    """Return the daemon base URL when configured, else ``None``.

    Read per call rather than at import so tests and embedders can point the
    server at a daemon with an environment variable, no reload required —
    except in a process that has been primed with its own model (the
    daemon): ownership beats ambient configuration.
    """
    if _daemon_owned:
        return None
    return os.environ.get("LAYA_DAEMON_URL", "").strip() or None


def _predict_via_daemon(url: str, state: Any, questions: dict[str, Any]) -> dict[str, Any]:
    """POST one inference to a running laya daemon's ``/predict`` endpoint."""
    timeout = float(os.environ.get("LAYA_DAEMON_TIMEOUT", "15"))
    response = httpx.post(
        f"{url.rstrip('/')}/predict",
        json={"state": state, "questions": questions},
        timeout=timeout,
    )
    response.raise_for_status()
    result: dict[str, Any] = response.json()
    return result


def _predict(state: Any, questions: dict[str, Any]) -> dict[str, Any]:
    """Run one inference, daemon-first.

    All tools route through this helper. When ``LAYA_DAEMON_URL`` is set and
    the daemon answers, the call is forwarded there so all processes share one
    warm model; if the daemon is unreachable or errors, this silently falls
    back to the local lazy-loaded agent (paying one cold load), keeping the
    tools available while the daemon is down.
    """
    url = _daemon_url()
    if url is not None:
        try:
            return _predict_via_daemon(url, state, questions)
        except Exception:
            pass  # daemon down or unhealthy: fall back to the local model
    return _predict_local(state, questions)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool
def laya_decide(state: str | dict[str, Any] | list[Any], questions: dict[str, Any]) -> dict[str, Any]:
    """Run arbitrary typed-decision inference with a caller-supplied question spec.

    Args:
        state: Input text for the questions. Usually a plain string (a message,
            prompt, post or email body). Question instructions reference the
            input with a backtick placeholder, so either pass a string or a
            dict whose key matches the placeholder the questions use (for the
            presets: ``message``, ``prompt``, ``post`` or ``body``). A dict or
            list is serialized to JSON text and embedded in the prompt as-is;
            exactly one answer per question is returned (there is no
            per-element batching).
        questions: Question spec: a dict mapping question name to its
            definition. Each definition has ``type`` and ``instructions``, plus
            ``criteria`` depending on type (see below).

    Question types:

    1. ``choice`` — pick one label. ``criteria`` is either a dict
       ``{"label": "description", ...}`` or a list ``["label", ...]``.
       Example: ``{"intent": {"type": "choice", "instructions": "What does
       the customer want in `message`?", "criteria": {"refund": "money
       returned", "bug": "a software problem"}}}``
    2. ``score`` — expected position on an ordered rubric. ``criteria`` is a
       list of level descriptions from worst/lowest to best/highest.
       Example: ``{"frustration": {"type": "score", "instructions": "How
       frustrated is the author of `message`?", "criteria": ["calm",
       "annoyed", "angry"]}}``
    3. ``noul`` — yes/no probability. ``criteria`` is optional; when present
       it describes the two outcomes: ``{"false": "desc", "true": "desc"}``.
       Example: ``{"is_urgent": {"type": "noul", "instructions": "Does
       `message` communicate a deadline?"}}``

    Returns ``{"model": ..., "answers": {...}, "usage": {"input_tokens": n,
    "output_tokens": 0}}``. Each answer in ``answers`` always contains:

    - ``type`` — the question type
    - ``confidence`` — model confidence, 4 decimal places
    - ``action`` — ``{"act_probability": float}``, an auxiliary action head

    plus, by type:

    - ``choice``: ``choice`` (winning label) and ``probabilities``
      (label -> probability)
    - ``score``: ``score`` (expected zero-based rubric level, e.g. 1.37 on a
      3-level rubric means between "annoyed" and "angry"), ``legend``
      ({"0": first level, ...}) and ``probabilities`` ({"0": p0, ...})
    - ``noul``: ``noul`` (P(yes), where 1.0 means certainly yes); for this
      type ``confidence`` is ``max(p_yes, 1 - p_yes)``
    """
    return _predict(state, questions)


@mcp.tool
def laya_triage(message: str) -> dict[str, Any]:
    """Triage a support message (preset questions, state key `message`).

    Returns answers for: ``intent`` (choice: refund / technical_help /
    billing_question / information / cancellation / other), ``is_urgent``
    (noul), ``frustration`` (score, 4 levels from calm to very angry),
    ``refund_requested`` (noul) and ``churn_risk`` (noul). See
    ``laya_decide`` for the answer payload shapes.
    """
    from laya_mlx import triage_questions

    return _predict({"message": message}, triage_questions())


@mcp.tool
def laya_guard(prompt: str) -> dict[str, Any]:
    """Screen a user prompt for safety risks (preset questions, state key `prompt`).

    Returns answers for: ``jailbreak`` (noul), ``prompt_injection`` (noul),
    ``sensitive_data`` (noul), ``harm_severity`` (score, 4 levels from none to
    severe) and ``topic`` (choice: product_support / coding /
    general_knowledge / personal_advice / security_testing / other). See
    ``laya_decide`` for the answer payload shapes.
    """
    from laya_mlx import guard_questions

    return _predict({"prompt": prompt}, guard_questions())


@mcp.tool
def laya_moderate(post: str) -> dict[str, Any]:
    """Moderate a user-generated post (preset questions, state key `post`).

    Returns answers for: ``toxic`` (noul), ``harassment`` (noul),
    ``threat`` (noul), ``spam`` (noul) and ``severity`` (score, 4 levels from
    no rule-breaking to extreme). See ``laya_decide`` for the answer payload
    shapes.
    """
    from laya_mlx import moderation_questions

    return _predict({"post": post}, moderation_questions())


@mcp.tool
def laya_email(body: str, categories: dict[str, str] | None = None) -> dict[str, Any]:
    """Triage an inbound email (preset questions, state key `body`).

    Args:
        body: The email body text.
        categories: Optional replacement routing choices for the ``category``
            question, as ``{"label": "description"}``. Defaults to
            billing / technical / sales / security / hr / other.

    Returns answers for: ``category`` (choice), ``is_spam`` (noul),
    ``is_phishing`` (noul), ``urgency`` (score, 3 levels) and ``needs_reply``
    (noul). See ``laya_decide`` for the answer payload shapes.
    """
    from laya_mlx import email_questions

    if categories is not None and not categories:
        raise ValueError("categories, when provided, must be a non-empty dict")
    return _predict({"body": body}, email_questions(categories))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
