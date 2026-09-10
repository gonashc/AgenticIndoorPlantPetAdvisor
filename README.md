# Indoor Plant and Pet Advisor

This repository implements the React experience and recommendation API described in the product and architecture document. The API can run against deterministic fixtures for local development or PostgreSQL for durable care-plan storage.

## Implemented surface

- `POST /v1/recommendations`
- `POST /v1/recommendations/stream` (`text/event-stream`)
- `POST /v1/care-plans/preview`
- `POST /v1/care-plans`
- `GET/PATCH /v1/care-plans/{plan_id}`
- `POST /v1/care-plans/{plan_id}/tasks/{task_id}/complete`
- `/openapi.json`, `/docs`, and `/redoc`
- `/health/live` and `/health/ready` operational probes

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

Install and run the React application in a second terminal with:

```powershell
npm install
npm run api-client:generate
npm run web:dev
```

Vite serves the application at `http://localhost:5173` and proxies `/api` requests to the local
FastAPI process at `http://127.0.0.1:8000`. The browser uses a TypeScript client generated from the
committed OpenAPI document, including the recommendation progress stream and care-plan confirmation
flow.

Run the frontend quality gate with:

```powershell
npm run web:lint
npm run web:typecheck
npm run web:test
npm run web:build
```

Build and run the same non-root container used for Cloud Run with:

```powershell
docker build --tag advisor-api:local .
docker run --rm --publish 8080:8080 --env APP_ENV=test --env DATABASE_MODE=memory advisor-api:local
```

The liveness probe checks the HTTP process. The readiness probe performs a current database ping
after startup has validated the required schema capabilities. Operational probes are deliberately
excluded from the versioned product OpenAPI contract.

Export the source-controlled OpenAPI contract with:

```powershell
uv run python scripts/export_openapi.py
```

The fixture adapters are intentionally labeled degraded and never claim current inventory or local-source availability.

## PostgreSQL and Google Cloud SQL

Set `DATABASE_MODE=url` for local PostgreSQL or `DATABASE_MODE=cloud_sql` for Google Cloud SQL. The API initializes its connection pool during application lifespan, verifies the expected Alembic revision, and closes the pool and Cloud SQL connector during shutdown. Migrations are always a separate release step.

See [Google Cloud SQL setup](docs/gcp-cloud-sql-postgres.md) and [migration instructions](database/migrations/README.md).

## LangSmith tracing

Recommendation graph runs can be traced to LangSmith without coupling public API contracts to the
provider. Copy `.env.example` to an ignored `.env`, set `LANGSMITH_TRACING=true`, and supply
`LANGSMITH_API_KEY` and `LANGSMITH_PROJECT`. Inputs and outputs are hidden by default; traces retain
only operational metadata such as request ID, category, transport, environment, and component
versions. CI leaves tracing disabled and never requires a LangSmith credential.

## Recommendation evaluations

The source-controlled `recommendation-eval-v1` dataset contains synthetic Plant, Dog, and Cat
scenarios covering toxicity, housing, time-alone exclusions, routing, ranking, evidence, response
quality, and provenance. Run the deterministic CI gate locally with:

```powershell
uv run pytest -m evaluation
```

Run the same baseline and publish the synthetic dataset and experiment to LangSmith with:

```powershell
uv run python scripts/run_recommendation_evals.py --upload
```

The upload command runs the local gate first and stops before publishing if any evaluator fails.
