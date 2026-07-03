# Jarvis — TODO

*Last updated: 2026-07-03 21:13*

Task breakdown for the phases in [DESIGN.md](DESIGN.md). Ship each phase end-to-end
before starting the next.

## Phase 0 — Plumbing ✅ COMPLETE

Prove the phone → Pi → Claude text round-trip.

- [x] Pick backend language/framework (default: Python + FastAPI)
- [x] Dockerize the backend for Pi deployment
  - [x] Create Dockerfile (multi-stage, Python alpine base for ARM compatibility)
  - [x] Create docker-compose.yml with port mapping (8000:8000)
  - [x] Configure volume mounts for profile and state persistence
  - [x] Add healthcheck to container
- [x] Set up the orchestrator service on the Pi (single `/chat` endpoint, takes text, returns text)
  - [x] Install Docker on Raspberry Pi
  - [x] Build and run container: `docker compose up -d`
- [x] Store the Anthropic API key as a secret on the Pi (env file, not in code)
  - [x] Create `.env` file on Pi with `ANTHROPIC_API_KEY=...`
  - [x] Ensure `.env` is in `.dockerignore`
- [x] Wire the `/chat` endpoint to Claude Haiku (single call site, easy to swap later)
- [x] Confirm the Pi is reachable over the tailnet (Tailscale hostname + port)
  - [x] Test: `curl http://raspberry-pi:8000/health` from iPhone Safari
- [x] Minimal SwiftUI app: text box, send button, shows reply
- [x] Round-trip works: type on phone → Pi → Claude → reply on phone

## Phase 1 — Read-only proposed plan ⏳ IN PROGRESS

The core value, zero write risk.

- [x] Create the "About Ben" profile store (a file on the Pi: priorities, scheduling rules, preferences, delighters)
- [ ] Google Calendar OAuth: one-time setup, store token on the Pi
  - BLOCKED: Need to add ben.molyneaux1@gmail.com as test user in Google Cloud OAuth consent screen (error: "jarvis has not completed the Google verification process")
  - Steps: Console → APIs & Services → OAuth consent screen → Test users → + ADD USERS
  - Then run token script to get refresh_token
  - Required .env vars: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN
- [x] Calendar **read** tool for Claude (fetch today's / this week's events)
- [x] Trello auth (API key + token) stored on the Pi
  - Code complete: trello_tool.py reads from TRELLO_API_KEY, TRELLO_TOKEN, TRELLO_BOARD_ID
  - User has credentials; needs adding to .env on Pi + redeploy
- [x] Trello **read** tool for Claude (fetch cards/lists)
- [x] Rolling-state store (yesterday's plan, what slipped, carried-forward priorities)
- [x] System prompt assembles: profile + rolling state + live calendar + Trello
- [ ] Morning conversation produces a **proposed** time-boxed plan (text only, no writes)
  - TODO: Update prompt.py to instruct Claude to output structured plan
  - TODO: Add plan parsing to extract time-boxes from Claude response
- [ ] Display the proposed plan clearly in the app
  - TODO: Update iOS ContentView with dedicated plan display

## Phase 2 — Calendar writes + message drafts

Act on the plan once trusted.

- [ ] Calendar **create/modify** tool for Claude (own time-boxes only)
- [ ] Respect explicit scheduling guardrails (work hours, focus blocks, sacred family time)
- [ ] App writes agreed time-boxes to Google Calendar
- [ ] Generate draft messages for reschedules (shown as copyable text, no send)
- [ ] Approval/copy view in the app for drafts and calendar changes
- [ ] Persist the day's plan into rolling state (so tomorrow knows what slipped)

## Phase 3 — Voice + reminder

The 10-minute ritual feel.

- [ ] Speech-to-text via `SFSpeechRecognizer` (push-to-talk)
- [ ] Text-to-speech via `AVSpeechSynthesizer` (spoken replies)
- [ ] Conversation UI works hands-free (speak → hear response)
- [ ] Daily morning reminder (local notification)

## Later — earn-their-place TODOs

- [ ] Realtime cloud voice API (nicer, customisable voice) instead of Apple TTS
- [ ] Work calendar via Microsoft Graph / Outlook (security permitting)
- [ ] Gmail drafts instead of copy/paste messages
- [ ] Swap Claude Haiku for another model (possibly open-source)
- [ ] Decide on Apple Developer account ($99/yr recommended) for long-lived installs
