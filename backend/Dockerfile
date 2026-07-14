# Dockerfile for Jarvis backend on Raspberry Pi
# Multi-stage: deps are resolved from uv.lock in the builder, so the runtime
# image carries no compiler toolchain.

FROM python:3.11-slim AS builder

# Pinned rather than :latest so an image rebuild can't silently change uv.
COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /usr/local/bin/uv

WORKDIR /app

# Build tools for any dependency without a prebuilt arm64 wheel.
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Only the dependency manifests, so this layer caches until they change.
COPY pyproject.toml uv.lock ./

# --frozen: fail if uv.lock is stale rather than silently re-resolving.
# --no-dev: pytest and httpx stay out of the production image.
RUN uv sync --frozen --no-dev


FROM python:3.11-slim

WORKDIR /app

# curl is used by the healthcheck below.
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv

COPY . .

# Put the venv first on PATH so `uvicorn` resolves to the locked one.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    JARVIS_PROFILE_PATH=/data/about_ben.md \
    JARVIS_STATE_PATH=/data/state.json

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
