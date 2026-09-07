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
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

SCHEMA = "advisor"


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


class CarePlanPreviewRow(TimestampMixin, Base):
    __tablename__ = "care_plan_previews"
    __table_args__ = (
        CheckConstraint("category IN ('PLANT', 'DOG', 'CAT')", name="ck_preview_category"),
        Index("ix_care_plan_previews_expires_at", "expires_at"),
        Index("ix_care_plan_previews_owner_id", "owner_id"),
        {"schema": SCHEMA},
    )

    preview_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
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
    owner_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
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
