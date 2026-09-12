"""MCP server exposing bounded reads from the authoritative PostgreSQL catalog."""

import re
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal, cast

from advisor_api.contracts.base import Category
from advisor_api.ports.data import (
    CandidateRecord,
    CatalogRepository,
    PlantToxicityRepository,
)
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from database.repositories import PostgresCatalogRepository, PostgresPlantToxicityRepository
from database.runtime import DatabaseRuntime, create_database_runtime
from services.catalog_mcp.config import CatalogMcpSettings
from services.catalog_mcp.contracts import (
    CatalogConstraints,
    CatalogCost,
    CatalogProfile,
    ConstraintsResult,
    ProfilesResult,
    ProvenanceRecord,
    ProvenanceResult,
    ToxicityFact,
    ToxicityResult,
)

_CANDIDATE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,99}$")
_SCIENTIFIC_NAME = re.compile(r"^[A-Za-z][A-Za-z .()'\-]{1,238}$")
CATALOG_SCHEMA_CAPABILITIES = frozenset(
    {
        "catalog_candidates.candidate_id",
        "catalog_candidates.category",
        "catalog_candidates.active",
        "catalog_evidence.candidate_id",
        "catalog_evidence.source_url",
        "plant_toxicity.normalized_scientific_name",
        "plant_toxicity.animal_species",
        "plant_toxicity.toxicity_status",
        "plant_toxicity.active",
    }
)


@dataclass(slots=True)
class CatalogMcpState:
    catalog: CatalogRepository
    toxicity: PlantToxicityRepository
    database: DatabaseRuntime | None


@dataclass(slots=True)
class RuntimeProbe:
    database: DatabaseRuntime | None = None


def create_server(
    settings: CatalogMcpSettings | None = None,
    catalog: CatalogRepository | None = None,
    toxicity: PlantToxicityRepository | None = None,
) -> MCPServer[CatalogMcpState]:
    resolved = settings or CatalogMcpSettings()
    if (catalog is None) != (toxicity is None):
        raise ValueError("Catalog and toxicity repositories must be supplied together")
    probe = RuntimeProbe()

    @asynccontextmanager
    async def lifespan(_: MCPServer[CatalogMcpState]) -> AsyncIterator[CatalogMcpState]:
        if catalog is not None and toxicity is not None:
            yield CatalogMcpState(catalog=catalog, toxicity=toxicity, database=None)
            return
        runtime = await create_database_runtime(resolved)
        probe.database = runtime
        try:
            await runtime.verify(CATALOG_SCHEMA_CAPABILITIES)
            yield CatalogMcpState(
                catalog=PostgresCatalogRepository(runtime.session_factory),
                toxicity=PostgresPlantToxicityRepository(
                    runtime.session_factory,
                    resolved.allowed_trust_tiers(),
                ),
                database=runtime,
            )
        finally:
            probe.database = None
            await runtime.close()

    server: MCPServer[CatalogMcpState] = MCPServer(
        name="advisor-catalog",
        title="Indoor Plant and Pet Advisor Catalog Service",
        description=(
            "Returns reviewed profiles, deterministic constraints, toxicity facts, and provenance."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    @server.tool(
        name="get_profiles",
        description=(
            "Return up to ten exact approved profiles from one already-selected category. "
            "This tool cannot rank candidates or choose a category."
        ),
        structured_output=True,
    )
    async def get_profiles(
        category: str,
        candidate_ids: list[str],
        ctx: Context[CatalogMcpState],
    ) -> ProfilesResult:
        selected_category = _category(category)
        ids = _candidate_ids(candidate_ids)
        candidates = await ctx.request_context.lifespan_context.catalog.list_candidates(
            selected_category
        )
        selected = _select(candidates, ids)
        return ProfilesResult(
            category=selected_category.value,
            profiles=[_profile(item) for item in selected],
        )

    @server.tool(
        name="get_constraints",
        description=(
            "Return deterministic safety and household constraints for one exact candidate. "
            "The result is authoritative and cannot be overridden by an LLM."
        ),
        structured_output=True,
    )
    async def get_constraints(
        category: str,
        candidate_id: str,
        ctx: Context[CatalogMcpState],
    ) -> ConstraintsResult:
        candidate = await _one_candidate(ctx, _category(category), candidate_id)
        return ConstraintsResult(constraints=_constraints(candidate))

    @server.tool(
        name="get_provenance",
        description="Return reviewed source provenance for one exact catalog candidate.",
        structured_output=True,
    )
    async def get_provenance(
        category: str,
        candidate_id: str,
        ctx: Context[CatalogMcpState],
    ) -> ProvenanceResult:
        candidate = await _one_candidate(ctx, _category(category), candidate_id)
        return ProvenanceResult(
            candidate_id=candidate.candidate_id,
            records=[
                ProvenanceRecord(
                    evidence_id=item.evidence_id,
                    title=item.title,
                    source_name=item.source_name,
                    source_url=item.source_url,
                    reviewed_at=item.reviewed_at,
                    content_version=item.content_version,
                )
                for item in candidate.evidence
            ],
        )

    @server.tool(
        name="get_toxicity",
        description=(
            "Return matching reviewed structured plant-toxicity classifications. An omitted "
            "classification must never be interpreted as safe."
        ),
        structured_output=True,
    )
    async def get_toxicity(
        scientific_names: list[str],
        animal_species: list[str],
        ctx: Context[CatalogMcpState],
    ) -> ToxicityResult:
        names = _scientific_names(scientific_names)
        species = _animal_species(animal_species)
        results = await ctx.request_context.lifespan_context.toxicity.classify(names, species)
        facts = [
            ToxicityFact(
                scientific_name=name,
                animal_species=cast(Literal["DOG", "CAT"], animal),
                classification=results[(animal, _normalize_scientific_name(name))].value,
            )
            for name in names
            for animal in species
            if (animal, _normalize_scientific_name(name)) in results
        ]
        return ToxicityResult(facts=facts)

    @server.custom_route(  # type: ignore[untyped-decorator]
        "/health", methods=["GET"], include_in_schema=False
    )
    async def health(_: Request) -> Response:
        if catalog is not None:
            return JSONResponse({"status": "ok", "service": "advisor-catalog"})
        if probe.database is None:
            return JSONResponse(
                {"status": "unavailable", "service": "advisor-catalog"}, status_code=503
            )
        try:
            await probe.database.ping()
        except Exception:
            return JSONResponse(
                {"status": "unavailable", "service": "advisor-catalog"}, status_code=503
            )
        return JSONResponse({"status": "ok", "service": "advisor-catalog"})

    return server


def create_app(settings: CatalogMcpSettings | None = None) -> Starlette:
    resolved = settings or CatalogMcpSettings()
    server = create_server(resolved)
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=resolved.allowed_hosts(),
        allowed_origins=[],
    )
    return server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        max_request_body_size=64 * 1024,
        transport_security=security,
        host="0.0.0.0",
    )


def _category(value: str) -> Category:
    try:
        return Category(value)
    except ValueError as error:
        raise ValueError("category must be PLANT, DOG, or CAT") from error


def _candidate_ids(values: list[str]) -> tuple[str, ...]:
    if not 1 <= len(values) <= 10:
        raise ValueError("candidate_ids must contain between one and ten values")
    if len(values) != len(set(values)) or any(not _CANDIDATE_ID.fullmatch(item) for item in values):
        raise ValueError("candidate_ids must be unique valid identifiers")
    return tuple(values)


def _scientific_names(values: list[str]) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values)
    if not 1 <= len(normalized) <= 10:
        raise ValueError("scientific_names must contain between one and ten values")
    if len(normalized) != len({value.casefold() for value in normalized}) or any(
        not _SCIENTIFIC_NAME.fullmatch(value) for value in normalized
    ):
        raise ValueError("scientific_names must be unique valid names")
    return normalized


def _normalize_scientific_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _animal_species(values: list[str]) -> tuple[str, ...]:
    normalized = tuple(value.upper() for value in values)
    if not normalized or len(normalized) > 2 or len(normalized) != len(set(normalized)):
        raise ValueError("animal_species must contain one or two unique values")
    if set(normalized).difference({"DOG", "CAT"}):
        raise ValueError("animal_species accepts only DOG or CAT")
    return normalized


def _select(
    candidates: Sequence[CandidateRecord], candidate_ids: Sequence[str]
) -> tuple[CandidateRecord, ...]:
    by_id = {item.candidate_id: item for item in candidates}
    missing = [identifier for identifier in candidate_ids if identifier not in by_id]
    if missing:
        raise ValueError("One or more candidates do not exist in the selected category")
    return tuple(by_id[identifier] for identifier in candidate_ids)


async def _one_candidate(
    ctx: Context[CatalogMcpState], category: Category, candidate_id: str
) -> CandidateRecord:
    ids = _candidate_ids([candidate_id])
    candidates = await ctx.request_context.lifespan_context.catalog.list_candidates(category)
    return _select(candidates, ids)[0]


def _profile(candidate: CandidateRecord) -> CatalogProfile:
    return CatalogProfile(
        candidate_id=candidate.candidate_id,
        category=candidate.category.value,
        name=candidate.name,
        scientific_name=candidate.scientific_name,
        profile=candidate.profile,
        care_summary=list(candidate.care_summary),
        cost=CatalogCost(**candidate.cost.model_dump()),
        content_version=candidate.content_version,
    )


def _constraints(candidate: CandidateRecord) -> CatalogConstraints:
    return CatalogConstraints(
        candidate_id=candidate.candidate_id,
        category=candidate.category.value,
        toxic_to_children=candidate.toxic_to_children,
        toxic_to_dogs=candidate.toxic_to_dogs,
        toxic_to_cats=candidate.toxic_to_cats,
        allowed_housing=sorted(candidate.allowed_housing),
        child_compatible=candidate.child_compatible,
        dog_compatible=candidate.dog_compatible,
        cat_compatible=candidate.cat_compatible,
        max_hours_alone=candidate.max_hours_alone,
        content_version=candidate.content_version,
    )
