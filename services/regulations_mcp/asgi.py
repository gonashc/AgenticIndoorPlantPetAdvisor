"""ASGI entry point for the regulations MCP service."""

from services.regulations_mcp.server import create_app

app = create_app()
