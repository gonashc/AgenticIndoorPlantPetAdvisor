"""ASGI entry point for the private climate MCP service."""

from services.climate_mcp.server import create_app

app = create_app()
