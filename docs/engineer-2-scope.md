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

## Skeleton-phase decision

No application routes, Pydantic transport models, OpenAPI artifact, streaming event schema, graph, prompt, scoring rule, safety rule, persistence call, or external tool call is implemented. The folders and ownership boundaries exist so those contracts can be agreed before coding begins.

