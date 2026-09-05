# ADR 0001: Begin with a route-free modular-monolith skeleton

- Status: Accepted for skeleton phase
- Date: 2026-09-04

## Context

The architecture calls for FastAPI plus a hierarchical Supervisor–Specialist LangGraph design. Four engineers work concurrently across UI, recommendation behavior, data/retrieval, and integrations/operations. Stable interfaces are required before parallel implementation.

## Decision

Create the ownership-aligned directories and a route-free FastAPI application factory. Keep OpenAPI and interactive documentation disabled. Defer all public and internal schemas until an explicit contract-design task and affected-owner review.

## Consequences

- The scaffold imports no database, vector store, memory, model, or MCP SDK.
- Data and integration implementations can later attach through provider-neutral ports.
- No endpoint is accidentally treated as a stable contract before review.
- The next implementation step must define and test versioned contracts before registering routers.

