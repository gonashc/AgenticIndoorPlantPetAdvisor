"""ASGI entry point for the optional commerce MCP service."""

from services.commerce_mcp.server import create_app

app = create_app()
