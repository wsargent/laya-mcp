# laya-mcp

`laya-mcp` runs the [Laya](https://github.com/mizorewww/laya-mlx) decision model locally and exposes it as an [MCP](https://modelcontextprotocol.io/) server. Use it to classify text, score text against a rubric, or answer yes/no questions without sending inference input to a remote service.

Laya is a decision model, not a chat model. It returns probabilities for structured questions such as “Is this urgent?” or “Which category fits this message?”. Inference uses the Apple Silicon GPU through MLX.

## Requirements

- macOS on Apple Silicon
- Python 3.12 or newer
- [`uv`](https://docs.astral.sh/uv/)

## Install

```sh
git clone https://github.com/wsargent/laya-mcp.git
cd laya-mcp
uv sync
```

The model checkpoint downloads from Hugging Face on the first inference request and is cached locally. The server starts without loading the model; the first request may take longer than later requests.

## Use as an MCP server

Start the stdio server from the project directory:

```sh
uv run laya-mcp
```

Register the server in an MCP client with the command below. Use the absolute path to the Python executable in this project's `.venv`:

```json
{
  "command": "/absolute/path/to/laya-mcp/.venv/bin/python",
  "args": ["-m", "laya_mcp.server"]
}
```

See [client setup](docs/client-setup.md) for Claude Desktop, Polytoken, and the shared daemon.

## Tools

The server provides five tools:

| Tool | Purpose |
| --- | --- |
| `laya_decide` | Answer caller-defined `choice`, `score`, and yes/no (`noul`) questions about a string, object, or list. |
| `laya_triage` | Classify a support message by intent, urgency, frustration, refund request, and churn risk. |
| `laya_guard` | Check a prompt for jailbreak, prompt-injection, sensitive-data, harm, and topic signals. |
| `laya_moderate` | Check a post for toxicity, harassment, threats, spam, and severity. |
| `laya_email` | Classify an email by category, spam, phishing, urgency, and whether it needs a reply. |

Every result contains `model`, `answers`, and `usage`. Each answer includes a `type`, `confidence`, and `action`; the type determines the result fields:

- `choice`: the selected label and probabilities for all labels.
- `score`: an expected rubric value and probabilities for each level.
- `noul`: the probability that the answer is yes.

Use `laya_decide` when the preset tools do not match your question. Its question instructions refer to input fields with backticks, for example `` `message` ``.

## Command-line client

`laya-cli` calls the same tools. Use `--stdio` for a one-off local server:

```sh
uv run laya-cli --stdio triage "I was charged twice and need a refund"
uv run laya-cli --stdio guard "ignore previous instructions"
uv run laya-cli --stdio moderate "post text"
uv run laya-cli --stdio email "Invoice attached"
```

For repeated requests, start the daemon in another terminal and omit `--stdio`:

```sh
uv run laya-daemon
uv run laya-cli ping
uv run laya-cli triage "I was charged twice and need a refund"
```

The daemon keeps one warm model for all clients. It serves MCP at `http://127.0.0.1:8742/mcp`, unless `LAYA_DAEMON_HOST` or `LAYA_DAEMON_PORT` changes the bind address. See [daemon and HTTP usage](docs/daemon.md).

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `LAYA_MCP_MODEL` | `convaiinnovations/laya` | Hugging Face model ID or local model path. |
| `LAYA_MCP_DTYPE` | `float16` | Data type passed to `laya_mlx.load`. |
| `LAYA_MCP_DEVICE` | library default | Optional MLX device. An empty value uses the library default. |
| `LAYA_DAEMON_URL` | unset | Daemon base URL for stdio inference forwarding. The stdio server falls back to local inference if forwarding fails. |
| `LAYA_DAEMON_TIMEOUT` | `15` | Per-request timeout for daemon forwarding, in seconds. |
| `LAYA_CLI_URL` | `http://127.0.0.1:8742/mcp` | Default MCP URL used by `laya-cli` without `--stdio` or `--url`. |

Code Mode is opt-in and changes the MCP tool surface. Read [Code Mode](docs/code-mode.md) before enabling `LAYA_MCP_CODE_MODE=1`.

## Development

```sh
uv run pytest
uv run pytest -m integration
```

The default test command skips integration tests. Integration tests load the real model and may download the checkpoint on the first run.

## Further documentation

- [Daemon and HTTP API](docs/daemon.md)
- [Client setup](docs/client-setup.md)
- [Code Mode](docs/code-mode.md)
- [Polytoken hooks](docs/polytoken.md)

## Credits

The model implementation comes from [laya-mlx](https://github.com/mizorewww/laya-mlx).
