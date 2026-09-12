"""ASGI entry point for the private catalog MCP service."""

from services.catalog_mcp.server import create_app

app = create_app()
