"""SQLAlchemy models for authoritative catalog and care-plan data."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

SCHEMA = "advisor"
OWNER_ID_COMMENT = "Internal UUID derived from the verified identity-provider issuer and subject."


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CatalogCandidateRow(TimestampMixin, Base):
    __tablename__ = "catalog_candidates"
    __table_args__ = (
        CheckConstraint("category IN ('PLANT', 'DOG', 'CAT')", name="ck_candidate_category"),
        CheckConstraint("initial_min >= 0 AND initial_max >= initial_min", name="ck_initial_cost"),
        CheckConstraint("monthly_min >= 0 AND monthly_max >= monthly_min", name="ck_monthly_cost"),
        CheckConstraint("max_hours_alone >= 0 AND max_hours_alone <= 24", name="ck_hours_alone"),
        Index("ix_catalog_candidates_category_active", "category", "active"),
        {"schema": SCHEMA},
    )

    candidate_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    category: Mapped[str] = mapped_column(String(8), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    scientific_name: Mapped[str | None] = mapped_column(String(200))
    profile: Mapped[str] = mapped_column(Text, nullable=False)
    features: Mapped[dict[str, float]] = mapped_column(JSONB, nullable=False)
    care_summary: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    initial_min: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    initial_max: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    monthly_min: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    monthly_max: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    toxic_to_children: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    toxic_to_dogs: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    toxic_to_cats: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allowed_housing: Mapped[list[str]] = mapped_column(ARRAY(String(20)), nullable=False)
    child_compatible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    dog_compatible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cat_compatible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_hours_alone: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False, default=24)
    content_version: Mapped[str] = mapped_column(String(80), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    evidence: Mapped[list["CatalogEvidenceRow"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class CatalogEvidenceRow(TimestampMixin, Base):
    __tablename__ = "catalog_evidence"
    __table_args__ = (
        Index("ix_catalog_evidence_candidate_id", "candidate_id"),
        {"schema": SCHEMA},
    )

    evidence_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.catalog_candidates.candidate_id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_version: Mapped[str] = mapped_column(String(80), nullable=False)
    candidate: Mapped[CatalogCandidateRow] = relationship(back_populates="evidence")


class KnowledgeSourceRow(TimestampMixin, Base):
    __tablename__ = "knowledge_sources"
    __table_args__ = (
        CheckConstraint("category IN ('PLANT', 'DOG', 'CAT')", name="ck_knowledge_category"),
        CheckConstraint(
            "status IN ('PENDING', 'INDEXED', 'QUARANTINED')",
            name="ck_knowledge_status",
        ),
        Index("ix_knowledge_sources_status", "status"),
        {"schema": SCHEMA},
    )

    source_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    category: Mapped[str] = mapped_column(String(8), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    publisher: Mapped[str] = mapped_column(String(240), nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    license_id: Mapped[str] = mapped_column(String(100), nullable=False)
    trust_tier: Mapped[str] = mapped_column(String(30), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_by: Mapped[str] = mapped_column(String(160), nullable=False)
    content_version: Mapped[str] = mapped_column(String(100), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    rejection_reasons: Mapped[list[str]] = mapped_column(ARRAY(String(80)), nullable=False)
    metadata_json: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    chunks: Mapped[list["KnowledgeChunkRow"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class KnowledgeChunkRow(TimestampMixin, Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("namespace", "source_id", "position", name="uq_knowledge_chunk_position"),
        CheckConstraint("position >= 0", name="ck_knowledge_chunk_position"),
        CheckConstraint("word_count > 0", name="ck_knowledge_chunk_word_count"),
        Index("ix_knowledge_chunks_namespace", "namespace"),
        Index("ix_knowledge_chunks_source_id", "source_id"),
        {"schema": SCHEMA},
    )

    chunk_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.knowledge_sources.source_id", ondelete="CASCADE"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(8), nullable=False)
    candidate_ids: Mapped[list[str]] = mapped_column(ARRAY(String(100)), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    namespace: Mapped[str] = mapped_column(String(120), nullable=False)
    content_version: Mapped[str] = mapped_column(String(100), nullable=False)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    source: Mapped[KnowledgeSourceRow] = relationship(back_populates="chunks")


class PlantToxicityRow(TimestampMixin, Base):
    """Versioned structured plant toxicity fact from a reviewed source artifact."""

    __tablename__ = "plant_toxicity"
    __table_args__ = (
        CheckConstraint(
            "animal_species IN ('DOG', 'CAT')", name="ck_plant_toxicity_animal_species"
        ),
        CheckConstraint(
            "toxicity_status IN ('TOXIC', 'NON_TOXIC_LISTED')",
            name="ck_plant_toxicity_status",
        ),
        CheckConstraint(
            "trust_tier IN ('AUTHORITATIVE', 'EXPERT_REVIEWED', 'DEMO_UNVERIFIED')",
            name="ck_plant_toxicity_trust_tier",
        ),
        Index(
            "ix_plant_toxicity_lookup",
            "animal_species",
            "normalized_scientific_name",
            "active",
        ),
        Index("ix_plant_toxicity_source_id", "source_id"),
        {"schema": SCHEMA},
    )

    toxicity_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    common_names: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    scientific_name: Mapped[str] = mapped_column(String(240), nullable=False)
    normalized_scientific_name: Mapped[str] = mapped_column(String(240), nullable=False)
    family: Mapped[str | None] = mapped_column(String(160))
    animal_species: Mapped[str] = mapped_column(String(8), nullable=False)
    toxicity_status: Mapped[str] = mapped_column(String(24), nullable=False)
    source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_document_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_version: Mapped[str] = mapped_column(String(100), nullable=False)
    trust_tier: Mapped[str] = mapped_column(String(30), nullable=False)
    permission_status: Mapped[str] = mapped_column(String(40), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CarePlanPreviewRow(TimestampMixin, Base):
    __tablename__ = "care_plan_previews"
    __table_args__ = (
        CheckConstraint("category IN ('PLANT', 'DOG', 'CAT')", name="ck_preview_category"),
        Index("ix_care_plan_previews_expires_at", "expires_at"),
        Index("ix_care_plan_previews_owner_id", "owner_id"),
        {"schema": SCHEMA},
    )

    preview_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, comment=OWNER_ID_COMMENT
    )
    session_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    recommendation_id: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(8), nullable=False)
    item_name: Mapped[str] = mapped_column(String(160), nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    tasks_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)


class CarePlanRow(TimestampMixin, Base):
    __tablename__ = "care_plans"
    __table_args__ = (
        CheckConstraint("category IN ('PLANT', 'DOG', 'CAT')", name="ck_plan_category"),
        CheckConstraint("status IN ('ACTIVE', 'PAUSED')", name="ck_plan_status"),
        CheckConstraint("version >= 1", name="ck_plan_version"),
        Index("ix_care_plans_owner_id", "owner_id"),
        Index("ix_care_plans_session_id", "session_id"),
        {"schema": SCHEMA},
    )

    plan_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, comment=OWNER_ID_COMMENT
    )
    session_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    recommendation_id: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(8), nullable=False)
    item_name: Mapped[str] = mapped_column(String(160), nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    tasks: Mapped[list["CareTaskRow"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="CareTaskRow.position",
    )


class CareTaskRow(TimestampMixin, Base):
    __tablename__ = "care_tasks"
    __table_args__ = (
        CheckConstraint(
            "cadence IN ('DAILY', 'WEEKLY', 'MONTHLY', 'QUARTERLY', 'ANNUALLY')",
            name="ck_task_cadence",
        ),
        CheckConstraint("position >= 0", name="ck_task_position"),
        Index("ix_care_tasks_plan_id", "plan_id"),
        Index("ix_care_tasks_next_due_on", "next_due_on"),
        {"schema": SCHEMA},
    )

    task_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    plan_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.care_plans.plan_id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    instructions: Mapped[str] = mapped_column(String(500), nullable=False)
    cadence: Mapped[str] = mapped_column(String(12), nullable=False)
    next_due_on: Mapped[date] = mapped_column(Date, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    plan: Mapped[CarePlanRow] = relationship(back_populates="tasks")
