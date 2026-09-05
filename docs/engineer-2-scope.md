# Engineer 2 Scope Review

## Requested outcomes

The user asked Engineer 2 to eventually publish the FastAPI surface consumed by React: recommendation APIs, care-plan APIs, request/response validation, OpenAPI, versioning and errors, and recommendation-progress streaming.

## Architecture constraints carried forward

- Exactly one category per recommendation session.
- At most three primary recommendations, with score, reasons, concerns, evidence, costs, verification data, and validation status.
- Deterministic code owns category routing, scoring, ZIP/schema checks, and hard exclusions.
- Only the selected Plant, Dog, or Cat specialist executes.
- Standard requests target a five-second P95; deep research is asynchronous.
- Streaming is progress reporting for the same bounded workflow, not an independent recommendation path.
- Care plans are previewed before explicit confirmation and persistence.
- Error, response, event, prompt, graph, rule, model, source, and knowledge versions support auditability.

## Ownership seams

- Engineer 3 supplies authoritative catalog/persistence and knowledge retrieval through reviewed ports.
- Engineer 4 supplies MCP/live-data, cache, tracing, secrets, health, and infrastructure adapters through reviewed ports.
- Engineer 1 receives the OpenAPI artifact/generated client and must not consume provider-specific types.
- Shared contracts and fixtures require all affected owners to review changes.

## Implemented Engineer 2 slice

The application now publishes strict Pydantic v1 transport contracts, a uniform error envelope, generated OpenAPI, discriminated SSE progress events, and care-plan preview/confirmation/lifecycle endpoints. A hierarchical LangGraph Supervisor deterministically routes to exactly one category subgraph, applies safety before scoring, evaluates outputs, and permits at most two explanation-only repairs.

Engineer 3 and Engineer 4 dependencies remain provider-neutral ports. Deterministic in-memory fixtures make the slice runnable while clearly returning `DEGRADED` when current local-source data is unavailable.
