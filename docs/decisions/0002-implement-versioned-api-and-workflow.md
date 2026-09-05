# ADR 0002: Implement the v1 API over one shared LangGraph workflow

- Status: Accepted
- Date: 2026-09-04
- Supersedes: ADR 0001's route-free phase

## Context

React needs stable recommendation, care-plan, error, and progress contracts while data, retrieval, memory, and MCP implementations are developed independently.

## Decision

Publish all application resources under `/v1`. Execute synchronous and SSE recommendation requests through the same compiled Supervisor graph. Use strict discriminated Pydantic inputs, deterministic safety and scoring, one selected specialist, a bounded evaluator/optimizer loop, and a versioned error envelope. Require a short-lived preview and literal confirmation before persisting a care plan.

Use provider-neutral ports with deterministic in-memory adapters for development. Missing live-source data produces a valid but explicitly degraded response.

## Consequences

- React can generate a client from the checked-in OpenAPI document.
- Safety and scoring cannot diverge between synchronous and streaming transports.
- Engineer 3 and Engineer 4 can replace fakes through composition-root injection.
- Authentication, production persistence, retrieval, MCP calls, traces, and infrastructure remain outside this change.
