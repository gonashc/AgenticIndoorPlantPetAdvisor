# Application API

This is Engineer 2's FastAPI composition boundary. It publishes the reviewed v1 application contract while keeping data and live providers behind dependency-inverted ports.

The implementation uses these explicit seams:

- `http/v1/recommendations.py` — request, response, and progress transport.
- `http/v1/care_plans.py` — preview, confirm/save, retrieve, status, and task completion.
- `http/errors.py` — exception-to-versioned-envelope mapping.
- `http/openapi.py` — schema metadata, examples, security declarations, and compatibility policy.
- `http/streaming.py` — transport-neutral progress events and SSE framing.
- `ports/` — consumer-side abstractions for components owned by Engineers 3 and 4.

HTTP handlers should remain thin and delegate to application/orchestration services.
