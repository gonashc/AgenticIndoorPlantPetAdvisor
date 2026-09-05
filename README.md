# Indoor Plant and Pet Advisor — Engineer 2 API

This repository implements the recommendation-intelligence and application-API boundary described in the product and architecture document. It runs independently against deterministic in-memory catalog and persistence fakes until Engineers 3 and 4 supply production adapters.

## Implemented surface

- `POST /v1/recommendations`
- `POST /v1/recommendations/stream` (`text/event-stream`)
- `POST /v1/care-plans/preview`
- `POST /v1/care-plans`
- `GET/PATCH /v1/care-plans/{plan_id}`
- `POST /v1/care-plans/{plan_id}/tasks/{task_id}/complete`
- `/openapi.json`, `/docs`, and `/redoc`

All errors use the v1 error envelope and all responses carry `X-Request-ID` and `X-API-Version`. Streaming events have stable IDs, sequence numbers, discriminated event types, and `Last-Event-ID` replay filtering.

## Intended boundary

Engineer 2 owns HTTP application behavior, deterministic routing, recommendation orchestration, typed graph state, category subgraphs, scoring, hard constraints, safety checks, bounded repair, prompts, and structured output composition. PostgreSQL/Pinecone implementations and live provider integrations are out of scope here and will be consumed through ports.

## Setup

```powershell
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run mypy apps/api/src
```

Run the local API with:

```powershell
uv run uvicorn advisor_api.application:app --reload
```

Export the source-controlled OpenAPI contract with:

```powershell
uv run python scripts/export_openapi.py
```

The fixture adapters are intentionally labeled degraded and never claim current inventory or local-source availability.
