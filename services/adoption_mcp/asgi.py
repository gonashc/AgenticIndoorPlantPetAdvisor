"""ASGI entry point for the private adoption MCP service."""

from services.adoption_mcp.server import create_app

app = create_app()
