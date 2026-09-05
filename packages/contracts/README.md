# Shared contracts — review required

This directory contains the generated, versioned OpenAPI boundary shared by React and FastAPI. Python source contracts live in `apps/api/src/advisor_api/contracts`.

The v1 contract covers:

- v1 recommendation and care-plan requests/responses;
- validation rules and the public error envelope;
- streaming progress event types, ordering, reconnect, and terminal semantics;
- recommendation context and typed graph state;
- plant, dog, cat, evidence, source, cost, and care-plan models;
- data/retrieval and provider-neutral tool contracts;
- correlation, trace, redaction, and version fields;
- golden examples for success, exclusions, missing input, and degraded dependencies.

Every observable change requires compatibility notes, an updated OpenAPI artifact and fixtures, and affected-consumer review.
