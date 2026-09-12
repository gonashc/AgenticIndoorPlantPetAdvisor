"""Load the demo catalog, structured toxicity facts, and approved RAG content."""

import asyncio
import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from advisor_api.adapters.in_memory import InMemoryCatalogRepository
from advisor_api.config import Settings
from advisor_api.contracts.base import Category, EvidenceReference
from advisor_api.ports.data import CandidateRecord

from database.runtime import create_database_runtime
from database.seeding import grant_api_runtime_access, replace_catalog, replace_plant_toxicity
from scripts.ingest_approved_content import run as ingest_approved_content
from services.ingestion import PlantToxicityDataset

CATALOG_VERSION = "demo-catalog-2026-09-11"
REVIEWED_AT = datetime(2026, 9, 11, tzinfo=UTC)
ASPCA_URL = "https://www.aspca.org/pet-care/aspca-poison-control/toxic-and-non-toxic-plants"
USDA_URL = "https://plants.sc.egov.usda.gov/DocumentLibrary/Txt/plantlst.txt"
CDC_DOG_URL = "https://www.cdc.gov/healthy-pets/about/dogs.html"
CDC_CAT_URL = "https://www.cdc.gov/healthy-pets/about/cats.html"


def _evidence(candidate_id: str, category: Category) -> tuple[EvidenceReference, ...]:
    if category is Category.PLANT:
        return (
            EvidenceReference(
                evidence_id=f"usda-taxonomy-{candidate_id}",
                title="USDA PLANTS taxonomy",
                source_name="USDA Natural Resources Conservation Service",
                source_url=USDA_URL,
                reviewed_at=REVIEWED_AT,
                content_version="usda-plantlst-2026-09",
            ),
            EvidenceReference(
                evidence_id=f"aspca-safety-{candidate_id}",
                title="ASPCA toxic and non-toxic plants reference",
                source_name="ASPCA Animal Poison Control Center",
                source_url=ASPCA_URL,
                reviewed_at=REVIEWED_AT,
                content_version="aspca-demo-2026-09",
            ),
        )
    source_url = CDC_DOG_URL if category is Category.DOG else CDC_CAT_URL
    animal = "dog" if category is Category.DOG else "cat"
    return (
        EvidenceReference(
            evidence_id=f"cdc-care-{candidate_id}",
            title=f"CDC healthy {animal} guidance",
            source_name="Centers for Disease Control and Prevention",
            source_url=source_url,
            reviewed_at=REVIEWED_AT,
            content_version=f"cdc-{animal}-care-2026-09",
        ),
    )


async def _catalog() -> tuple[CandidateRecord, ...]:
    repository = InMemoryCatalogRepository()
    records = []
    for category in Category:
        for candidate in await repository.list_candidates(category):
            records.append(replace(candidate, evidence=_evidence(candidate.candidate_id, category)))
    return tuple(records)


async def run() -> int:
    settings = Settings()
    if settings.database_mode == "memory":
        raise RuntimeError("Demo bootstrap requires PostgreSQL")

    toxicity_path = Path("knowledge/demo/v1/structured/aspca-dog-toxicity.json")
    toxicity = PlantToxicityDataset.model_validate_json(toxicity_path.read_text(encoding="utf-8"))
    candidates = await _catalog()

    runtime = await create_database_runtime(settings)
    try:
        catalog_count = await replace_catalog(
            runtime.session_factory,
            candidates,
            content_version=CATALOG_VERSION,
        )
        toxicity_count = await replace_plant_toxicity(runtime.session_factory, toxicity)
        api_database_user = os.environ.get("API_DATABASE_USER")
        if api_database_user:
            await grant_api_runtime_access(runtime.session_factory, api_database_user)
    finally:
        await runtime.close()

    ingestion_status = await ingest_approved_content(Path("knowledge/demo/v1/manifest.json"))
    print(f"catalog={catalog_count} toxicity={toxicity_count} knowledge_status={ingestion_status}")
    return ingestion_status


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
