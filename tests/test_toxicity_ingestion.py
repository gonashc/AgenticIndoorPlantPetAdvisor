"""Structured toxicity extraction and fixture validation."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from services.ingestion.toxicity import (
    PlantToxicityDataset,
    PlantToxicityRecord,
    ToxicityStatus,
)

FIXTURE = Path("knowledge/demo/v1/structured/aspca-dog-toxicity.json")


def test_generated_aspca_fixture_is_versioned_and_normalized() -> None:
    dataset = PlantToxicityDataset.model_validate_json(FIXTURE.read_text(encoding="utf-8"))

    assert len(dataset.records) == 161
    assert dataset.source.trust_tier == "DEMO_UNVERIFIED"
    assert dataset.source.permission_status == "SOURCE_PERMISSION_PENDING"
    assert dataset.source.content_version.startswith("aspca-docx-")
    assert sum(record.toxicity_status is ToxicityStatus.TOXIC for record in dataset.records) == 123
    assert (
        sum(record.toxicity_status is ToxicityStatus.NON_TOXIC_LISTED for record in dataset.records)
        == 38
    )
    assert len({record.toxicity_id for record in dataset.records}) == len(dataset.records)


def test_dataset_rejects_conflicting_status_for_same_species_and_plant() -> None:
    source = PlantToxicityDataset.model_validate_json(FIXTURE.read_text(encoding="utf-8")).source
    base = {
        "common_names": ["Example"],
        "scientific_name": "Exemplum plantus",
        "normalized_scientific_name": "exemplum plantus",
    }

    with pytest.raises(ValidationError, match="Conflicting toxicity classifications"):
        PlantToxicityDataset(
            source=source,
            records=[
                PlantToxicityRecord(
                    toxicity_id="1" * 40,
                    toxicity_status=ToxicityStatus.TOXIC,
                    **base,
                ),
                PlantToxicityRecord(
                    toxicity_id="2" * 40,
                    toxicity_status=ToxicityStatus.NON_TOXIC_LISTED,
                    **base,
                ),
            ],
        )
