# Polytoken hooks

This repository includes optional hooks that use the daemon's local model. They fail open: if the daemon or payload is unavailable, the hook allows the action.

Treat these hooks as heuristics, not as a security boundary. Review their logs and tune thresholds for your traffic before enabling enforcement.

## Shell gate

`scripts/laya_shell_gate.sh` is a `pre_tool_use` hook for `shell_exec`. It sends the command to `/predict` and denies it when the model's destructive probability reaches `LAYA_GATE_THRESHOLD` (default `0.5`). It logs to `LAYA_GATE_LOG` (default `/tmp/laya-shell-gate.log`).

Register it in `.polytoken/hooks.json`:

```json
[
  {
    "name": "laya-shell-gate",
    "event": "pre_tool_use",
    "matcher": "shell_exec",
    "handler": {
      "bash": "LAYA_DAEMON_URL=http://127.0.0.1:8742 /absolute/path/to/laya-mcp/scripts/laya_shell_gate.sh"
    }
  }
]
```

## Prompt guard

`scripts/laya_prompt_guard.sh` is a `pre_user_prompt` hook. It calls `laya_guard` and a destructive-request question through Code Mode. It logs by default and only rejects prompts when `LAYA_GUARD_ENFORCE=1`.

Run a separate Code Mode daemon for it:

```sh
LAYA_DAEMON_PORT=8743 LAYA_MCP_CODE_MODE=1 uv run laya-daemon
```

The main settings are `LAYA_GUARD_URL`, `LAYA_GUARD_THRESHOLD` (default `0.9`), `LAYA_GUARD_ENFORCE` (default `0`), and `LAYA_GUARD_LOG` (default `/tmp/laya-prompt-guard.log`).

## Payload logger

`scripts/laya_log_payloads.sh` records raw hook payloads to `POLYTOKEN_PAYLOAD_LOG` (default `/tmp/polytoken-payloads.log`). It emits no decision and is useful when writing a new hook against an event's actual payload shape.
