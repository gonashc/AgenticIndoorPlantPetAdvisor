"""Grant least-privilege database access to Catalog and Care Plan MCP identities."""

import asyncio
import os

from advisor_api.config import Settings

from database.runtime import create_database_runtime
from database.seeding import grant_mcp_runtime_access


async def run() -> None:
    catalog_user = os.environ.get("CATALOG_MCP_DATABASE_USER", "").strip()
    care_plan_user = os.environ.get("CARE_PLAN_MCP_DATABASE_USER", "").strip()
    if not catalog_user or not care_plan_user:
        raise RuntimeError("CATALOG_MCP_DATABASE_USER and CARE_PLAN_MCP_DATABASE_USER are required")
    settings = Settings()
    if settings.database_mode == "memory":
        raise RuntimeError("MCP database grants require PostgreSQL")
    runtime = await create_database_runtime(settings)
    try:
        await grant_mcp_runtime_access(runtime.session_factory, catalog_user, care_plan_user)
    finally:
        await runtime.close()


def main() -> int:
    asyncio.run(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
