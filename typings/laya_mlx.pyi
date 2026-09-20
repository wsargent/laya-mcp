"""Type stubs for the subset of ``laya_mlx`` used by laya-mcp.

The installed package is untyped; these signatures mirror agent.py and
presets.py so pyright strict mode has something concrete to check against.
"""

from typing import Any

# One question spec: {"type": ..., "instructions": ..., "criteria": ...}.
type Question = dict[str, Any]
# A question set keyed by question name.
type Questions = dict[str, Question]


def triage_questions() -> Questions: ...
def email_questions(categories: dict[str, str] | None = ...) -> Questions: ...
def guard_questions() -> Questions: ...
def moderation_questions() -> Questions: ...
def router_questions() -> Questions: ...


class Agent:
    def __init__(
        self,
        model_id_or_path: str = ...,
        device: str | None = ...,
        token: str | None = ...,
        subfolder: str | None = ...,
        *,
        dtype: str = ...,
        revision: str | None = ...,
        batch_size: int = ...,
        compile: bool = ...,
        pad_to_multiple: int | None = ...,
        cache_prompts: bool = ...,
    ) -> None: ...

    def predict(self, state: Any, questions: Questions) -> dict[str, Any]: ...


def load(
    model_id_or_path: str = ...,
    device: str | None = ...,
    token: str | None = ...,
    subfolder: str | None = ...,
    **kwargs: Any,
) -> Agent: ...
