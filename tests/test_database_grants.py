"""Least-privilege database grant tests for MCP runtime identities."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

import pytest
from sqlalchemy.sql.elements import TextClause

from database.runtime import AsyncSessionFactory
from database.seeding import grant_mcp_runtime_access


class RecordingSession:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, statement: TextClause) -> None:
        self.statements.append(str(statement))


class RecordingSessionFactory:
    def __init__(self) -> None:
        self.session = RecordingSession()

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[RecordingSession]:
        yield self.session


@pytest.mark.asyncio
async def test_mcp_database_grants_keep_catalog_read_only_and_care_plan_scoped() -> None:
    factory = RecordingSessionFactory()

    await grant_mcp_runtime_access(
        cast(AsyncSessionFactory, cast(Any, factory)),
        "advisor-catalog-mcp@project.iam",
        "advisor-care-plan-mcp@project.iam",
    )

    statements = "\n".join(factory.session.statements)
    catalog_statements = "\n".join(
        line for line in factory.session.statements if "advisor-catalog-mcp" in line
    )
    care_plan_statements = "\n".join(
        line for line in factory.session.statements if "advisor-care-plan-mcp" in line
    )
    assert "GRANT SELECT" in catalog_statements
    assert "INSERT" not in catalog_statements
    assert "care_plan" not in catalog_statements
    assert "care_plan_previews" in care_plan_statements
    assert "catalog_candidates" not in care_plan_statements
    assert "GRANT USAGE ON SCHEMA advisor" in statements


@pytest.mark.asyncio
async def test_mcp_database_grants_reject_unquoted_sql_identifiers() -> None:
    factory = RecordingSessionFactory()

    with pytest.raises(ValueError, match="invalid PostgreSQL principal"):
        await grant_mcp_runtime_access(
            cast(AsyncSessionFactory, cast(Any, factory)),
            'catalog"; DROP SCHEMA advisor; --',
            "advisor-care-plan-mcp@project.iam",
        )

    assert factory.session.statements == []
