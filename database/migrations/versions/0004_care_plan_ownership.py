"""Enforce non-null ownership for care-plan state.

Revision ID: 0004_care_plan_ownership
Revises: 0003_plant_toxicity
Create Date: 2026-09-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_care_plan_ownership"
down_revision: str | None = "0003_plant_toxicity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "advisor"
LEGACY_OWNER_ID = "00000000-0000-0000-0000-000000000000"
OWNER_COMMENT = "Internal UUID derived from the verified identity-provider issuer and subject."


def upgrade() -> None:
    # Existing anonymous demo records are retained but assigned to an unreachable
    # legacy principal. They cannot be claimed by an authenticated end user.
    for table in ("care_plan_previews", "care_plans"):
        op.execute(
            f"UPDATE {SCHEMA}.{table} "
            f"SET owner_id = '{LEGACY_OWNER_ID}'::uuid WHERE owner_id IS NULL"
        )
        op.alter_column(
            table,
            "owner_id",
            schema=SCHEMA,
            nullable=False,
            comment=OWNER_COMMENT,
        )


def downgrade() -> None:
    for table in ("care_plans", "care_plan_previews"):
        op.alter_column(
            table,
            "owner_id",
            schema=SCHEMA,
            nullable=True,
            comment="Expand-phase ownership column; make NOT NULL after authentication rollout.",
        )
