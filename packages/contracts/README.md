# Shared contracts — review required

This directory is reserved for the approved, versioned boundary shared by React, FastAPI, data, and integrations. It contains no schema yet.

Before implementation, freeze and review:

- v1 recommendation and care-plan requests/responses;
- validation rules and the public error envelope;
- streaming progress event types, ordering, reconnect, and terminal semantics;
- recommendation context and typed graph state;
- plant, dog, cat, evidence, source, cost, and care-plan models;
- data/retrieval and provider-neutral tool contracts;
- correlation, trace, redaction, and version fields;
- golden examples for success, exclusions, missing input, and degraded dependencies.

Every observable change requires compatibility notes, updated fixtures, and affected-consumer review.

