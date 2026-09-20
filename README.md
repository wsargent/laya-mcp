# laya-mcp

Local MCP server exposing [laya-mlx](https://github.com/mizorewww/laya-mlx)
typed-decision inference on Apple Silicon (MLX) via
[fastmcp](https://gofastmcp.com), served over stdio.

Laya is a small decision-head model (not a generative LLM): it answers typed
questions — `choice`, `score`, or `noul` — about a text input in a single
forward pass, with calibrated probabilities. Inference runs locally on the
Metal GPU; no data leaves the machine.

## Tools

| Tool | Input | Answers |
|---|---|---|
| `laya_decide` | arbitrary `state` + `questions` spec | caller-defined |
| `laya_triage` | `message` (support ticket) | `intent` (choice), `is_urgent`, `frustration` (score 0–3), `refund_requested`, `churn_risk` (both noul) |
| `laya_guard` | `prompt` (user prompt screening) | `jailbreak`, `prompt_injection`, `sensitive_data` (noul), `harm_severity` (score 0–3), `topic` (choice) |
| `laya_moderate` | `post` (content moderation) | `toxic`, `harassment`, `threat`, `spam` (noul), `severity` (score 0–3) |
| `laya_email` | `body`, optional `categories` (email triage) | `category` (choice), `is_spam`, `is_phishing`, `needs_reply` (noul), `urgency` (score 0–2) |

### Answer shapes

Every answer contains `type`, `confidence` (4 decimal places), and
`action: {"act_probability": float}`. By question type:

- **`choice`** — adds `choice` (winning label) and `probabilities`
  (`{label: probability}`). `criteria` is a dict `{label: description}` or a
  list of labels.
- **`score`** — adds `score` (expected zero-based rubric level, e.g. `1.66`
  on a 0–3 rubric means between levels 1 and 2), `legend`
  (`{"0": rubric text, ...}`), and `probabilities` (`{"0": p, ...}`).
  `criteria` is an ordered list of level descriptions, worst to best.
- **`noul`** — adds `noul` (P(yes); `1.0` = certainly yes). For this type
  `confidence` is `max(p_yes, 1 - p_yes)`.

Example result from `laya_triage`:

```json
{
  "model": "laya-rl-agent",
  "answers": {
    "intent": {
      "type": "choice",
      "confidence": 0.9991,
      "action": {"act_probability": 1.0},
      "choice": "refund",
      "probabilities": {"refund": 0.9998, "technical_help": 0.0, "...": 0.0}
    },
    "is_urgent": {
      "type": "noul",
      "confidence": 0.5912,
      "action": {"act_probability": 1.0},
      "noul": 0.4088
    }
  },
  "usage": {"input_tokens": 369, "output_tokens": 0}
}
```

`laya_decide` accepts any question spec; see its docstring (exposed via MCP
tool description) for a worked example of each type. For `laya_email`,
`categories` replaces the default routing choices
(`billing` / `technical` / `sales` / `security` / `hr` / `other`) as
`{"label": "description"}`.

Question instructions reference the input with a backtick placeholder
(`` `message` ``, `` `prompt` ``, `` `post` ``, `` `body` ``); the preset
tools wrap the text argument into the matching state key automatically.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `LAYA_MCP_MODEL` | `convaiinnovations/laya` | Hugging Face model id or local path |
| `LAYA_MCP_DTYPE` | `float16` | Model dtype: `float16`, `bfloat16`, or `float32` |
| `LAYA_MCP_DEVICE` | library default (`gpu`) | MLX device: `gpu`, `metal`, or `cpu` |

The checkpoint downloads to the Hugging Face cache (`~/.cache/huggingface`)
on first load; later starts are instant.

## Development

```sh
uv sync                     # install into .venv (Python 3.12)
uv run pytest               # unit tests (fake agent, no model load)
uv run pytest -m integration  # real-model tests over stdio (downloads checkpoint on first run)
uv run laya-mcp             # run the server over stdio
uv run python -m laya_mcp.server  # same thing
```

The agent loads lazily on first inference (not at startup), and inference is
serialized behind a lock because fastmcp may serve tool calls concurrently.

## Polytoken registration

Add to `mcp_servers:` in `~/.config/polytoken/config.yaml`:

```yaml
mcp_servers:
    laya:
        args:
            - -m
            - laya_mcp.server
        command: /Users/wsargent/work/laya-mcp/.venv/bin/python
        default_timeout_seconds: 300
        transport: stdio
```

Takes effect in newly started sessions. `default_timeout_seconds: 300`
covers the cold first-call model load.

## Claude Desktop registration

For future use, the equivalent `claude_desktop_config.json` snippet:

```json
{
  "mcpServers": {
    "laya": {
      "command": "/Users/wsargent/work/laya-mcp/.venv/bin/python",
      "args": ["-m", "laya_mcp.server"]
    }
  }
}
```
