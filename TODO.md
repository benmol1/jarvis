# Jarvis — TODO

*Last updated: 2026-07-14 19:47*

Task breakdown for the phases in [DESIGN.md](DESIGN.md). Ship each phase end-to-end
before starting the next.

## Phase 0 — Plumbing ⚠️ IN PROGRESS

Prove the phone → Pi → Claude text round-trip.

Backend serves `/chat`; iOS app needed to complete the end-to-end round-trip.
(Calendar data is currently missing — see the expired Google token under Phase 1.)

- [x] Pick backend language/framework (default: Python + FastAPI)
- [x] Dockerize the backend for Pi deployment
  - [x] Create Dockerfile (multi-stage, `python:3.11-slim` base for ARM compatibility)
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
- [x] Minimal SwiftUI app: text box, send button, shows reply (see iOS App Setup block)
  - Buildable `Jarvis.xcodeproj` generated; `xcodebuild ... BUILD SUCCEEDED`
- [ ] Round-trip works: type on phone → Pi → Claude → reply on phone (see iOS App Setup block)
  - Blocked on: Apple ID / signing identity, iOS platform install, then device deploy

## iOS App Setup ⏳ IN PROGRESS

Create and deploy the iOS app to actually use Jarvis on the phone.

- [x] Set up Xcode on MacBook
  - App Store Xcode 26 needs macOS 26; on macOS 15.6.1 so installed **Xcode 16.4** via `xcodes` (last release supporting Sequoia)
  - Selected toolchain + accepted license (`xcode-select -s`, `xcodebuild -license accept`)
- [x] Create new iOS project in `ios/` directory
  - Generated with **XcodeGen** from `ios/project.yml` (repo-tracked spec) → `Jarvis.xcodeproj`
  - SwiftUI, deployment target iOS 17, iPhone-only, bundle id `com.bmolyneaux.jarvis`
- [x] Configure app networking
  - `NSAppTransportSecurity` / `NSAllowsArbitraryLoads` set via `project.yml` → generated `Info.plist`
- [x] Build basic UI (ContentView.swift)
  - Text input field, Send button, response area (send button disables while in-flight)
- [x] Wire UI to backend
  - POST to `http://raspberry-pi:8000/chat`; JSON encode/decode; error path shows message
  - Contract verified against backend (`{message}` → `{reply}`)
- [~] Test on iPhone Simulator — **skipped** (no iOS simulator runtime installed; targeting device directly)
- [ ] **Add an Apple ID in Xcode → Settings → Accounts** (GUI-only)
  - `security find-identity -p codesigning` currently reports **0 valid identities**
  - A free account is fine for device installs; the cert expires every 7 days
- [ ] **Install the iOS platform** (Xcode → Settings → Components; several GB)
  - The iOS 18.5 *SDK* is present (`xcodebuild -sdk iphoneos18.5` BUILD SUCCEEDED), but the
    *platform* is not, so `-destination generic/platform=iOS` fails and nothing can be run
- [ ] Set the signing team on the Jarvis target
- [ ] Test on physical iPhone via USB
  - Verify tailnet connectivity to Pi
  - Test actual on-device usage
- [ ] App Store prep (future)
  - Bundle ID, icons, display name

**Next step (resume here):** the three GUI steps above (Apple ID → iOS platform → signing team),
then plug in iPhone → select it as destination → Run. First launch: trust the dev cert on the phone
(Settings → General → VPN & Device Management).

⚠️ **Tailscale:** `raspberry-pi` currently resolves from the MacBook over the **LAN** (192.168.1.220);
Tailscale on the Mac is *stopped*. The phone needs Tailscale installed + logged in, or the app will
work at home and fail everywhere else.

---

## Backend hardening & repo hygiene ⏳ IN PROGRESS

Unplanned work, triggered by finding `/chat` returning a 500 while `/health` stayed green.

- [x] Fix `/chat` 500 when an integration fails
  - `main.py` caught only `(KeyError, ImportError)`, so a live failure (expired Google token)
    escaped and took down the whole request
  - Calendar/Trello now go through `fetch_context()`: logs a warning, degrades to no data
  - Regression test added (`tests/test_main.py::test_chat_survives_a_failing_integration`)
- [x] Move the `uv` project from repo root into `backend/`
  - Root `pyproject.toml` was invisible to the Docker build context (`backend/`)
  - Removed stray `uv init` artifacts (root `main.py`, empty `README.md`)
  - Fixed: `pytest` was a *runtime* dep; `requires-python` was 3.10 vs 3.11 in the image
- [x] Move test files into `backend/tests/` (`pythonpath`/`testpaths` set in `pyproject.toml`)
- [x] Switch the Dockerfile to `uv sync --frozen` (multi-stage; deleted `requirements.txt`)
  - Single source of dependency truth; no more requirements/pyproject drift
- [ ] Verify the new image builds and `/chat` still answers
  - Docker Desktop wasn't running locally; **not yet verified — do this before deploying to the Pi**

## Phase 1 — Read-only proposed plan ⏳ IN PROGRESS

The core value, zero write risk.

- [x] Create the "About Ben" profile store (a file on the Pi: priorities, scheduling rules, preferences, delighters)
- [x] Google Calendar OAuth integration (deployed & verified)
  - Code: calendar_tool.py get_calendar_service(), deps added, .env.example updated
  - Tested: Live calendar events successfully returned via /chat endpoint
- [ ] ⚠️ **BROKEN: Google refresh token expired** (`invalid_grant: Token has been expired or revoked`)
  - Root cause: OAuth consent screen is in **Testing** status → Google expires refresh tokens after 7 days
  - [ ] Publish the OAuth app to **Production** in Google Cloud Console (else this recurs weekly)
  - [ ] Re-mint `GOOGLE_REFRESH_TOKEN`, update the Pi's `.env`, redeploy
  - Chat no longer 500s on this (see Backend hardening), but Jarvis plans **without calendar data** until fixed
- [x] Calendar **read** tool for Claude (fetch today's / this week's events)
- [x] Trello auth (API key + token) stored on the Pi (deployed & verified)
  - Code: trello_tool.py reads from TRELLO_API_KEY, TRELLO_TOKEN, TRELLO_BOARD_ID
  - Tested: Trello cards successfully returned via /chat endpoint
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

## Phase 4 — Desktop web front-end

Same `/chat` backend, a second client. No new framework — plain HTML + fetch, served as a static file.

- [ ] Add `backend/static/index.html`: textarea, send button, response area, plain JS `fetch()` to `/chat`
- [ ] Mount it in FastAPI with `StaticFiles` (stdlib-adjacent, already a FastAPI dependency)
- [ ] Reuse existing CORS/auth as needed for browser access over the tailnet
- [ ] Confirm plan display works in a wide viewport (no mobile constraints to design around)
- [ ] (Later) Persist chat history in the page via `localStorage` if useful

Not building: an in-app calendar/Trello view. Jarvis's writes already show up in the real Google Calendar/Trello apps — use those side-by-side with Jarvis instead of replicating their UI.

## Later — earn-their-place TODOs

- [ ] Realtime cloud voice API (nicer, customisable voice) instead of Apple TTS
- [ ] Work calendar via Microsoft Graph / Outlook (security permitting)
- [ ] Gmail drafts instead of copy/paste messages
- [ ] Swap Claude Haiku for another model (possibly open-source)
- [ ] Decide on Apple Developer account ($99/yr recommended) for long-lived installs
