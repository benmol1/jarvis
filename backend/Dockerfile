# Dockerfile for Jarvis backend on Raspberry Pi (ARM64/ARMv7)
# Multi-stage build for smaller final image

# Build stage
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir uv && \
    uv pip install --no-cache-dir -r requirements.txt

# Final stage - use lightweight alpine base with Python
FROM python:3.11-alpine

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install runtime dependencies (for alpine)
RUN apk add --no-cache --virtual .build-deps gcc musl-dev libffi-dev openssl-dev && \
    apk add --no-cache libstdc++ curl && \
    apk del .build-deps

# Copy application code
COPY . .

# Create non-root user for security
RUN adduser -D jarvis && \
    mkdir -p /data && \
    chown jarvis:jarvis /data /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    JARVIS_PROFILE_PATH=/data/about_ben.md \
    JARVIS_STATE_PATH=/data/state.json

# Switch to non-root user
USER jarvis

# Expose port
EXPOSE 8000

# Health check (uses curl which is available in alpine)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
