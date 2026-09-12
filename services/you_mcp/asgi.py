"""ASGI entry point for the You.com guidance MCP service."""

from services.you_mcp.server import create_app

app = create_app()
