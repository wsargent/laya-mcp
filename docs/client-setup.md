# MCP client setup

The stdio server command is:

```text
/absolute/path/to/laya-mcp/.venv/bin/python -m laya_mcp.server
```

Replace the path with the location of this checkout. The model loads on the first inference request.

## Claude Desktop

Add an entry to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "laya": {
      "command": "/absolute/path/to/laya-mcp/.venv/bin/python",
      "args": ["-m", "laya_mcp.server"]
    }
  }
}
```

Restart Claude Desktop after changing the configuration.

## Polytoken over stdio

Add this entry under `mcp_servers` in `~/.config/polytoken/config.yaml`:

```yaml
mcp_servers:
  laya:
    command: /absolute/path/to/laya-mcp/.venv/bin/python
    args:
      - -m
      - laya_mcp.server
    transport: stdio
```

## Polytoken over HTTP

Start `laya-daemon`, then use the shared endpoint:

```yaml
mcp_servers:
  laya:
    transport: http
    url: http://127.0.0.1:8742/mcp
```
