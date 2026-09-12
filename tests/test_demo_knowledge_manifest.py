"""Regression checks for the source-controlled demo knowledge pack."""

from pathlib import Path

from advisor_api.contracts.base import Category

from scripts.ingest_approved_content import load_manifest


def test_demo_manifest_has_approved_evidence_for_every_cat_profile() -> None:
    _, documents = load_manifest(Path("knowledge/demo/v1/manifest.json"))

    cat_documents = [document for document in documents if document.category is Category.CAT]

    assert len(cat_documents) == 1
    assert cat_documents[0].source_id == "cdc-cat-selection-care-2026-06"
    assert set(cat_documents[0].candidate_ids) == {
        "cat-calm-adult",
        "cat-playful-young",
        "cat-senior-independent",
    }
    assert cat_documents[0].canonical_url == "https://www.cdc.gov/healthy-pets/about/cats.html"
