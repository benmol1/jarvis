# Jarvis — TODO

*Last updated: 2026-07-14 17:43*

Task breakdown for the phases in [DESIGN.md](DESIGN.md). Ship each phase end-to-end
before starting the next.

## Phase 0 — Plumbing ⚠️ IN PROGRESS

Prove the phone → Pi → Claude text round-trip.

Backend is complete; iOS app needed to complete end-to-end round-trip.

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
- [x] Minimal SwiftUI app: text box, send button, shows reply (see iOS App Setup block)
  - Buildable `Jarvis.xcodeproj` generated; `xcodebuild ... BUILD SUCCEEDED`
- [ ] Round-trip works: type on phone → Pi → Claude → reply on phone (see iOS App Setup block)
  - Blocked only on installing to the physical iPhone (signing + device deploy)

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
- [ ] Test on physical iPhone via USB
  - Verify Tailnet connectivity to Pi
  - Test actual on-device usage
- [ ] App Store prep (future)
  - Bundle ID, icons, display name

**Next step (resume here):** in Xcode set signing team (Apple ID) → plug in iPhone → select it as
destination → Run. First launch: trust the dev cert on the phone (Settings → General → VPN &
Device Management). Ensure Tailscale is installed + logged in on the phone so `raspberry-pi` resolves.

---

## Phase 1 — Read-only proposed plan ⏳ IN PROGRESS

The core value, zero write risk.

- [x] Create the "About Ben" profile store (a file on the Pi: priorities, scheduling rules, preferences, delighters)
- [x] Google Calendar OAuth integration (deployed & verified)
  - Code: calendar_tool.py get_calendar_service(), requirements.txt updated, .env.example updated
  - Tested: Live calendar events successfully returned via /chat endpoint
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
