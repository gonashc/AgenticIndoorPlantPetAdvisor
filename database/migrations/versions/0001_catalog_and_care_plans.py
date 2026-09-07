"""Create authoritative catalog and care-plan tables.

Revision ID: 0001_catalog_and_care_plans
Revises: None
Create Date: 2026-09-05
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_catalog_and_care_plans"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "advisor"


def timestamp_columns() -> tuple[sa.Column[Any], sa.Column[Any]]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    op.create_table(
        "catalog_candidates",
        sa.Column("candidate_id", sa.String(length=100), primary_key=True),
        sa.Column("category", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("scientific_name", sa.String(length=200)),
        sa.Column("profile", sa.Text(), nullable=False),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("care_summary", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("initial_min", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("initial_max", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("monthly_min", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("monthly_max", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("toxic_to_children", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("toxic_to_dogs", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("toxic_to_cats", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("allowed_housing", postgresql.ARRAY(sa.String(length=20)), nullable=False),
        sa.Column("child_compatible", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("dog_compatible", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("cat_compatible", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "max_hours_alone",
            sa.Numeric(precision=4, scale=1),
            server_default="24",
            nullable=False,
        ),
        sa.Column("content_version", sa.String(length=80), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint("category IN ('PLANT', 'DOG', 'CAT')", name="ck_candidate_category"),
        sa.CheckConstraint(
            "initial_min >= 0 AND initial_max >= initial_min", name="ck_initial_cost"
        ),
        sa.CheckConstraint(
            "monthly_min >= 0 AND monthly_max >= monthly_min", name="ck_monthly_cost"
        ),
        sa.CheckConstraint("max_hours_alone >= 0 AND max_hours_alone <= 24", name="ck_hours_alone"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_catalog_candidates_category_active",
        "catalog_candidates",
        ["category", "active"],
        schema=SCHEMA,
    )
    op.create_table(
        "catalog_evidence",
        sa.Column("evidence_id", sa.String(length=120), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.String(length=100),
            sa.ForeignKey(f"{SCHEMA}.catalog_candidates.candidate_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("source_name", sa.String(length=200), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_version", sa.String(length=80), nullable=False),
        *timestamp_columns(),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_catalog_evidence_candidate_id",
        "catalog_evidence",
        ["candidate_id"],
        schema=SCHEMA,
    )
    op.create_table(
        "care_plan_previews",
        sa.Column("preview_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Expand-phase ownership column; make NOT NULL after authentication rollout.",
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_id", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=8), nullable=False),
        sa.Column("item_name", sa.String(length=160), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tasks_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint("category IN ('PLANT', 'DOG', 'CAT')", name="ck_preview_category"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_care_plan_previews_expires_at",
        "care_plan_previews",
        ["expires_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_care_plan_previews_owner_id",
        "care_plan_previews",
        ["owner_id"],
        schema=SCHEMA,
    )
    op.create_table(
        "care_plans",
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Expand-phase ownership column; make NOT NULL after authentication rollout.",
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_id", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=8), nullable=False),
        sa.Column("item_name", sa.String(length=160), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint("category IN ('PLANT', 'DOG', 'CAT')", name="ck_plan_category"),
        sa.CheckConstraint("status IN ('ACTIVE', 'PAUSED')", name="ck_plan_status"),
        sa.CheckConstraint("version >= 1", name="ck_plan_version"),
        schema=SCHEMA,
    )
    op.create_index("ix_care_plans_owner_id", "care_plans", ["owner_id"], schema=SCHEMA)
    op.create_index("ix_care_plans_session_id", "care_plans", ["session_id"], schema=SCHEMA)
    op.create_table(
        "care_tasks",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.care_plans.plan_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("instructions", sa.String(length=500), nullable=False),
        sa.Column("cadence", sa.String(length=12), nullable=False),
        sa.Column("next_due_on", sa.Date(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        *timestamp_columns(),
        sa.CheckConstraint(
            "cadence IN ('DAILY', 'WEEKLY', 'MONTHLY', 'QUARTERLY', 'ANNUALLY')",
            name="ck_task_cadence",
        ),
        sa.CheckConstraint("position >= 0", name="ck_task_position"),
        schema=SCHEMA,
    )
    op.create_index("ix_care_tasks_plan_id", "care_tasks", ["plan_id"], schema=SCHEMA)
    op.create_index("ix_care_tasks_next_due_on", "care_tasks", ["next_due_on"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("care_tasks", schema=SCHEMA)
    op.drop_table("care_plans", schema=SCHEMA)
    op.drop_table("care_plan_previews", schema=SCHEMA)
    op.drop_table("catalog_evidence", schema=SCHEMA)
    op.drop_table("catalog_candidates", schema=SCHEMA)
