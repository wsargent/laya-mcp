#!/usr/bin/env bash
# laya-prompt-guard.sh — Polytoken pre_user_prompt hook handler.
#
# Runs laya-mcp's guard preset over the submitted prompt and rejects the
# prompt (exit 2) when the prompt_injection probability exceeds the
# threshold. Fails open: any error, missing daemon, or unparsable input
# exits 0 so a broken guard never locks you out of prompting.
#
# Environment:
#   LAYA_GUARD_THRESHOLD  rejection threshold for prompt_injection (default 0.8)
#   LAYA_GUARD_TIMEOUT_S  per-request timeout for daemon calls (default 10)
#   LAYA_CLI_URL          daemon MCP URL (laya-cli default http://127.0.0.1:8742/mcp)
#
# Payload log: .polytoken/logs/pre_user_prompt.jsonl — the exact stdin JSON
# is appended on every firing so the jq extraction path can be verified and
# tightened against real payloads (field name is not documented upstream).

set -u

threshold="${LAYA_GUARD_THRESHOLD:-0.8}"
export LAYA_DAEMON_TIMEOUT="${LAYA_GUARD_TIMEOUT_S:-10}"

payload=$(cat)

# Resolve the repo and the laya-cli entrypoint from this script's own
# location so the hook works from any cwd without laya-cli on PATH.
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
repo_dir=$(cd "$script_dir/../.." && pwd)

guard() {
  if [ -x "$repo_dir/.venv/bin/laya-cli" ]; then
    "$repo_dir/.venv/bin/laya-cli" guard "$1"
  else
    (cd "$repo_dir" && uv run laya-cli guard "$1")
  fi
}

# Log the raw payload for verification (never blocks the decision).
log_dir="${POLYTOKEN_PROJECT_DIR:-$repo_dir}/.polytoken/logs"
mkdir -p "$log_dir" 2>/dev/null || true
printf '%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$payload" >>"$log_dir/pre_user_prompt.jsonl" 2>/dev/null || true

# Defensive extraction: the documented schema only names tool_name/input for
# tool events, so try the likely prompt fields in order.
text=$(printf '%s' "$payload" | jq -r '.prompt // .text // .user_prompt // .content // .input.prompt // empty' 2>/dev/null)

# Nothing extractable or trivially short: fail open.
[ -n "$text" ] || exit 0
[ "${#text}" -ge 8 ] || exit 0

# Evaluate. Any laya-cli failure (daemon down, timeout, bad JSON) fails open.
result=$(guard "$text" 2>/dev/null) || exit 0
prob=$(printf '%s' "$result" | jq -r '.answers.prompt_injection.noul // empty' 2>/dev/null)
[ -n "$prob" ] || exit 0

if awk -v x="$prob" -v t="$threshold" 'BEGIN { exit !(x > t) }'; then
  echo "laya-prompt-guard: rejected (prompt_injection probability ${prob} > ${threshold}). If this is a false positive, raise LAYA_GUARD_THRESHOLD or disable the !laya-prompt-guard hook in .polytoken/hooks.json."
  exit 2
fi

exit 0
