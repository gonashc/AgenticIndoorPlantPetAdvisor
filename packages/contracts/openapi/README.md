# OpenAPI artifacts

`openapi.json` is generated from the FastAPI application and is the source for React client generation.

Regenerate it with `uv run python scripts/export_openapi.py`. CI should fail when the generated file differs from the running application schema.
