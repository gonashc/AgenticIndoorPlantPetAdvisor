"""ASGI entry point for the private care-plan MCP service."""

from services.care_plan_mcp.server import create_app

app = create_app()
