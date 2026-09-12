"""Version 1 recommendation HTTP and streaming endpoints."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from advisor_api.container import get_container
from advisor_api.contracts.recommendations import RecommendationRequest, RecommendationResponse
from advisor_api.http.auth import authenticated_user
from advisor_api.http.context import request_id
from advisor_api.http.errors import COMMON_ERROR_RESPONSES
from advisor_api.http.streaming import encode_sse, sequence_from_last_event_id
from advisor_api.ports.auth import AuthenticatedUser

router = APIRouter(prefix="/recommendations", tags=["recommendations"])
Authenticated = Annotated[AuthenticatedUser, Depends(authenticated_user)]


@router.post(
    "",
    response_model=RecommendationResponse,
    responses=COMMON_ERROR_RESPONSES,
    operation_id="createRecommendation",
    summary="Create up to three recommendations",
)
async def create_recommendation(
    payload: RecommendationRequest,
    request: Request,
    user: Authenticated,
) -> RecommendationResponse:
    del user
    return await get_container(request).recommendations.recommend(payload, request_id(request))


@router.post(
    "/stream",
    response_class=StreamingResponse,
    responses={
        **COMMON_ERROR_RESPONSES,
        200: {
            "description": "Versioned recommendation progress events",
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string", "x-event-contract": "RecommendationStreamEvent"}
                }
            },
        },
    },
    operation_id="streamRecommendation",
    summary="Stream recommendation workflow progress",
)
async def stream_recommendation(
    payload: RecommendationRequest,
    request: Request,
    user: Authenticated,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    del user
    events = get_container(request).recommendations.stream(
        payload,
        request_id(request),
        after_sequence=sequence_from_last_event_id(last_event_id),
    )

    async def encoded_events() -> AsyncIterator[str]:
        async for event in events:
            yield encode_sse(event)

    return StreamingResponse(
        encoded_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
