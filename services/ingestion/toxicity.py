"""Normalize a reviewed DOCX plant list into versioned structured toxicity facts."""

import hashlib
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

WORD_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class ToxicityStatus(StrEnum):
    TOXIC = "TOXIC"
    NON_TOXIC_LISTED = "NON_TOXIC_LISTED"


class ToxicitySource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    title: str
    publisher: str
    canonical_url: HttpUrl
    source_document_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_version: str
    trust_tier: str = "DEMO_UNVERIFIED"
    permission_status: str = "SOURCE_PERMISSION_PENDING"
    reviewed_at: datetime


class PlantToxicityRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    toxicity_id: str = Field(pattern=r"^[a-f0-9]{40}$")
    common_names: list[str] = Field(min_length=1)
    scientific_name: str
    normalized_scientific_name: str
    family: str | None = None
    animal_species: str = "DOG"
    toxicity_status: ToxicityStatus


class PlantToxicityDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: ToxicitySource
    records: list[PlantToxicityRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def scientific_names_do_not_conflict(self) -> "PlantToxicityDataset":
        statuses: dict[tuple[str, str], set[ToxicityStatus]] = defaultdict(set)
        for record in self.records:
            statuses[(record.animal_species, record.normalized_scientific_name)].add(
                record.toxicity_status
            )
        conflicts = sorted(name for (_, name), values in statuses.items() if len(values) > 1)
        if conflicts:
            raise ValueError("Conflicting toxicity classifications: " + ", ".join(conflicts))
        return self


def extract_docx_tables(path: Path) -> tuple[tuple[tuple[str, ...], ...], ...]:
    """Read visible table cell text without executing macros or embedded content."""

    with ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    tables: list[tuple[tuple[str, ...], ...]] = []
    for table in root.findall(f".//{WORD_NAMESPACE}tbl"):
        rows: list[tuple[str, ...]] = []
        for row in table.findall(f"./{WORD_NAMESPACE}tr"):
            cells = tuple(_node_text(cell) for cell in row.findall(f"./{WORD_NAMESPACE}tc"))
            if any(cells):
                rows.append(cells)
        tables.append(tuple(rows))
    return tuple(tables)


def build_aspca_dog_dataset(path: Path, *, reviewed_at: datetime) -> PlantToxicityDataset:
    tables = extract_docx_tables(path)
    if len(tables) != 2:
        raise ValueError(f"Expected toxic and non-toxic tables, found {len(tables)}")
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    content_version = f"aspca-docx-{checksum[:12]}"
    source = ToxicitySource(
        source_id="aspca-dog-plant-toxicity-demo",
        title="ASPCA toxic and non-toxic plant compilation for dogs",
        publisher="ASPCA Animal Poison Control Center",
        canonical_url=HttpUrl(
            "https://www.aspca.org/pet-care/aspca-poison-control/toxic-and-non-toxic-plants"
        ),
        source_document_sha256=checksum,
        content_version=content_version,
        reviewed_at=reviewed_at,
    )
    records: list[PlantToxicityRecord] = []
    for table, status in zip(
        tables,
        (ToxicityStatus.TOXIC, ToxicityStatus.NON_TOXIC_LISTED),
        strict=True,
    ):
        records.extend(_normalize_table(table, status, source))
    return PlantToxicityDataset(source=source, records=sorted(records, key=_record_sort_key))


def _normalize_table(
    table: tuple[tuple[str, ...], ...],
    status: ToxicityStatus,
    source: ToxicitySource,
) -> list[PlantToxicityRecord]:
    if not table or tuple(value.casefold() for value in table[0][:3]) != (
        "common name",
        "scientific name",
        "family",
    ):
        raise ValueError("Unexpected toxicity table header")
    grouped: dict[str, list[tuple[str, str, str | None]]] = defaultdict(list)
    for position, row in enumerate(table[1:], start=2):
        if len(row) < 3 or not row[0].strip() or not row[1].strip():
            raise ValueError(f"Invalid toxicity row {position}")
        common_name = _clean_text(row[0])
        scientific_name = _clean_text(row[1])
        family = _clean_optional(row[2])
        grouped[_normalize_scientific_name(scientific_name)].append(
            (common_name, scientific_name, family)
        )

    records: list[PlantToxicityRecord] = []
    for normalized_name, values in grouped.items():
        common_names = sorted({value[0] for value in values}, key=str.casefold)
        scientific_names = sorted({value[1] for value in values}, key=str.casefold)
        families = sorted({value[2] for value in values if value[2]}, key=str.casefold)
        identity = "|".join(
            (
                source.source_id,
                source.content_version,
                "DOG",
                status.value,
                normalized_name,
            )
        )
        records.append(
            PlantToxicityRecord(
                toxicity_id=hashlib.sha1(identity.encode(), usedforsecurity=False).hexdigest(),
                common_names=common_names,
                scientific_name=scientific_names[0],
                normalized_scientific_name=normalized_name,
                family=families[0] if families else None,
                toxicity_status=status,
            )
        )
    return records


def _node_text(node: ElementTree.Element) -> str:
    return "".join(child.text or "" for child in node.iter(f"{WORD_NAMESPACE}t")).strip()


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def _clean_optional(value: str) -> str | None:
    cleaned = _clean_text(value)
    return None if not cleaned or "\ufffd" in cleaned else cleaned


def _normalize_scientific_name(value: str) -> str:
    return _clean_text(value).casefold().rstrip(".")


def _record_sort_key(record: PlantToxicityRecord) -> tuple[str, str]:
    return record.toxicity_status.value, record.normalized_scientific_name
