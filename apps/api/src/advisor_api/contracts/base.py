"""Shared contract primitives."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContractModel(BaseModel):
    """Strict base for public contracts."""

    model_config = ConfigDict(extra="forbid")


class Category(StrEnum):
    PLANT = "PLANT"
    DOG = "DOG"
    CAT = "CAT"


class Confidence(StrEnum):
    CONFIRMED = "CONFIRMED"
    RECENTLY_OBSERVED = "RECENTLY_OBSERVED"
    UNVERIFIED = "UNVERIFIED"


class ValidationStatus(StrEnum):
    PASSED = "PASSED"
    DEGRADED = "DEGRADED"


ZipCode = Annotated[str, Field(pattern=r"^\d{5}$", examples=["10001"])]


class Destination(ContractModel):
    zip_code: ZipCode
    state_code: Annotated[str | None, Field(pattern=r"^[A-Z]{2}$")] = None


class EvidenceReference(ContractModel):
    evidence_id: str
    title: str
    source_name: str
    source_url: str
    reviewed_at: datetime
    content_version: str


class LocalSource(ContractModel):
    name: str
    source_type: str
    url: str
    distance_miles: float | None = Field(default=None, ge=0)
    verified_at: datetime
    confidence: Confidence


class CostEstimate(ContractModel):
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    initial_min: float = Field(ge=0)
    initial_max: float = Field(ge=0)
    monthly_min: float = Field(ge=0)
    monthly_max: float = Field(ge=0)

    @model_validator(mode="after")
    def ranges_are_ordered(self) -> "CostEstimate":
        if self.initial_min > self.initial_max or self.monthly_min > self.monthly_max:
            raise ValueError("Cost estimate minimums cannot exceed maximums")
        return self


class VersionInfo(ContractModel):
    api: str = "v1"
    graph: str = "recommendation-graph-v1"
    rules: str = "rules-v1"
    scoring: str = "scoring-v1"
    prompt: str = "deterministic-explanations-v1"
    model: str = "none"
    knowledge: str = "fake-catalog-v1"


class RequestMetadata(ContractModel):
    request_id: UUID
    generated_at: datetime
    versions: VersionInfo
