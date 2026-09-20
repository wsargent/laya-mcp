# Code Mode

Code Mode lets one MCP call run a Python snippet that makes several Laya calls. It is useful for batch classification or when later decisions depend on earlier results.

Enable it on the server:

```sh
LAYA_MCP_CODE_MODE=1 uv run laya-daemon
```

Code Mode replaces the five `laya_*` tools with `search`, `get_schema`, and `execute`. Clients that expect the normal tool names should not connect to a Code Mode server.

Inside an `execute` snippet, call tools with `await call_tool(...)` and return the value you want:

```python
messages = ["I need a refund", "Where is my order?"]
results = []
for message in messages:
    result = await call_tool("laya_triage", {"message": message})
    results.append(result["answers"]["intent"]["choice"])
return results
```

Limit calls per execution with `LAYA_CODE_MODE_MAX_CALLS` (default `50`). FastMCP also applies its execution time and memory limits.

The CLI enables Code Mode automatically for its one-off stdio execution path:

```sh
uv run laya-cli --stdio exec sweep.py
uv run laya-cli --stdio exec <<'PY'
result = await call_tool("laya_triage", {"message": "I need a refund"})
return result["answers"]["intent"]["choice"]
PY
```
