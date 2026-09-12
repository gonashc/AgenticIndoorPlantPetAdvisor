"""Strict, provider-neutral contracts for authoritative catalog reads."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class McpContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CatalogCost(McpContract):
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    initial_min: float = Field(ge=0)
    initial_max: float = Field(ge=0)
    monthly_min: float = Field(ge=0)
    monthly_max: float = Field(ge=0)


class CatalogProfile(McpContract):
    candidate_id: str
    category: Literal["PLANT", "DOG", "CAT"]
    name: str
    scientific_name: str | None
    profile: str
    care_summary: list[str]
    cost: CatalogCost
    content_version: str


class CatalogConstraints(McpContract):
    candidate_id: str
    category: Literal["PLANT", "DOG", "CAT"]
    toxic_to_children: bool
    toxic_to_dogs: bool
    toxic_to_cats: bool
    allowed_housing: list[str]
    child_compatible: bool
    dog_compatible: bool
    cat_compatible: bool
    max_hours_alone: float = Field(ge=0, le=24)
    content_version: str


class ProvenanceRecord(McpContract):
    evidence_id: str
    title: str
    source_name: str
    source_url: str
    reviewed_at: datetime
    content_version: str


class ToxicityFact(McpContract):
    scientific_name: str
    animal_species: Literal["DOG", "CAT"]
    classification: Literal["TOXIC", "NON_TOXIC_LISTED"]


class ProfilesResult(McpContract):
    category: Literal["PLANT", "DOG", "CAT"]
    profiles: list[CatalogProfile] = Field(max_length=10)


class ConstraintsResult(McpContract):
    constraints: CatalogConstraints


class ProvenanceResult(McpContract):
    candidate_id: str
    records: list[ProvenanceRecord] = Field(max_length=20)


class ToxicityResult(McpContract):
    facts: list[ToxicityFact] = Field(max_length=20)
    notice: Literal[
        "Only reviewed matching records are returned; an absent record does not establish safety."
    ] = "Only reviewed matching records are returned; an absent record does not establish safety."
