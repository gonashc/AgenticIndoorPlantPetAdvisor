"""Care-plan application behavior with an explicit confirmation boundary."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from advisor_api.contracts.base import Category, RequestMetadata, VersionInfo
from advisor_api.contracts.care_plans import (
    Cadence,
    CarePlan,
    CarePlanCreateRequest,
    CarePlanPreviewRequest,
    CarePlanPreviewResponse,
    CarePlanStatus,
    CarePlanUpdateRequest,
    CareTask,
)
from advisor_api.http.errors import ConflictError, NotFoundError
from advisor_api.ports.data import CarePlanRepository


class CarePlanService:
    def __init__(self, repository: CarePlanRepository) -> None:
        self._repository = repository
        self._previews: dict[UUID, CarePlanPreviewResponse] = {}

    def preview(self, request: CarePlanPreviewRequest, request_id: UUID) -> CarePlanPreviewResponse:
        now = datetime.now(UTC)
        preview = CarePlanPreviewResponse(
            metadata=self._metadata(request_id, now),
            preview_id=uuid4(),
            expires_at=now + timedelta(minutes=30),
            session_id=request.session_id,
            recommendation_id=request.recommendation_id,
            category=request.category,
            item_name=request.item_name,
            timezone=request.timezone,
            tasks=self._tasks(request),
        )
        self._previews[preview.preview_id] = preview
        return preview

    async def create(self, request: CarePlanCreateRequest, request_id: UUID) -> CarePlan:
        preview = self._previews.get(request.preview_id)
        if preview is None:
            raise NotFoundError("care_plan_preview", str(request.preview_id))
        now = datetime.now(UTC)
        if preview.expires_at <= now:
            self._previews.pop(request.preview_id, None)
            raise ConflictError("CARE_PLAN_PREVIEW_EXPIRED", "The care-plan preview has expired.")
        plan = CarePlan(
            metadata=self._metadata(request_id, now),
            plan_id=uuid4(),
            session_id=preview.session_id,
            recommendation_id=preview.recommendation_id,
            category=preview.category,
            item_name=preview.item_name,
            timezone=preview.timezone,
            status=CarePlanStatus.ACTIVE,
            tasks=preview.tasks,
            created_at=now,
            updated_at=now,
        )
        self._previews.pop(request.preview_id, None)
        return await self._repository.save(plan)

    async def get(self, plan_id: UUID, request_id: UUID | None = None) -> CarePlan:
        plan = await self._repository.get(plan_id)
        if plan is None:
            raise NotFoundError("care_plan", str(plan_id))
        if request_id is not None:
            plan = plan.model_copy(
                update={"metadata": self._metadata(request_id, datetime.now(UTC))}
            )
        return plan

    async def update(
        self,
        plan_id: UUID,
        request: CarePlanUpdateRequest,
        request_id: UUID,
    ) -> CarePlan:
        plan = await self.get(plan_id)
        now = datetime.now(UTC)
        updated = plan.model_copy(
            update={
                "metadata": self._metadata(request_id, now),
                "status": request.status,
                "updated_at": now,
            }
        )
        return await self._repository.update(updated)

    async def complete_task(self, plan_id: UUID, task_id: UUID, request_id: UUID) -> CarePlan:
        plan = await self.get(plan_id)
        if plan.status == CarePlanStatus.PAUSED:
            raise ConflictError("CARE_PLAN_PAUSED", "Tasks cannot be completed on a paused plan.")
        now = datetime.now(UTC)
        found = False
        tasks: list[CareTask] = []
        for task in plan.tasks:
            if task.task_id == task_id:
                found = True
                tasks.append(task.model_copy(update={"completed_at": now}))
            else:
                tasks.append(task)
        if not found:
            raise NotFoundError("care_task", str(task_id))
        updated = plan.model_copy(
            update={
                "metadata": self._metadata(request_id, now),
                "tasks": tasks,
                "updated_at": now,
            }
        )
        return await self._repository.update(updated)

    @staticmethod
    def _metadata(request_id: UUID, generated_at: datetime) -> RequestMetadata:
        return RequestMetadata(
            request_id=request_id,
            generated_at=generated_at,
            versions=VersionInfo(),
        )

    @staticmethod
    def _tasks(request: CarePlanPreviewRequest) -> list[CareTask]:
        definitions = {
            Category.PLANT: (
                (
                    "Check soil moisture",
                    "Water only when the plant-specific soil trigger is met.",
                    Cadence.WEEKLY,
                ),
                (
                    "Inspect leaves and pests",
                    "Check both leaf surfaces and stems for changes.",
                    Cadence.WEEKLY,
                ),
                (
                    "Review fertilizer need",
                    "Apply only according to reviewed seasonal guidance.",
                    Cadence.MONTHLY,
                ),
            ),
            Category.DOG: (
                (
                    "Daily exercise",
                    "Complete the profile-appropriate exercise plan.",
                    Cadence.DAILY,
                ),
                ("Training practice", "Use a short reward-based training session.", Cadence.DAILY),
                (
                    "Grooming check",
                    "Brush and inspect coat, ears, and nails as appropriate.",
                    Cadence.WEEKLY,
                ),
            ),
            Category.CAT: (
                ("Litter care", "Scoop litter and observe for meaningful changes.", Cadence.DAILY),
                (
                    "Play and enrichment",
                    "Provide interactive play and rotate enrichment.",
                    Cadence.DAILY,
                ),
                (
                    "Grooming check",
                    "Brush and inspect coat and nails as appropriate.",
                    Cadence.WEEKLY,
                ),
            ),
        }
        return [
            CareTask(
                task_id=uuid4(),
                title=title,
                instructions=instructions,
                cadence=cadence,
                next_due_on=request.start_date,
            )
            for title, instructions, cadence in definitions[request.category]
        ]
