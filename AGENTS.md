# Repository Instructions

## Architecture rules

- Keep the application a modular monolith until scale or ownership provides a reason to split it.
- A recommendation session has exactly one deterministic category: `PLANT`, `DOG`, or `CAT`.
- Never allow an LLM to select or change the category, compute authoritative scores, override hard exclusions, or perform database queries directly.
- Execute only the selected specialist. Do not run Plant, Dog, and Cat specialists in parallel.
- PostgreSQL is authoritative for structured facts and transactions. Pinecone contains approved explanatory passages. Mem0 contains consented preferences only. MCP tools provide bounded current information.
- Keep provider payloads behind ports; public contracts must be provider-neutral.
- Require explicit user confirmation before a care plan is persisted or reminders are enabled.
- Preserve source, prompt, graph, model, rule, and knowledge versions needed to reconstruct a result.

## Ownership

- Engineer 2: `apps/api`, `agents`, `services/orchestration`, `services/scoring`, and `services/safety`.
- Engineer 3: catalog, ingestion, retrieval, database, and retrieval evaluations.
- Engineer 4: MCP gateway, provider integrations, observability, infrastructure, and production health checks.
- Shared contracts, domain models, fixtures, ADRs, and this file require affected-owner review.

## Change discipline

- Keep the API under an explicit major version prefix.
- Make errors conform to one versioned envelope and make streaming events discriminated and resumable.
- Update compatibility notes and golden fixtures with every observable contract change.
- Do not create a general `utils` package; create small, owned modules with a stable public surface.
- Keep secrets and personal data out of source, fixtures, logs, traces, and errors.

## Verification

Run formatting/lint, type checks, unit tests, contract tests, and the relevant recommendation evaluation subset before completion. This skeleton phase must continue to publish zero routes.

