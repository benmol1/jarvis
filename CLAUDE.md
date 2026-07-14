# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Backend: Python + FastAPI with Docker support for Raspberry Pi deployment.
Frontend: SwiftUI iOS app.

## Build, lint, and test commands

### Backend (Python)

All commands run from `backend/`. Dependencies live in `pyproject.toml` and are locked in
`uv.lock` — the same lockfile is used for local dev and the Docker image, so add deps with
`uv add` (never by hand) and commit the updated lockfile, or the image build will fail.

```bash
# Install dependencies (creates .venv)
uv sync

# Run locally
uv run uvicorn main:app --reload

# Run tests
uv run pytest

# Run single test file
uv run pytest tests/test_main.py -v

# Format and lint (run before committing)
uv run ruff format .
uv run ruff check . --fix

# Docker build and run
docker compose build
docker compose up -d
```

### iOS (SwiftUI)
See `ios/README.md` for build instructions (requires Xcode on macOS).

## High-level architecture

- **Backend**: `backend/` — FastAPI service with Docker support
  - `main.py` — FastAPI app with `/chat` and `/health` endpoints
  - `profile_store.py` — Loads user profile from markdown file
  - `state.py` — Rolling state persistence (JSON)
  - `prompt.py` — System prompt builder
  - `calendar_tool.py` — Google Calendar integration (read-only for now)
  - `trello_tool.py` — Trello API integration
  - `Dockerfile` — Multi-stage build for ARM compatibility
  - `docker-compose.yml` — Service orchestration with volumes and health checks
- **Frontend**: `ios/Jarvis/` — SwiftUI app with chat interface
- **Deployment**: Raspberry Pi via Docker over Tailscale tailnet
