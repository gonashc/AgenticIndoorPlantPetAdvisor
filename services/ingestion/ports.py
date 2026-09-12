"""Storage boundaries for the approved-content ingestion workflow."""

from collections.abc import Sequence
from typing import Protocol

from services.ingestion.models import ApprovedContentDocument, ContentChunk, QuarantinedContent


class KnowledgeIndexWriter(Protocol):
    async def replace_source(
        self,
        *,
        namespace: str,
        source_id: str,
        chunks: Sequence[ContentChunk],
    ) -> None: ...


class IngestionManifestRepository(Protocol):
    async def begin_source(
        self,
        document: ApprovedContentDocument,
        chunks: Sequence[ContentChunk],
    ) -> None: ...

    async def mark_indexed(self, source_id: str, namespace: str) -> None: ...

    async def quarantine(
        self,
        document: ApprovedContentDocument,
        content: QuarantinedContent,
    ) -> None: ...


class InMemoryIngestionManifestRepository:
    def __init__(self) -> None:
        self.pending: dict[str, tuple[ContentChunk, ...]] = {}
        self.indexed: set[tuple[str, str]] = set()
        self.quarantined: list[QuarantinedContent] = []

    async def begin_source(
        self,
        document: ApprovedContentDocument,
        chunks: Sequence[ContentChunk],
    ) -> None:
        self.pending[document.source_id] = tuple(chunks)

    async def mark_indexed(self, source_id: str, namespace: str) -> None:
        self.indexed.add((source_id, namespace))

    async def quarantine(
        self,
        document: ApprovedContentDocument,
        content: QuarantinedContent,
    ) -> None:
        del document
        self.quarantined.append(content)


class InMemoryKnowledgeIndexWriter:
    def __init__(self) -> None:
        self.chunks: dict[tuple[str, str], tuple[ContentChunk, ...]] = {}

    async def replace_source(
        self,
        *,
        namespace: str,
        source_id: str,
        chunks: Sequence[ContentChunk],
    ) -> None:
        self.chunks[(namespace, source_id)] = tuple(chunks)
