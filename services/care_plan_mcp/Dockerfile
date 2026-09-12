FROM ghcr.io/astral-sh/uv:0.12.1 AS uv

FROM python:3.12-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=uv /uv /uvx /bin/
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY apps ./apps
COPY agents ./agents
COPY database ./database
COPY services ./services
RUN uv sync --locked --no-dev

FROM python:3.12-slim AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

RUN groupadd --gid 10008 care-plan-mcp \
    && useradd --uid 10008 --gid care-plan-mcp --no-create-home --shell /usr/sbin/nologin care-plan-mcp

WORKDIR /app
COPY --from=builder --chown=care-plan-mcp:care-plan-mcp /app /app

USER care-plan-mcp
EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn services.care_plan_mcp.asgi:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
