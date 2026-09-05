# Application API

This is Engineer 2's FastAPI composition boundary. During the skeleton phase it creates an application with all documentation and schema URLs disabled and registers no routers.

Future work belongs in these explicit seams:

- `http/v1/recommendations.py` — request, response, and progress transport only.
- `http/v1/care_plans.py` — preview, confirm/save, retrieve, adjust, and task-completion transport only.
- `http/errors.py` — exception-to-versioned-envelope mapping.
- `http/openapi.py` — schema metadata, examples, security declarations, and compatibility policy.
- `http/streaming.py` — transport-neutral progress events and SSE framing.
- `ports/` — consumer-side abstractions for components owned by Engineers 3 and 4.

HTTP handlers should remain thin and delegate to application/orchestration services.

