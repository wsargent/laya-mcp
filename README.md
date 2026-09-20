# laya-mcp

`laya-mcp` is a local [Model Context Protocol](https://modelcontextprotocol.io/) server that exposes [laya-mlx](https://github.com/mizorewww/laya-mlx) typed-decision inference through [FastMCP](https://gofastmcp.com) over stdio. Laya is a small decision-head model—not a generative LLM—that answers `choice`, `score`, and `noul` questions about text in one forward pass, with calibrated probabilities. Inference runs locally on the Metal GPU: no input data leaves your machine.

## Requirements

- macOS on Apple Silicon
- Python 3.12
- [uv](https://docs.astral.sh/uv/)

## Quickstart

```sh
git clone https://github.com/wsargent/laya-mcp.git
cd laya-mcp
uv sync
uv run laya-mcp
```

The server communicates over stdio. On the first inference call, it downloads the approximately 3.4 MB `convaiinnovations/laya` checkpoint from Hugging Face into `~/.cache/huggingface`. The model is loaded lazily, so startup and tool listing do not load the checkpoint.

## Tools

| Tool | Input | Questions answered |
|---|---|---|
| `laya_decide` | `state` (`str`, `dict`, or `list`) and a `questions` spec | Caller-defined questions; each question is `choice`, `score`, or `noul` |
| `laya_triage` | `message` (`str`) | `intent` (`choice`), `is_urgent` (`noul`), `frustration` (`score`, 0–3), `refund_requested` (`noul`), `churn_risk` (`noul`) |
| `laya_guard` | `prompt` (`str`) | `jailbreak` (`noul`), `prompt_injection` (`noul`), `sensitive_data` (`noul`), `harm_severity` (`score`, 0–3), `topic` (`choice`) |
| `laya_moderate` | `post` (`str`) | `toxic` (`noul`), `harassment` (`noul`), `threat` (`noul`), `spam` (`noul`), `severity` (`score`, 0–3) |
| `laya_email` | `body` (`str`), optional `categories` (`dict[str, str]`) | `category` (`choice`), `is_spam` (`noul`), `is_phishing` (`noul`), `urgency` (`score`, 0–2), `needs_reply` (`noul`) |

### Answer format

Each tool returns an object with `model`, `answers`, and `usage`. Every entry in `answers` contains:

- `type`: the question type (`choice`, `score`, or `noul`)
- `confidence`: model confidence, represented to four decimal places
- `action`: an object containing `act_probability` (the auxiliary action-head probability)

The type-specific fields are:

- **`choice`** — `choice` is the winning label, and `probabilities` maps each label to its probability. Its `criteria` is either a `{label: description}` object or a list of labels.
- **`score`** — `score` is the expected zero-based rubric level (for example, `1.66` on a 0–3 rubric lies between levels 1 and 2); `legend` maps stringified levels to rubric text; and `probabilities` maps stringified levels to probabilities. Its `criteria` is an ordered list from lowest to highest.
- **`noul`** — `noul` is P(yes), where `1.0` means certainly yes. For this type, `confidence` is `max(p_yes, 1 - p_yes)`. `criteria` is optional and can describe the false and true outcomes.

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
      "probabilities": {
        "refund": 0.9998,
        "technical_help": 0.0,
        "billing_question": 0.0,
        "information": 0.0,
        "cancellation": 0.0001,
        "other": 0.0
      }
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

`laya_decide` accepts any question specification. Question instructions refer to input with a backtick placeholder such as `` `message` ``, `` `prompt` ``, `` `post` ``, or `` `body` ``. The preset tools wrap their text argument in the matching state key. For `laya_email`, `categories` replaces the default `billing`, `technical`, `sales`, `security`, `hr`, and `other` routing choices as a `{label: description}` object.

## Configuration

The server reads these variables when the module is imported.

| Variable | Default | Meaning |
|---|---|---|
| `LAYA_MCP_MODEL` | `convaiinnovations/laya` | Model ID or local model path passed to `laya_mlx.load` |
| `LAYA_MCP_DTYPE` | `float16` | Dtype passed to `laya_mlx.load` |
| `LAYA_MCP_DEVICE` | library default | Optional device passed to `laya_mlx.load`; an empty value uses the library default |

The agent is loaded on the first inference call, not at startup. Errors from model loading or invalid configuration therefore surface on first inference.

## Client registration

For an MCP client that accepts a command and argument list, run the server with the Python environment created by uv:

```json
{
  "command": "/absolute/path/to/laya-mcp/.venv/bin/python",
  "args": ["-m", "laya_mcp.server"]
}
```

### Claude Desktop

Add the server to `claude_desktop_config.json`:

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

### Polytoken

Add this entry under `mcp_servers:` in `~/.config/polytoken/config.yaml`:

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

The 300-second timeout covers the cold first-call model load. The configuration takes effect in newly started sessions.

## Development and testing

```sh
uv sync
uv run pytest                  # unit tests (integration tests are excluded by default)
uv run pytest -m integration   # real-model integration tests over stdio
```

Integration tests use the real model and require network access on the first run to download the checkpoint. The test suite is in `tests/`; unit tests use a fake agent and do not load the model.

## Credits

The upstream model implementation is [laya-mlx](https://github.com/mizorewww/laya-mlx).
