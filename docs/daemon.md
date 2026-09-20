# Daemon and HTTP API

`laya-daemon` loads the model once and serves MCP and plain JSON over HTTP. Use it when several clients or scripts should share one warm model.

Start it with:

```sh
uv run laya-daemon
```

By default it listens on `127.0.0.1:8742`. Set `LAYA_DAEMON_HOST` and `LAYA_DAEMON_PORT` before starting it to change the bind address.

## Endpoints

### MCP: `/mcp`

Connect an MCP client to:

```text
http://127.0.0.1:8742/mcp
```

This exposes the same five tools as the stdio server.

### Readiness: `GET /health`

Returns `200` after the model is loaded and `503` while the daemon is starting.

```sh
curl http://127.0.0.1:8742/health
```

### Inference: `POST /predict`

Use this endpoint from hooks and scripts that do not need MCP:

```sh
curl -s http://127.0.0.1:8742/predict \
  -H 'content-type: application/json' \
  -d '{"state":{"message":"I need a refund"},"questions":{"refund":{"type":"noul","instructions":"Does `message` request a refund?"}}}'
```

The request must contain a `state` string, object, or list and a non-empty `questions` object. The response is the normal Laya result with `model`, `answers`, and `usage`.

## Sharing the daemon from stdio clients

Set `LAYA_DAEMON_URL` to the daemon base URL when starting a stdio server:

```sh
LAYA_DAEMON_URL=http://127.0.0.1:8742 uv run laya-mcp
```

The stdio server forwards inference to `/predict`. If the daemon is unavailable, it loads and uses its own model locally.
