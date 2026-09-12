"""Add approved knowledge source registry and chunk manifest.

Revision ID: 0002_knowledge_manifest
Revises: 0001_catalog_and_care_plans
Create Date: 2026-09-09
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_knowledge_manifest"
down_revision: str | None = "0001_catalog_and_care_plans"
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
    op.create_table(
        "knowledge_sources",
        sa.Column("source_id", sa.String(length=160), primary_key=True),
        sa.Column("category", sa.String(length=8), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("publisher", sa.String(length=240), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("license_id", sa.String(length=100), nullable=False),
        sa.Column("trust_tier", sa.String(length=30), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by", sa.String(length=160), nullable=False),
        sa.Column("content_version", sa.String(length=100), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("rejection_reasons", postgresql.ARRAY(sa.String(length=80)), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        *timestamp_columns(),
        sa.CheckConstraint("category IN ('PLANT', 'DOG', 'CAT')", name="ck_knowledge_category"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'INDEXED', 'QUARANTINED')",
            name="ck_knowledge_status",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_knowledge_sources_status", "knowledge_sources", ["status"], schema=SCHEMA)
    op.create_table(
        "knowledge_chunks",
        sa.Column("chunk_id", sa.String(length=40), primary_key=True),
        sa.Column(
            "source_id",
            sa.String(length=160),
            sa.ForeignKey(f"{SCHEMA}.knowledge_sources.source_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(length=8), nullable=False),
        sa.Column("candidate_ids", postgresql.ARRAY(sa.String(length=100)), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("namespace", sa.String(length=120), nullable=False),
        sa.Column("content_version", sa.String(length=100), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        *timestamp_columns(),
        sa.UniqueConstraint(
            "namespace", "source_id", "position", name="uq_knowledge_chunk_position"
        ),
        sa.CheckConstraint("position >= 0", name="ck_knowledge_chunk_position"),
        sa.CheckConstraint("word_count > 0", name="ck_knowledge_chunk_word_count"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_knowledge_chunks_namespace", "knowledge_chunks", ["namespace"], schema=SCHEMA
    )
    op.create_index(
        "ix_knowledge_chunks_source_id", "knowledge_chunks", ["source_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_table("knowledge_chunks", schema=SCHEMA)
    op.drop_table("knowledge_sources", schema=SCHEMA)
