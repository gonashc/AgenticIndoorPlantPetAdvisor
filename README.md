# Indoor Plant and Pet Advisor — Engineer 2 Skeleton

This repository is scaffolded for the recommendation-intelligence and application-API work described in the product and architecture document. It intentionally contains **no recommendation or care-plan endpoints and no domain behavior yet**.

## Current contents

- A FastAPI application factory with documentation and OpenAPI routes disabled until contracts are approved.
- Empty HTTP v1, validation, error-contract, OpenAPI, and streaming extension points.
- Empty Supervisor, Plant, Dog, Cat, evaluator, optimizer, scoring, safety, and care-plan modules.
- Provider-neutral port locations for data, retrieval, memory, and MCP integrations.
- Architecture and ownership notes that protect the Engineer 3 and Engineer 4 boundaries.
- A guard test that prevents accidental route publication during the skeleton phase.

## Intended boundary

Engineer 2 owns HTTP application behavior, deterministic routing, recommendation orchestration, typed graph state, category subgraphs, scoring, hard constraints, safety checks, bounded repair, prompts, and structured output composition. PostgreSQL/Pinecone implementations and live provider integrations are out of scope here and will be consumed through ports.

## Setup (when implementation begins)

```powershell
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run mypy apps/api/src
```

Do not add routes until the versioned contracts and golden fixtures have received affected-owner review.

