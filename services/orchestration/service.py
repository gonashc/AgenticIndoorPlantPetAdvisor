"""Recommendation use case over one shared compiled LangGraph workflow."""

from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from advisor_api.contracts.errors import ErrorBody
from advisor_api.contracts.recommendations import RecommendationRequest, RecommendationResponse
from advisor_api.contracts.streaming import (
    ProgressData,
    ProgressStage,
    RecommendationCompletedEvent,
    RecommendationFailedEvent,
    RecommendationProgressEvent,
    RecommendationStreamEvent,
)
from advisor_api.http.errors import ApiError
from advisor_api.ports.observability import RecommendationTracer

from agents.supervisor import Graph
from services.orchestration.state import RecommendationState


class RecommendationService:
    _PROGRESS: Mapping[str, tuple[ProgressStage, int, str]] = {
        "prepare": ("VALIDATING", 15, "Validated the request and loaded candidates."),
        "apply_safety": ("APPLYING_SAFETY", 35, "Applied deterministic hard constraints."),
        "plant_specialist": ("SCORING", 65, "Ranked eligible plant candidates."),
        "dog_specialist": ("SCORING", 65, "Ranked eligible dog profiles."),
        "cat_specialist": ("SCORING", 65, "Ranked eligible cat profiles."),
        "evaluate": ("EVALUATING", 85, "Evaluated structure, evidence, and safety."),
        "optimizer": ("OPTIMIZING", 90, "Repaired failed explanation sections."),
    }

    def __init__(self, graph: Graph, tracer: RecommendationTracer) -> None:
        self._graph = graph
        self._tracer = tracer

    async def recommend(
        self, request: RecommendationRequest, request_id: UUID
    ) -> RecommendationResponse:
        with self._tracer.trace(
            request_id=request_id,
            category=request.category,
            transport="http",
        ):
            result = await self._graph.ainvoke(self._initial_state(request, request_id))
        state = cast(RecommendationState, result)
        return state["response"]

    async def stream(
        self,
        request: RecommendationRequest,
        request_id: UUID,
        *,
        after_sequence: int = 0,
    ) -> AsyncIterator[RecommendationStreamEvent]:
        with self._tracer.trace(
            request_id=request_id,
            category=request.category,
            transport="stream",
        ):
            sequence = 1
            accepted = self._progress_event(
                request,
                request_id,
                sequence,
                "ACCEPTED",
                0,
                "Recommendation request accepted.",
            )
            if sequence > after_sequence:
                yield accepted

            try:
                final_response: RecommendationResponse | None = None
                async for chunk in self._graph.astream(
                    self._initial_state(request, request_id),
                    stream_mode="updates",
                    version="v2",
                ):
                    if chunk["type"] != "updates":
                        continue
                    for node_name, update in chunk["data"].items():
                        if node_name == "compose" and "response" in update:
                            final_response = cast(RecommendationResponse, update["response"])
                        progress = self._PROGRESS.get(node_name)
                        if progress is None:
                            continue
                        sequence += 1
                        stage, percent, message = progress
                        event = self._progress_event(
                            request, request_id, sequence, stage, percent, message
                        )
                        if sequence > after_sequence:
                            yield event

                if final_response is None:
                    raise RuntimeError("Recommendation graph completed without a response")
                sequence += 1
                completed = RecommendationCompletedEvent(
                    event_id=f"{request_id}:{sequence}",
                    sequence=sequence,
                    request_id=request_id,
                    session_id=request.session_id,
                    emitted_at=datetime.now(UTC),
                    data=final_response,
                )
                if sequence > after_sequence:
                    yield completed
            except ApiError as exc:
                sequence += 1
                failed = RecommendationFailedEvent(
                    event_id=f"{request_id}:{sequence}",
                    sequence=sequence,
                    request_id=request_id,
                    session_id=request.session_id,
                    emitted_at=datetime.now(UTC),
                    data=ErrorBody(
                        code=exc.code,
                        message=exc.message,
                        request_id=request_id,
                        details=exc.details,
                    ),
                )
                if sequence > after_sequence:
                    yield failed
            except Exception:
                sequence += 1
                failed = RecommendationFailedEvent(
                    event_id=f"{request_id}:{sequence}",
                    sequence=sequence,
                    request_id=request_id,
                    session_id=request.session_id,
                    emitted_at=datetime.now(UTC),
                    data=ErrorBody(
                        code="INTERNAL_ERROR",
                        message="The recommendation stream could not be completed.",
                        request_id=request_id,
                    ),
                )
                if sequence > after_sequence:
                    yield failed

    @staticmethod
    def _initial_state(request: RecommendationRequest, request_id: UUID) -> RecommendationState:
        return {"request": request, "request_id": request_id}

    @staticmethod
    def _progress_event(
        request: RecommendationRequest,
        request_id: UUID,
        sequence: int,
        stage: ProgressStage,
        percent: int,
        message: str,
    ) -> RecommendationProgressEvent:
        return RecommendationProgressEvent(
            event_id=f"{request_id}:{sequence}",
            sequence=sequence,
            request_id=request_id,
            session_id=request.session_id,
            emitted_at=datetime.now(UTC),
            data=ProgressData(stage=stage, percent=percent, message=message),
        )
