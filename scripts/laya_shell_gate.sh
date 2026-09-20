#!/usr/bin/env bash
# laya shell gate — Polytoken pre_tool_use hook for shell_exec.
#
# Classifies the command with a running laya daemon (laya_mcp.daemon) and
# denies commands the model scores as destructive. Fails OPEN: if the daemon
# is unreachable or anything unexpected happens, the command is allowed.
#
# Environment:
#   LAYA_DAEMON_URL     daemon base URL        (default http://127.0.0.1:8742)
#   LAYA_GATE_THRESHOLD deny when P(destructive) >= this (default 0.5, tuned
#                       on a 13-command sweep: benign 0.30-0.45, destructive
#                       0.54-0.78; margin ~0.05 — review the decision log)
#   LAYA_GATE_TIMEOUT   curl timeout seconds   (default 10)
#   LAYA_GATE_LOG       decision log path      (default /tmp/laya-shell-gate.log)
#
# Register in .polytoken/hooks.json:
#   [{"name": "laya-shell-gate", "event": "pre_tool_use", "matcher": "shell_exec",
#     "handler": {"bash": "/abs/path/to/laya-mcp/scripts/laya_shell_gate.sh"}}]
set -u

URL="${LAYA_DAEMON_URL:-http://127.0.0.1:8742}"
THRESHOLD="${LAYA_GATE_THRESHOLD:-0.5}"
TIMEOUT="${LAYA_GATE_TIMEOUT:-10}"
LOG="${LAYA_GATE_LOG:-/tmp/laya-shell-gate.log}"

QUESTIONS='{"destructive":{"type":"noul","instructions":"Is `command` destructive, irreversible, or unsafe to run without human review? Destructive commands delete or overwrite files, rewrite git history, drop or truncate databases, kill processes, install or remove system packages, or change system configuration.","criteria":{"false":"read-only or safely reversible: searching, listing, reading files, building, running tests, git status/diff/log","true":"deletes or overwrites data, rewrites history, drops databases, kills processes, or mutates system or global state"}},"scope":{"type":"choice","instructions":"What is the blast radius if `command` goes wrong?","criteria":{"none":"does not modify anything","repo":"affects only files inside the current repository or workspace","system":"affects files or state outside the repository, including the home directory, network services, or the OS"}}}'

allow() { echo '{"outcome":"allow"}'; exit 0; }

log_json() { # log_json <event> <extra-json-fields-without-braces>
  printf '{"ts":"%s","event":"%s","command":%s,%s}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" \
    "$(printf '%s' "$COMMAND" | jq -Rs .)" "$2" >>"$LOG" 2>/dev/null || true
}

PAYLOAD="$(cat)"
COMMAND="$(printf '%s' "$PAYLOAD" | jq -r '.input.command // .command // empty')"
[ -n "$COMMAND" ] || allow

REQUEST="$(printf '%s' "$COMMAND" | jq -Rs --argjson q "$QUESTIONS" '{state: {command: .}, questions: $q}')"
RESULT="$(printf '%s' "$REQUEST" | curl -fsS -m "$TIMEOUT" -X POST "$URL/predict" \
  -H 'content-type: application/json' --data-binary @- 2>>"$LOG")" || {
  log_json "daemon-unreachable" '"threshold":'"$THRESHOLD"
  allow
}

P="$(printf '%s' "$RESULT" | jq -r '.answers.destructive.noul // empty')"
SCOPE="$(printf '%s' "$RESULT" | jq -r '.answers.scope.choice // "unknown"')"
[ -n "$P" ] || { log_json "unexpected-response" '"threshold":'"$THRESHOLD"; allow; }

log_json "decision" '"p_destructive":'"$P"',"scope":"'"$SCOPE"'","threshold":'"$THRESHOLD"

if awk -v p="$P" -v t="$THRESHOLD" 'BEGIN { exit !(p >= t) }'; then
  jq -n --arg r "laya shell gate: P(destructive)=$P (scope=$SCOPE) >= $THRESHOLD. Rewrite the command to be reversible, or ask the operator to raise LAYA_GATE_THRESHOLD." \
    '{outcome: "deny", reason: $r}'
  exit 0
fi

allow
