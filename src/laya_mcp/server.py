"""Laya MCP server: typed-decision inference from laya-mlx exposed over fastmcp.

The server defines five tools:

- ``laya_decide``   — generic: caller supplies the state and the question spec.
- ``laya_triage``   — support-ticket triage (state key ``message``).
- ``laya_guard``    — prompt safety guard (state key ``prompt``).
- ``laya_moderate`` — content moderation (state key ``post``).
- ``laya_email``    — inbound email triage (state key ``body``).

The MLX agent is loaded lazily on first inference (never at import time), so
server startup and tool listing are instant. Inference is single-flight via a
module-level lock because ``Agent.predict`` is not documented as thread-safe.
"""

from __future__ import annotations

import os
import threading
from typing import Any

from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration (read once at import; env vars override defaults)
# ---------------------------------------------------------------------------

MODEL_ID: str = os.environ.get("LAYA_MCP_MODEL", "convaiinnovations/laya")
DTYPE: str = os.environ.get("LAYA_MCP_DTYPE", "float16")
_DEVICE_ENV: str = os.environ.get("LAYA_MCP_DEVICE", "").strip()
DEVICE: str | None = _DEVICE_ENV or None

mcp = FastMCP("laya")

# ---------------------------------------------------------------------------
# Agent management
# ---------------------------------------------------------------------------

_agent: Any | None = None
_agent_lock = threading.Lock()
_inference_lock = threading.Lock()


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


def _predict(state: Any, questions: dict[str, Any]) -> dict[str, Any]:
    """Run one inference against the shared agent, serialized by lock.

    All tools route through this helper: fastmcp may serve tool calls
    concurrently and ``Agent.predict`` shares mutable model state.
    """
    with _inference_lock:
        return _get_agent().predict(state, questions)


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
            presets: ``message``, ``prompt``, ``post`` or ``body``). A list is
            passed through for batch inference.
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
    3. ``noul`` — yes/no probability, no criteria.
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

    return _predict({"body": body}, email_questions(categories))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
