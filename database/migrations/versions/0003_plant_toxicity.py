"""Add versioned structured plant toxicity facts.

Revision ID: 0003_plant_toxicity
Revises: 0002_knowledge_manifest
Create Date: 2026-09-11
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_plant_toxicity"
down_revision: str | None = "0002_knowledge_manifest"
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
        "plant_toxicity",
        sa.Column("toxicity_id", sa.String(length=64), primary_key=True),
        sa.Column("common_names", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("scientific_name", sa.String(length=240), nullable=False),
        sa.Column("normalized_scientific_name", sa.String(length=240), nullable=False),
        sa.Column("family", sa.String(length=160)),
        sa.Column("animal_species", sa.String(length=8), nullable=False),
        sa.Column("toxicity_status", sa.String(length=24), nullable=False),
        sa.Column("source_id", sa.String(length=160), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("source_document_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_version", sa.String(length=100), nullable=False),
        sa.Column("trust_tier", sa.String(length=30), nullable=False),
        sa.Column("permission_status", sa.String(length=40), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint(
            "animal_species IN ('DOG', 'CAT')", name="ck_plant_toxicity_animal_species"
        ),
        sa.CheckConstraint(
            "toxicity_status IN ('TOXIC', 'NON_TOXIC_LISTED')",
            name="ck_plant_toxicity_status",
        ),
        sa.CheckConstraint(
            "trust_tier IN ('AUTHORITATIVE', 'EXPERT_REVIEWED', 'DEMO_UNVERIFIED')",
            name="ck_plant_toxicity_trust_tier",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_plant_toxicity_lookup",
        "plant_toxicity",
        ["animal_species", "normalized_scientific_name", "active"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_plant_toxicity_source_id",
        "plant_toxicity",
        ["source_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("plant_toxicity", schema=SCHEMA)
