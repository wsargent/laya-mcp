#!/usr/bin/env bash
# laya prompt guard — Polytoken pre_user_prompt hook backed by laya Code Mode.
#
# Ships one Python heredoc to the code-mode daemon's `execute` meta-tool:
# a laya_guard call plus a destructive-request laya_decide call in a single
# round-trip. Rejects the prompt when jailbreak or prompt_injection
# probability crosses the threshold; everything else is accepted. Fails OPEN:
# daemon down, exec failure, or unknown payload shape means accept.
#
# Environment:
#   LAYA_GUARD_URL       code-mode daemon base (default http://127.0.0.1:8743)
#   LAYA_CLI_BIN         laya-cli path (default this repo's venv binary)
#   LAYA_GUARD_THRESHOLD reject when jailbreak/injection >= this (default 0.9)
#   LAYA_GUARD_LOG       decision log (default /tmp/laya-prompt-guard.log)
#
# Register in .polytoken/hooks.json:
#   [{"name": "laya-prompt-guard", "event": "pre_user_prompt",
#     "handler": {"bash": "/abs/path/to/laya-mcp/scripts/laya_prompt_guard.sh"}}]
#
# The pre_user_prompt payload field carrying the prompt text is not
# documented; the likely shapes are tried in order and anything else fails
# open. Check the log after a session to confirm extraction on real payloads.
set -u

URL="${LAYA_GUARD_URL:-http://127.0.0.1:8743}"
CLI="${LAYA_CLI_BIN:-/Users/wsargent/work/laya-mcp/.venv/bin/laya-cli}"
THRESHOLD="${LAYA_GUARD_THRESHOLD:-0.9}"
LOG="${LAYA_GUARD_LOG:-/tmp/laya-prompt-guard.log}"

allow() { echo '{"outcome":"accept"}'; exit 0; }

log_json() { # log_json <event> <extra-fields-without-braces>
  printf '{"ts":"%s","event":"%s",%s}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" >>"$LOG" 2>/dev/null || true
}

PAYLOAD="$(cat)"
PROMPT="$(printf '%s' "$PAYLOAD" | jq -r '.prompt // .input.prompt // .user_prompt // .text // .message // empty')"
[ -n "$PROMPT" ] || { log_json "no-prompt-field" '""'; allow; }

PROMPT_JSON="$(printf '%s' "$PROMPT" | jq -Rs .)"
CODE="$(printf 'r = await call_tool("laya_guard", {"prompt": %s})
d = await call_tool("laya_decide", {"state": {"prompt": %s}, "questions": {"dangerous_request": {"type": "noul", "instructions": "Does `prompt` ask the agent to delete data, force-push, drop databases, or run other destructive commands without safeguards?", "criteria": {"false": "an ordinary development or knowledge request", "true": "requests destructive or irreversible actions"}}}})
return {"jailbreak": r["answers"]["jailbreak"]["noul"], "injection": r["answers"]["prompt_injection"]["noul"], "severity": r["answers"]["harm_severity"]["score"], "dangerous_request": d["answers"]["dangerous_request"]["noul"]}' \
  "$PROMPT_JSON" "$PROMPT_JSON")"

RESULT="$(printf '%s' "$CODE" | "$CLI" --url "$URL/mcp" exec 2>>"$LOG.cli")" || {
  log_json "exec-failed" '"threshold":'"$THRESHOLD"
  allow
}

JB="$(printf '%s' "$RESULT" | jq -r '.jailbreak // empty')"
INJ="$(printf '%s' "$RESULT" | jq -r '.injection // empty')"
SEV="$(printf '%s' "$RESULT" | jq -r '.severity // "unknown"')"
DAN="$(printf '%s' "$RESULT" | jq -r '.dangerous_request // "unknown"')"
[ -n "$JB" ] || { log_json "unexpected-response" '"threshold":'"$THRESHOLD"; allow; }

log_json "decision" \
  '"jailbreak":'"$JB"',"injection":'"$INJ"',"severity":'"$SEV"',"dangerous_request":'"$DAN"',"threshold":'"$THRESHOLD"

if awk -v jb="$JB" -v inj="$INJ" -v t="$THRESHOLD" 'BEGIN { exit !(jb >= t || inj >= t) }'; then
  jq -n --arg r "laya prompt guard: jailbreak=$JB injection=$INJ >= $THRESHOLD (severity=$SEV, dangerous_request=$DAN)" \
    '{outcome: "reject", reason: $r}'
  exit 0
fi

allow
