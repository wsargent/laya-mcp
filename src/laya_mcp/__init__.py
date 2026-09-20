"""laya-mcp: local MCP server exposing laya-mlx typed-decision inference."""

__all__ = ["main"]


def main() -> None:
    """Entry point kept for ``python -m laya_mcp``; delegates to the server."""
    from laya_mcp.server import main as server_main

    server_main()
