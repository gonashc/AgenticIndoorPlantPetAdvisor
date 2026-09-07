"""Deterministic fakes for independent Engineer 2 development and tests."""

from datetime import UTC, datetime
from uuid import UUID

from advisor_api.contracts.base import Category, CostEstimate, EvidenceReference, LocalSource
from advisor_api.contracts.care_plans import CarePlan, CarePlanPreviewResponse
from advisor_api.ports.data import CandidateRecord, PreviewClaimStatus


def _evidence(entity_id: str, title: str) -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            evidence_id=f"evidence-{entity_id}",
            title=title,
            source_name="Reviewed development catalog",
            source_url=f"https://example.invalid/catalog/{entity_id}",
            reviewed_at=datetime(2026, 9, 1, tzinfo=UTC),
            content_version="fake-catalog-v1",
        ),
    )


def _cost(initial: tuple[float, float], monthly: tuple[float, float]) -> CostEstimate:
    return CostEstimate(
        initial_min=initial[0],
        initial_max=initial[1],
        monthly_min=monthly[0],
        monthly_max=monthly[1],
    )


class InMemoryCatalogRepository:
    """Small reviewed fixture catalog; never presented as current inventory."""

    def __init__(self) -> None:
        self._records = (
            CandidateRecord(
                candidate_id="plant-spider",
                category=Category.PLANT,
                name="Spider Plant",
                scientific_name="Chlorophytum comosum",
                profile="Adaptable, pet-safe foliage plant suited to newer plant owners.",
                features={
                    "light": 0.55,
                    "humidity": 0.5,
                    "temperature": 0.55,
                    "maintenance": 0.35,
                    "experience": 0.1,
                    "space": 0.3,
                },
                care_summary=(
                    "Water when the top inch of soil dries.",
                    "Use bright indirect light.",
                ),
                cost=_cost((12, 35), (2, 6)),
                evidence=_evidence("plant-spider", "Reviewed spider plant profile"),
            ),
            CandidateRecord(
                candidate_id="plant-boston-fern",
                category=Category.PLANT,
                name="Boston Fern",
                scientific_name="Nephrolepis exaltata",
                profile="Humidity-loving, pet-safe fern for attentive households.",
                features={
                    "light": 0.5,
                    "humidity": 0.9,
                    "temperature": 0.5,
                    "maintenance": 0.75,
                    "experience": 0.55,
                    "space": 0.55,
                },
                care_summary=(
                    "Keep soil consistently moist, not saturated.",
                    "Maintain higher humidity.",
                ),
                cost=_cost((18, 45), (4, 10)),
                evidence=_evidence("plant-boston-fern", "Reviewed Boston fern profile"),
            ),
            CandidateRecord(
                candidate_id="plant-parlor-palm",
                category=Category.PLANT,
                name="Parlor Palm",
                scientific_name="Chamaedorea elegans",
                profile="Pet-safe palm tolerant of moderate indoor light.",
                features={
                    "light": 0.35,
                    "humidity": 0.55,
                    "temperature": 0.6,
                    "maintenance": 0.4,
                    "experience": 0.2,
                    "space": 0.65,
                },
                care_summary=(
                    "Allow the surface soil to dry between watering.",
                    "Avoid intense direct sun.",
                ),
                cost=_cost((20, 70), (3, 9)),
                evidence=_evidence("plant-parlor-palm", "Reviewed parlor palm profile"),
            ),
            CandidateRecord(
                candidate_id="plant-pothos",
                category=Category.PLANT,
                name="Golden Pothos",
                scientific_name="Epipremnum aureum",
                profile="Low-maintenance trailing plant that is toxic if ingested.",
                features={
                    "light": 0.45,
                    "humidity": 0.45,
                    "temperature": 0.6,
                    "maintenance": 0.2,
                    "experience": 0.05,
                    "space": 0.25,
                },
                care_summary=(
                    "Water after partial soil drying.",
                    "Keep away from children and pets.",
                ),
                cost=_cost((10, 30), (2, 5)),
                evidence=_evidence("plant-pothos", "Reviewed pothos safety profile"),
                toxic_to_children=True,
                toxic_to_dogs=True,
                toxic_to_cats=True,
            ),
            CandidateRecord(
                candidate_id="dog-calm-small-adult",
                category=Category.DOG,
                name="Calm Small Adult Dog Profile",
                scientific_name=None,
                profile="An adult small-dog profile with moderate exercise needs.",
                features={"home": 0.2, "activity": 0.35, "time_alone": 0.65, "grooming": 0.4},
                care_summary=("Plan two daily walks.", "Use reward-based training and enrichment."),
                cost=_cost((250, 800), (90, 220)),
                evidence=_evidence("dog-calm-small-adult", "Reviewed small adult dog profile"),
                max_hours_alone=8,
            ),
            CandidateRecord(
                candidate_id="dog-family-medium-adult",
                category=Category.DOG,
                name="Family-Oriented Medium Adult Dog Profile",
                scientific_name=None,
                profile="A social medium-dog profile for active households.",
                features={"home": 0.55, "activity": 0.65, "time_alone": 0.45, "grooming": 0.5},
                care_summary=(
                    "Provide daily exercise and training.",
                    "Budget for preventive veterinary care.",
                ),
                cost=_cost((300, 1000), (130, 300)),
                evidence=_evidence("dog-family-medium-adult", "Reviewed family dog profile"),
                allowed_housing=frozenset({"CONDO", "HOUSE"}),
                max_hours_alone=6,
            ),
            CandidateRecord(
                candidate_id="dog-active-large-adult",
                category=Category.DOG,
                name="Active Large Adult Dog Profile",
                scientific_name=None,
                profile="A high-energy large-dog profile for experienced active owners.",
                features={"home": 0.9, "activity": 0.95, "time_alone": 0.25, "grooming": 0.65},
                care_summary=("Provide vigorous daily exercise.", "Continue structured training."),
                cost=_cost((400, 1300), (180, 400)),
                evidence=_evidence("dog-active-large-adult", "Reviewed active large dog profile"),
                allowed_housing=frozenset({"HOUSE"}),
                max_hours_alone=4,
            ),
            CandidateRecord(
                candidate_id="cat-calm-adult",
                category=Category.CAT,
                name="Calm Adult Cat Profile",
                scientific_name=None,
                profile="A balanced adult indoor-cat profile with moderate social needs.",
                features={"home": 0.25, "activity": 0.35, "time_alone": 0.8, "grooming": 0.3},
                care_summary=("Scoop litter daily.", "Provide daily interactive play."),
                cost=_cost((180, 600), (70, 180)),
                evidence=_evidence("cat-calm-adult", "Reviewed calm adult cat profile"),
                max_hours_alone=10,
            ),
            CandidateRecord(
                candidate_id="cat-playful-young",
                category=Category.CAT,
                name="Playful Young Cat Profile",
                scientific_name=None,
                profile="A social, energetic young indoor-cat profile.",
                features={"home": 0.3, "activity": 0.8, "time_alone": 0.45, "grooming": 0.35},
                care_summary=(
                    "Schedule several play sessions daily.",
                    "Provide climbing and scratching areas.",
                ),
                cost=_cost((200, 700), (80, 200)),
                evidence=_evidence("cat-playful-young", "Reviewed playful young cat profile"),
                max_hours_alone=7,
            ),
            CandidateRecord(
                candidate_id="cat-senior-independent",
                category=Category.CAT,
                name="Independent Senior Cat Profile",
                scientific_name=None,
                profile=(
                    "A lower-energy senior indoor-cat profile with added health planning needs."
                ),
                features={"home": 0.2, "activity": 0.15, "time_alone": 0.9, "grooming": 0.45},
                care_summary=(
                    "Use accessible litter and resting areas.",
                    "Plan age-appropriate veterinary visits.",
                ),
                cost=_cost((150, 500), (100, 260)),
                evidence=_evidence("cat-senior-independent", "Reviewed senior cat profile"),
                max_hours_alone=12,
            ),
        )

    async def list_candidates(self, category: Category) -> tuple[CandidateRecord, ...]:
        return tuple(record for record in self._records if record.category == category)


class InMemoryCarePlanRepository:
    def __init__(self) -> None:
        self._plans: dict[UUID, CarePlan] = {}
        self._previews: dict[UUID, tuple[CarePlanPreviewResponse, datetime | None]] = {}

    async def save_preview(self, preview: CarePlanPreviewResponse) -> CarePlanPreviewResponse:
        stored = preview.model_copy(deep=True)
        self._previews[preview.preview_id] = (stored, None)
        return stored.model_copy(deep=True)

    async def get_preview(self, preview_id: UUID) -> CarePlanPreviewResponse | None:
        entry = self._previews.get(preview_id)
        return entry[0].model_copy(deep=True) if entry is not None else None

    async def confirm_preview(
        self,
        preview_id: UUID,
        claimed_at: datetime,
        plan: CarePlan,
    ) -> PreviewClaimStatus:
        entry = self._previews.get(preview_id)
        if entry is None:
            return PreviewClaimStatus.NOT_FOUND
        preview, consumed_at = entry
        if consumed_at is not None:
            return PreviewClaimStatus.ALREADY_CONSUMED
        if preview.expires_at <= claimed_at:
            return PreviewClaimStatus.EXPIRED
        self._previews[preview_id] = (preview, claimed_at)
        self._plans[plan.plan_id] = plan.model_copy(deep=True)
        return PreviewClaimStatus.CLAIMED

    async def get(self, plan_id: UUID) -> CarePlan | None:
        plan = self._plans.get(plan_id)
        return plan.model_copy(deep=True) if plan else None

    async def update(self, plan: CarePlan, *, expected_version: int) -> CarePlan | None:
        stored = self._plans.get(plan.plan_id)
        if stored is None or stored.version != expected_version:
            return None
        updated = plan.model_copy(deep=True)
        self._plans[plan.plan_id] = updated
        return updated.model_copy(deep=True)


class UnavailableCurrentSourceGateway:
    async def find_sources(
        self,
        *,
        category: Category,
        candidate_id: str,
        zip_code: str,
    ) -> tuple[LocalSource, ...]:
        del category, candidate_id, zip_code
        return ()


class EmptyPreferenceMemory:
    async def recall(self, session_id: UUID) -> dict[str, object]:
        del session_id
        return {}

    async def delete(self, session_id: UUID) -> None:
        del session_id
