"""Idempotent loaders for reviewed demo catalog and structured safety facts."""

import re
from collections.abc import Sequence
from decimal import Decimal

from advisor_api.ports.data import CandidateRecord
from sqlalchemy import delete, text, update

from database.models import CatalogCandidateRow, CatalogEvidenceRow, PlantToxicityRow
from database.runtime import AsyncSessionFactory
from services.ingestion.toxicity import PlantToxicityDataset

DATABASE_PRINCIPAL_PATTERN = re.compile(r"[a-z0-9][a-z0-9@._-]{0,62}")


async def grant_api_runtime_access(
    session_factory: AsyncSessionFactory,
    database_user: str,
) -> None:
    """Grant only the DML privileges needed by the deployed API identity."""

    if DATABASE_PRINCIPAL_PATTERN.fullmatch(database_user) is None:
        raise ValueError("API database user has an invalid PostgreSQL principal name")
    principal = f'"{database_user}"'
    read_tables = (
        "advisor.alembic_version, advisor.catalog_candidates, advisor.catalog_evidence, "
        "advisor.knowledge_sources, advisor.knowledge_chunks, advisor.plant_toxicity"
    )
    write_tables = "advisor.care_plan_previews, advisor.care_plans, advisor.care_tasks"
    statements = (
        f"GRANT USAGE ON SCHEMA advisor TO {principal}",
        f"GRANT SELECT ON {read_tables} TO {principal}",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {write_tables} TO {principal}",
    )
    async with session_factory.begin() as session:
        for statement in statements:
            await session.execute(text(statement))


async def replace_catalog(
    session_factory: AsyncSessionFactory,
    candidates: Sequence[CandidateRecord],
    *,
    content_version: str,
) -> int:
    """Upsert the supplied catalog and replace evidence for those candidates."""

    candidate_ids = [candidate.candidate_id for candidate in candidates]
    async with session_factory.begin() as session:
        for candidate in candidates:
            row = await session.get(CatalogCandidateRow, candidate.candidate_id)
            if row is None:
                row = CatalogCandidateRow(candidate_id=candidate.candidate_id)
                session.add(row)
            row.category = candidate.category.value
            row.name = candidate.name
            row.scientific_name = candidate.scientific_name
            row.profile = candidate.profile
            row.features = dict(candidate.features)
            row.care_summary = list(candidate.care_summary)
            row.initial_min = Decimal(str(candidate.cost.initial_min))
            row.initial_max = Decimal(str(candidate.cost.initial_max))
            row.monthly_min = Decimal(str(candidate.cost.monthly_min))
            row.monthly_max = Decimal(str(candidate.cost.monthly_max))
            row.toxic_to_children = candidate.toxic_to_children
            row.toxic_to_dogs = candidate.toxic_to_dogs
            row.toxic_to_cats = candidate.toxic_to_cats
            row.allowed_housing = sorted(candidate.allowed_housing)
            row.child_compatible = candidate.child_compatible
            row.dog_compatible = candidate.dog_compatible
            row.cat_compatible = candidate.cat_compatible
            row.max_hours_alone = Decimal(str(candidate.max_hours_alone))
            row.content_version = content_version
            row.active = True

        await session.execute(
            delete(CatalogEvidenceRow).where(CatalogEvidenceRow.candidate_id.in_(candidate_ids))
        )
        session.add_all(
            [
                CatalogEvidenceRow(
                    evidence_id=evidence.evidence_id,
                    candidate_id=candidate.candidate_id,
                    title=evidence.title,
                    source_name=evidence.source_name,
                    source_url=str(evidence.source_url),
                    reviewed_at=evidence.reviewed_at,
                    content_version=evidence.content_version,
                )
                for candidate in candidates
                for evidence in candidate.evidence
            ]
        )
    return len(candidates)


async def replace_plant_toxicity(
    session_factory: AsyncSessionFactory,
    dataset: PlantToxicityDataset,
) -> int:
    """Activate one source version while retaining older versions for reconstruction."""

    source = dataset.source
    async with session_factory.begin() as session:
        await session.execute(
            update(PlantToxicityRow)
            .where(
                PlantToxicityRow.source_id == source.source_id,
                PlantToxicityRow.content_version != source.content_version,
            )
            .values(active=False)
        )
        for record in dataset.records:
            row = await session.get(PlantToxicityRow, record.toxicity_id)
            if row is None:
                row = PlantToxicityRow(toxicity_id=record.toxicity_id)
                session.add(row)
            row.common_names = record.common_names
            row.scientific_name = record.scientific_name
            row.normalized_scientific_name = record.normalized_scientific_name
            row.family = record.family
            row.animal_species = record.animal_species
            row.toxicity_status = record.toxicity_status.value
            row.source_id = source.source_id
            row.canonical_url = str(source.canonical_url)
            row.source_document_sha256 = source.source_document_sha256
            row.content_version = source.content_version
            row.trust_tier = source.trust_tier
            row.permission_status = source.permission_status
            row.reviewed_at = source.reviewed_at
            row.active = True
    return len(dataset.records)
