#!/usr/bin/env bash
# laya payload logger — discovery hook for writing new laya hooks.
#
# Appends the raw JSON payload of each matched event to a log file so hook
# authors can see the real field names (the docs only pin down tool events'
# .tool_name/.input). Produces no decision: exit 0 with no output is the
# proceed/allow outcome for blocking events and is discarded for
# fire-and-forget ones, so attaching it never changes behavior.
#
# Environment:
#   POLYTOKEN_PAYLOAD_LOG  log path (default /tmp/polytoken-payloads.log)
#
# Register in .polytoken/hooks.json, e.g.:
#   [
#     {"name": "laya-log-stop-payload", "event": "stop",
#      "handler": {"bash": "/abs/path/to/laya-mcp/scripts/laya_log_payloads.sh"}},
#     {"name": "laya-log-turn-payload", "event": "post_model_turn",
#      "handler": {"bash": "/abs/path/to/laya-mcp/scripts/laya_log_payloads.sh"}}
#   ]
set -u
cat >>"${POLYTOKEN_PAYLOAD_LOG:-/tmp/polytoken-payloads.log}" 2>/dev/null || true
exit 0
