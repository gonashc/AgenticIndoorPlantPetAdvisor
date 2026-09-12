"""SQLAlchemy implementations of provider-neutral persistence ports."""

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from advisor_api.contracts.base import (
    Category,
    CostEstimate,
    EvidenceReference,
    RequestMetadata,
)
from advisor_api.contracts.care_plans import (
    Cadence,
    CarePlan,
    CarePlanPreviewResponse,
    CarePlanStatus,
    CareTask,
)
from advisor_api.ports.data import (
    CandidateRecord,
    PreviewClaimStatus,
)
from sqlalchemy import delete, select, update
from sqlalchemy.orm import selectinload

from database.models import (
    CarePlanPreviewRow,
    CarePlanRow,
    CareTaskRow,
    CatalogCandidateRow,
    KnowledgeChunkRow,
    KnowledgeSourceRow,
)
from database.runtime import AsyncSessionFactory
from services.ingestion.models import ApprovedContentDocument, ContentChunk, QuarantinedContent


class PostgresCatalogRepository:
    def __init__(self, session_factory: AsyncSessionFactory) -> None:
        self._sessions = session_factory

    async def list_candidates(self, category: Category) -> tuple[CandidateRecord, ...]:
        statement = (
            select(CatalogCandidateRow)
            .where(
                CatalogCandidateRow.category == category.value,
                CatalogCandidateRow.active.is_(True),
            )
            .options(selectinload(CatalogCandidateRow.evidence))
            .order_by(CatalogCandidateRow.candidate_id)
        )
        async with self._sessions() as session:
            rows = (await session.scalars(statement)).unique().all()
        return tuple(self._candidate(row) for row in rows)

    @staticmethod
    def _candidate(row: CatalogCandidateRow) -> CandidateRecord:
        evidence = tuple(
            EvidenceReference(
                evidence_id=item.evidence_id,
                title=item.title,
                source_name=item.source_name,
                source_url=item.source_url,
                reviewed_at=item.reviewed_at,
                content_version=item.content_version,
            )
            for item in sorted(row.evidence, key=lambda value: value.evidence_id)
        )
        return CandidateRecord(
            candidate_id=row.candidate_id,
            category=Category(row.category),
            name=row.name,
            scientific_name=row.scientific_name,
            profile=row.profile,
            features={key: float(value) for key, value in row.features.items()},
            care_summary=tuple(row.care_summary),
            cost=CostEstimate(
                initial_min=float(row.initial_min),
                initial_max=float(row.initial_max),
                monthly_min=float(row.monthly_min),
                monthly_max=float(row.monthly_max),
            ),
            evidence=evidence,
            toxic_to_children=row.toxic_to_children,
            toxic_to_dogs=row.toxic_to_dogs,
            toxic_to_cats=row.toxic_to_cats,
            allowed_housing=frozenset(row.allowed_housing),
            child_compatible=row.child_compatible,
            dog_compatible=row.dog_compatible,
            cat_compatible=row.cat_compatible,
            max_hours_alone=float(row.max_hours_alone),
        )


class PostgresIngestionManifestRepository:
    """Tracks reviewed source state and exact Pinecone chunk identities."""

    def __init__(self, session_factory: AsyncSessionFactory) -> None:
        self._sessions = session_factory

    async def begin_source(
        self,
        document: ApprovedContentDocument,
        chunks: Sequence[ContentChunk],
    ) -> None:
        if not chunks:
            raise ValueError("Knowledge manifests require at least one chunk")
        async with self._sessions.begin() as session:
            row = await session.get(KnowledgeSourceRow, document.source_id)
            if row is None:
                row = KnowledgeSourceRow(source_id=document.source_id)
                session.add(row)
            self._apply_document(row, document)
            row.status = "PENDING"
            row.rejection_reasons = []
            await session.execute(
                delete(KnowledgeChunkRow).where(
                    KnowledgeChunkRow.source_id == document.source_id,
                    KnowledgeChunkRow.namespace == chunks[0].namespace,
                )
            )
            session.add_all([self._chunk_row(chunk) for chunk in chunks])

    async def mark_indexed(self, source_id: str, namespace: str) -> None:
        indexed_at = datetime.now(UTC)
        async with self._sessions.begin() as session:
            await session.execute(
                update(KnowledgeSourceRow)
                .where(KnowledgeSourceRow.source_id == source_id)
                .values(status="INDEXED", updated_at=indexed_at)
            )
            await session.execute(
                update(KnowledgeChunkRow)
                .where(
                    KnowledgeChunkRow.source_id == source_id,
                    KnowledgeChunkRow.namespace == namespace,
                )
                .values(indexed_at=indexed_at, updated_at=indexed_at)
            )

    async def quarantine(
        self,
        document: ApprovedContentDocument,
        content: QuarantinedContent,
    ) -> None:
        async with self._sessions.begin() as session:
            row = await session.get(KnowledgeSourceRow, document.source_id)
            if row is None:
                row = KnowledgeSourceRow(source_id=document.source_id)
                session.add(row)
            self._apply_document(row, document)
            row.status = "QUARANTINED"
            row.rejection_reasons = list(content.reasons)

    @staticmethod
    def _apply_document(row: KnowledgeSourceRow, document: ApprovedContentDocument) -> None:
        row.category = document.category.value
        row.title = document.title
        row.publisher = document.publisher
        row.canonical_url = document.canonical_url
        row.license_id = document.license_id
        row.trust_tier = document.trust_tier.value
        row.retrieved_at = document.retrieved_at
        row.reviewed_at = document.reviewed_at
        row.approved_by = document.approved_by
        row.content_version = document.content_version
        row.checksum_sha256 = hashlib.sha256(document.text.encode()).hexdigest()
        row.metadata_json = dict(document.metadata)

    @staticmethod
    def _chunk_row(chunk: ContentChunk) -> KnowledgeChunkRow:
        return KnowledgeChunkRow(
            chunk_id=chunk.chunk_id,
            source_id=chunk.source_id,
            category=chunk.category.value,
            candidate_ids=list(chunk.candidate_ids),
            position=chunk.position,
            text_sha256=chunk.text_sha256,
            word_count=chunk.word_count,
            namespace=chunk.namespace,
            content_version=chunk.content_version,
            indexed_at=None,
            metadata_json=dict(chunk.metadata),
        )


class PostgresCarePlanRepository:
    def __init__(self, session_factory: AsyncSessionFactory) -> None:
        self._sessions = session_factory

    async def save_preview(self, preview: CarePlanPreviewResponse) -> CarePlanPreviewResponse:
        row = CarePlanPreviewRow(
            preview_id=preview.preview_id,
            owner_id=None,
            session_id=preview.session_id,
            recommendation_id=preview.recommendation_id,
            category=preview.category.value,
            item_name=preview.item_name,
            timezone=preview.timezone,
            expires_at=preview.expires_at,
            consumed_at=None,
            metadata_json=preview.metadata.model_dump(mode="json"),
            tasks_json=[task.model_dump(mode="json") for task in preview.tasks],
        )
        async with self._sessions.begin() as session:
            session.add(row)
        return preview.model_copy(deep=True)

    async def get_preview(self, preview_id: UUID) -> CarePlanPreviewResponse | None:
        statement = select(CarePlanPreviewRow).where(CarePlanPreviewRow.preview_id == preview_id)
        async with self._sessions() as session:
            row = await session.scalar(statement)
            return self._preview(row) if row is not None else None

    async def confirm_preview(
        self,
        preview_id: UUID,
        claimed_at: datetime,
        plan: CarePlan,
    ) -> PreviewClaimStatus:
        statement = (
            select(CarePlanPreviewRow)
            .where(CarePlanPreviewRow.preview_id == preview_id)
            .with_for_update()
        )
        async with self._sessions.begin() as session:
            row = await session.scalar(statement)
            if row is None:
                return PreviewClaimStatus.NOT_FOUND
            if row.consumed_at is not None:
                return PreviewClaimStatus.ALREADY_CONSUMED
            if row.expires_at <= claimed_at:
                return PreviewClaimStatus.EXPIRED
            row.consumed_at = claimed_at
            session.add(self._plan_row(plan))
            return PreviewClaimStatus.CLAIMED

    @classmethod
    def _plan_row(cls, plan: CarePlan) -> CarePlanRow:
        return CarePlanRow(
            plan_id=plan.plan_id,
            owner_id=None,
            session_id=plan.session_id,
            recommendation_id=plan.recommendation_id,
            category=plan.category.value,
            item_name=plan.item_name,
            timezone=plan.timezone,
            status=plan.status.value,
            version=plan.version,
            metadata_json=plan.metadata.model_dump(mode="json"),
            created_at=plan.created_at,
            updated_at=plan.updated_at,
            tasks=[
                cls._task_row(task, plan.plan_id, position)
                for position, task in enumerate(plan.tasks)
            ],
        )

    async def get(self, plan_id: UUID) -> CarePlan | None:
        statement = (
            select(CarePlanRow)
            .where(CarePlanRow.plan_id == plan_id)
            .options(selectinload(CarePlanRow.tasks))
        )
        async with self._sessions() as session:
            row = await session.scalar(statement)
            return self._plan(row) if row is not None else None

    async def update(self, plan: CarePlan, *, expected_version: int) -> CarePlan | None:
        statement = (
            select(CarePlanRow)
            .where(CarePlanRow.plan_id == plan.plan_id)
            .options(selectinload(CarePlanRow.tasks))
            .with_for_update()
        )
        async with self._sessions.begin() as session:
            row = await session.scalar(statement)
            if row is None or row.version != expected_version:
                return None
            row.status = plan.status.value
            row.version = plan.version
            row.metadata_json = plan.metadata.model_dump(mode="json")
            row.updated_at = plan.updated_at
            existing = {task.task_id: task for task in row.tasks}
            requested_ids = {task.task_id for task in plan.tasks}
            row.tasks[:] = [task for task in row.tasks if task.task_id in requested_ids]
            for position, task in enumerate(plan.tasks):
                task_row = existing.get(task.task_id)
                if task_row is None:
                    row.tasks.append(self._task_row(task, plan.plan_id, position))
                else:
                    task_row.position = position
                    task_row.title = task.title
                    task_row.instructions = task.instructions
                    task_row.cadence = task.cadence.value
                    task_row.next_due_on = task.next_due_on
                    task_row.completed_at = task.completed_at
        return plan.model_copy(deep=True)

    @staticmethod
    def _preview(row: CarePlanPreviewRow) -> CarePlanPreviewResponse:
        return CarePlanPreviewResponse(
            metadata=RequestMetadata.model_validate(row.metadata_json),
            preview_id=row.preview_id,
            expires_at=row.expires_at,
            session_id=row.session_id,
            recommendation_id=row.recommendation_id,
            category=Category(row.category),
            item_name=row.item_name,
            timezone=row.timezone,
            tasks=[CareTask.model_validate(task) for task in row.tasks_json],
        )

    @staticmethod
    def _task_row(task: CareTask, plan_id: UUID, position: int) -> CareTaskRow:
        return CareTaskRow(
            task_id=task.task_id,
            plan_id=plan_id,
            position=position,
            title=task.title,
            instructions=task.instructions,
            cadence=task.cadence.value,
            next_due_on=task.next_due_on,
            completed_at=task.completed_at,
        )

    @staticmethod
    def _plan(row: CarePlanRow) -> CarePlan:
        return CarePlan(
            metadata=RequestMetadata.model_validate(row.metadata_json),
            plan_id=row.plan_id,
            session_id=row.session_id,
            recommendation_id=row.recommendation_id,
            category=Category(row.category),
            item_name=row.item_name,
            timezone=row.timezone,
            status=CarePlanStatus(row.status),
            version=row.version,
            tasks=[
                CareTask(
                    task_id=task.task_id,
                    title=task.title,
                    instructions=task.instructions,
                    cadence=Cadence(task.cadence),
                    next_due_on=task.next_due_on,
                    completed_at=task.completed_at,
                )
                for task in sorted(row.tasks, key=lambda value: value.position)
            ],
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
