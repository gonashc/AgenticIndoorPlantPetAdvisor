"""ASGI entry point for the private plant-location MCP service."""

from services.places_mcp.server import create_app

app = create_app()
