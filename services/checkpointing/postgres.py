"""Official asynchronous PostgreSQL checkpointer behind one lifecycle boundary."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer


@asynccontextmanager
async def open_postgres_checkpointer(
    connection_string: str,
) -> AsyncIterator[AsyncPostgresSaver]:
    """Open and idempotently initialize the production checkpoint schema."""

    serializer = JsonPlusSerializer(allowed_msgpack_modules=[("advisor_api",), ("services",)])
    async with AsyncPostgresSaver.from_conn_string(
        connection_string, serde=serializer
    ) as checkpointer:
        await checkpointer.setup()
        yield checkpointer
