# Jarvis — TODO

*Last updated: 2026-07-27 15:30*

Task breakdown for the phases in [DESIGN.md](DESIGN.md). Ship each phase end-to-end
before starting the next.

## Phase 0 — Plumbing ✅ COMPLETE

Prove the phone → Pi → Claude text round-trip.

Backend serves `/chat` with live calendar + Trello data; iOS app needed to complete the
end-to-end round-trip.

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
- [x] Round-trip works: type on phone → Pi → Claude → reply on phone (see iOS App Setup block)
  - Verified on physical iPhone over Tailscale (away from home network): sent a message, got Jarvis's welcome reply back

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
- [x] **Add an Apple ID in Xcode → Settings → Accounts** (GUI-only)
  - Signed in; `security find-identity -p codesigning` now shows a valid
    "Apple Development: ben.molyneaux1@gmail.com" identity
- [x] **Install the iOS platform** (Xcode → Settings → Components; several GB)
  - Confirmed already installed under the active `Xcode-16.4.0.app` toolchain
    (`iPhoneOS.platform` present); earlier "platform missing" read was against
    a stale `/Applications/Xcode.app` path
- [x] Set the signing team on the Jarvis target
  - `CODE_SIGN_STYLE: Automatic` in `project.yml` picked up the team once the
    Apple ID was added; build shows "iOS Team Provisioning Profile:
    com.bmolyneaux.jarvis"
- [x] Test on physical iPhone via USB
  - Built, installed, and launched on "BM iPhone 13 blue" via
    `xcodebuild` + `xcrun devicectl`; had to enable Developer Mode on-device
    (Settings → Privacy & Security) and trust the dev cert (Settings →
    General → VPN & Device Management) before first launch would work
  - Verified tailnet connectivity: activated Tailscale on the phone, sent a
    message away from the home network, got a reply
- [ ] App Store prep (future)
  - Bundle ID, icons, display name

⚠️ **Tailscale:** the phone needs Tailscale active to reach `raspberry-pi` away from the
home LAN (192.168.1.220) — confirmed working now that it's installed and logged in.

---

## Backend hardening & repo hygiene ✅ COMPLETE

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
- [x] Add `ruff` for formatting + linting (dev dependency; config in `pyproject.toml`)
  - Note: ruff's `UP` rules rewrote `timezone.utc` → `UTC`, which is 3.11+ only — safe only
    because `requires-python` now matches the image
- [x] Verify the new image builds and `/chat` still answers
  - Built and deployed on the Pi: `uv sync --frozen` resolves on ARM, service serves from it

## Phase 1 — Read-only proposed plan ⏳ IN PROGRESS

The core value, zero write risk.

- [x] Create the "About Ben" profile store (a file on the Pi: priorities, scheduling rules, preferences, delighters)
- [x] Google Calendar OAuth integration (deployed & verified)
  - Code: calendar_tool.py get_calendar_service(), deps added, .env.example updated
  - Tested: Live calendar events successfully returned via /chat endpoint
- [x] **Fixed: expired Google refresh token** (`invalid_grant: Token has been expired or revoked`)
  - Root cause: OAuth consent screen was in **Testing** status → Google expires refresh tokens after 7 days
  - [x] Publish the OAuth app to **Production** in Google Cloud Console (stops it recurring weekly)
  - [x] Re-mint `GOOGLE_REFRESH_TOKEN` (`backend/reauth_google.py`), update the Pi's `.env`, redeploy
  - Verified end-to-end: `/chat` correctly named a real upcoming event from the live calendar
- [x] Calendar **read** tool for Claude (fetch today's / this week's events)
- [x] Widen calendar visibility beyond the fixed rolling window
  - Default lookahead injected into the prompt bumped 7 → 14 days
  - Added a `list_events` tool so Jarvis can look up any arbitrary date range
    on demand (e.g. "what's on in August") instead of only the injected window
  - Fixed `list_events` omitting `event_id`/`calendar_id`, which had silently
    blocked Jarvis from acting on events it had just looked up
- [x] Trello auth (API key + token) stored on the Pi (deployed & verified)
  - Code: trello_tool.py reads from TRELLO_API_KEY, TRELLO_TOKEN, TRELLO_BOARD_ID
  - Tested: Trello cards successfully returned via /chat endpoint
- [x] Trello **read** tool for Claude (fetch cards/lists)
- [x] Rolling-state store (yesterday's plan, what slipped, carried-forward priorities)
- [x] System prompt assembles: profile + rolling state + live calendar + Trello
- [x] Widen the default calendar context to include recent history (past 3
      days) alongside the 14-day lookahead, so Jarvis has context on what's
      already happened today, not just what's ahead (`get_upcoming_events`)
- [ ] Morning conversation produces a **proposed** time-boxed plan (text only, no writes)
  - TODO: Update prompt.py to instruct Claude to output structured plan
  - TODO: Add plan parsing to extract time-boxes from Claude response
- [ ] Display the proposed plan clearly in the app
  - TODO: Update iOS ContentView with dedicated plan display

## Phase 2 — Calendar writes + message drafts ⏳ IN PROGRESS

Act on the plan once trusted. Hybrid trust model: Jarvis freely
creates/moves/deletes its **own** tagged events; moving/deleting **anyone
else's** event is queued for Ben's approval in the app.

- [x] Calendar **create / modify / delete** tool for Claude (`create_time_box`,
      `move_event`, `delete_event`) via a tool-use loop in `main.py`
  - Jarvis-created events stamped with a visible `🤖 [Jarvis]` tag in the
    description (`calendar_tool.JARVIS_TAG`); ownership checked server-side, not
    trusted from the model
  - `GOOGLE_REFRESH_TOKEN` re-minted with the `calendar.events` scope
    (`backend/reauth_google.py`) — verified locally end-to-end
- [x] Jarvis tag enhancement: add a created at timestamp DD/MM/YY hh:mm (24hr clock, local timezone)
- [x] Cross-calendar targeting: create events in the right calendar (Personal vs Joint)
      and move/copy events between them
  - Create: `create_time_box` takes an optional `calendar_id`; Jarvis picks the
    target from the ask ("add to Joint") against the live calendar list, else primary
  - Move: `move_to_calendar` tool → `calendar_tool.move_event_to_calendar`
    (Google `events.move`); Jarvis-owned applies inline, foreign is queued for approval
  - Copy: `copy_event` tool → `calendar_tool.copy_event` (insert duplicate, leave
    original); non-destructive so applies inline, copy is stamped Jarvis-owned
  - Calendar list surfaced in the system prompt so Jarvis knows each calendar's id
  - Tested locally; still needs Pi deploy + verify
- [x] Respect explicit scheduling guardrails (work hours, focus blocks, sacred
      family time) — instructed in `prompt.py`, sourced from "About Ben"
- [x] App writes agreed time-boxes to Google Calendar (create applies inline;
      foreign move/delete applies via `/apply` after approval) — verified
      locally
- [x] Generate draft messages for reschedules — prompt instructs Jarvis to
      write copyable drafts; web reply has a **Copy** button (no send)
  - Refined: Copy button was showing on every reply, not just drafts. Added a
    `flag_draft_message` tool Jarvis calls only when a reply contains a
    message meant to be copied and sent — button now gated on that flag
- [x] Approval/copy view in the app (web front-end): pending foreign-event
      changes render **Approve** buttons that POST to `/apply`
- [x] Persist the day's plan into rolling state (`save_plan` tool → `state.json`)
- [x] Refactor toolset
  - `create_time_box` → `create_event` (adds location, description, attendees,
    >14-day conflict warning); `move_event` replaced by `modify_event`
    (patches any subset of fields, refreshes "modified at" only on
    Jarvis-owned events so foreign ones don't flip ownership)
  - Added `list_calendars`, `respond_to_event` (RSVP), `cancel_approval`
  - Approvals persisted in `state["pending_approvals"]` with stable ids
    (`/apply` clears by id); any change inviting other people is queued
  - Reconciled client-side (web + iOS) instead of appending a bubble per turn
- [x] Make sure JARVIS can automatically fill locations
  - `create_event`/`modify_event` accept an optional `location`; the Maps
    tools now let Jarvis resolve one — `find_place` turns a fuzzy name into a
    clean postal address + Maps link, and `add_route_to_event` sets the event
    location outright (see "Google Maps integration")
- [x] iOS: mirror the approval/copy view (done in Phase 2.5 — iOS Interface)
- [x] Surface free/busy status and the Calendar UI colour on every event
      (`get_event`, `get_events_in_range`, `create_event`, `modify_event`,
      `copy_event`); `create_event`/`modify_event` can also set them
      (`busy`, `color_id`). An event marked free (`[FREE]` in the prompt) is
      informational only — the system prompt and the far-out conflict check
      both treat it as never being a diary clash.
- [ ] Deploy and verify on the Pi (tested locally only so far)

## Google Maps integration ⏳ IN PROGRESS

Unplanned work: give Jarvis travel times and real locations so it can plan
"when to leave" and attach directions to events (`backend/maps_tool.py`).

- [x] `find_place` — resolve a fuzzy place name/address to a postal address +
      Google Maps deep link (Places Text Search)
- [x] `travel_time` — distance/duration between two places, traffic-aware for
      driving at a chosen departure time (Distance Matrix); returns
      `duration_seconds` so callers can compute a "leave by" time
- [x] `add_route_to_event` — plan a route and write it onto an existing event
      in one step: sets the location, appends a route block (travel time,
      distance, leave-by, directions link) to the description, replacing any
      prior block. Applies inline on Jarvis-owned events, queues via the
      standard approval otherwise
- [x] Accept a list of travel modes (driving / walking / bicycling / transit)
      so Jarvis can compare e.g. driving vs the train in one call; prompt
      tells it to infer the mode from Ben's habits and ask when unsure rather
      than defaulting to driving
- [x] Saved places: `resolve_location` expands "home"/"work" to
      `JARVIS_HOME_ADDRESS` / `JARVIS_WORK_ADDRESS`, kept out of the system
      prompt so the addresses only enter a request when a tool needs them
- [x] Plain `GOOGLE_MAPS_API_KEY` auth (no OAuth, no new refresh token);
      documented in `.env.example`, wired into the tool loop, prompt, and
      `CLAUDE.md`, with unit tests for the module and the `execute_tool` branches
- [ ] Enable the Distance Matrix + Places APIs on the key and deploy/verify on
      the Pi (tested locally only so far)

## Phase 2.5 — iOS Interface (Jarvis HUD) ✅ COMPLETE

Brought the iOS app to visual + feature parity with the desktop web console
(`backend/static/index.html`), using the tokens already specified in
[DESIGN.md](DESIGN.md#visual-identity--jarvis-interface-mark-i).
`ContentView.swift` was a bare text field with a one-shot request/response —
it had none of the streaming, history, draft-copy, or approvals behaviour
the web client already has; this phase closed both gaps at once. Built,
installed, and verified running on the physical iPhone.

- [x] Add an Asset Catalog color set with the core tokens (Void, VoidRaised,
      Panel, Line, LineHot, JarvisCyan, Wireframe, Hologram, StarkGold,
      Alert, Ink) — exact hex values from the DESIGN.md token table, so web
      and iOS can never drift (`Assets.xcassets`, `Theme.swift`)
- [x] Bundle Orbitron + JetBrains Mono as embedded fonts (`UIAppFonts` in
      `Info.plist` via `project.yml`); wordmark/headings in Orbitron, chrome
      and data readouts in JetBrains Mono, body text in system sans
  - Google's repo only ships variable fonts for these two families;
    instantiated static Medium/Bold (Orbitron) and Regular/Medium/Bold
    (JetBrains Mono) weights with `fonttools varLib.instancer` via `uvx`
    so SwiftUI's `Font.custom` can address them by PostScript name directly
- [x] Force dark color scheme app-wide (`UIUserInterfaceStyle: Dark` in
      `project.yml` + `.preferredColorScheme(.dark)` in `ContentView`) — the
      identity is committed-dark by design, no light theme
- [x] Rebuild the header to match the web app-head: small spinning
      arc-reactor mark, "JARVIS" wordmark with cyan glow, "Online" status
      pill with a breathing LED (`HeaderView.swift`)
- [x] Rebuild the transcript as chat bubbles matching the web styling:
      Jarvis left-aligned in cyan-bordered panels, you right-aligned in
      gold-bordered panels, "who" label above each (`MessageBubble.swift`)
- [x] Wire the composer (text field + Send button) to match the web
      styling: mono font, uppercase letter-spaced button label, cyan glow
      on focus/press (`ComposerView.swift`)
- [x] Switch networking from one-shot `URLSession.data(for:)` to a
      streaming NDJSON reader (`URLSession.bytes(for:).lines`, mirroring
      `/chat`'s one-`{"type":"tool"}`-line-per-call then a
      `{"type":"final"}` line) so a bubble shows "Calling `<tool>`…" while
      a tool call is in flight (`ChatViewModel.swift`)
- [x] Add the calculating-ring component (rotating cyan arc, matches the
      web `.calc`/`RING` markup) for the in-flight bubble
      (`CalculatingRing.swift`)
- [x] Keep session history client-side (array of `{role, content}`) and
      replay it on each request, matching the web client's `history` array
- [x] Add a Copy button on replies flagged `is_draft`, using
      `UIPasteboard.general.string` (mirrors the web `addCopyButton`)
- [x] Add an approvals view: render `pending` items from the response with
      individual Approve buttons that POST to `/apply` (mirrors
      `renderApprovals`; `ApprovalsBubble.swift`)
- [x] Respect Reduce Motion — `CalculatingRing`/`HeaderView`/`CalculatingLabel`
      check `@Environment(\.accessibilityReduceMotion)` and skip their
      animations when set
- [x] Swap the placeholder app icon for the arc-reactor mark asset described
      in DESIGN.md's Visual Assets section — generated a 1024×1024 PNG with
      Pillow (concentric rings, crosshair ticks, glowing core) matching the
      design proposal's icon spec

Post-launch polish, from testing on the physical device:

- [x] Render `**bold**` markdown in Jarvis's replies instead of showing
      literal asterisks (`AttributedString(markdown:)` in `MessageBubble`);
      your own messages stay plain text
- [x] Give Jarvis's replies a dedicated body font (JetBrains Mono, sized down
      one step to 13pt after review) while your own messages and the
      composer's typed text keep the plain system font
- [x] Fix the composer/bubble layout so the "Calculating…" row can't wrap to
      a second line (`fixedSize` + `lineLimit(1)`, trimmed side margins)
- [x] Fix the animated "…" glitching into a single ellipsis glyph — JetBrains
      Mono ligature-substitutes three periods; swapped the dots for plain
      circles instead of text characters
- [x] Add a distinct **Processing** ring (dual counter-rotating arcs, gold
      ring, pulsing core — the design proposal's second calculating tier) for
      when a tool call is actually in flight, separate from the plain
      **Thinking** ring shown before any tool call starts

## Phase 3 — Voice + reminder

The 10-minute ritual feel.

- [ ] Speech-to-text via `SFSpeechRecognizer` (push-to-talk)
- [ ] Text-to-speech via `AVSpeechSynthesizer` (spoken replies)
- [ ] Conversation UI works hands-free (speak → hear response)
- [ ] Daily morning reminder (local notification)

## Phase 4 — Desktop web front-end ⏳ IN PROGRESS

Same `/chat` backend, a second client. No new framework — plain HTML + fetch, served as a static file.

- [x] Add `backend/static/index.html`: textarea, send button, transcript view, plain JS `fetch()` to `/chat`
  - Inline emoji favicon (data URI) so the browser stops requesting `/favicon.ico` (was a harmless 404)
- [x] Load `backend/.env` via `python-dotenv` so `uv run uvicorn` picks up the API key locally (no-op in Docker)
- [x] Mount it in FastAPI with `StaticFiles` (mounted last so `/chat` + `/health` match first)
- [x] Reuse existing CORS/auth as needed for browser access over the tailnet
  - No CORS needed: the page is served by the backend, so `fetch('/chat')` is same-origin. No auth exists to reuse.
- [x] Stream tool-call progress to the chat UI
  - `/chat` now streams NDJSON (one `{"type":"tool",...}` line per tool call,
    then a final line with the reply) instead of one blocking JSON body
  - Chat bubble shows "Using `<tool>`…" while a tool call is in flight, then
    swaps in the final reply
- [~] Confirm plan display works in a wide viewport (no mobile constraints to design around)
  - Page is 800px-max centred, transcript style; structured plan display still pending Phase 1
- [x] Render `**bold**` markdown in Jarvis's replies (web), matching the iOS
      bubble's behaviour; own messages stay plain text. Jarvis's replies also
      switched to a dedicated JetBrains Mono body font, matching iOS.
- [ ] (Later) Persist chat history in the page via `localStorage` if useful

Not building: an in-app calendar/Trello view. Jarvis's writes already show up in the real Google Calendar/Trello apps — use those side-by-side with Jarvis instead of replicating their UI.

## Later — earn-their-place TODOs

- [ ] Test how JARVIS performs with a Sonnet instead of a Haiku brain
- [ ] Realtime cloud voice API (nicer, customisable voice) instead of Apple TTS
- [ ] Work calendar via Microsoft Graph / Outlook (security permitting)
- [ ] Gmail drafts instead of copy/paste messages
- [ ] Swap Claude Haiku for another model (possibly open-source)
- [ ] Decide on Apple Developer account ($99/yr recommended) for long-lived installs

## Bug fixes ⏳ IN PROGRESS

- [x] Bug where JARVIS asked to rename an existing event (which he didn't
      create) but he called the move_event tool so nothing happened
      (logged in `bugs/bug_log.txt` as "No modify_event tool"). Fixed by the
      calendar tools refactor: `move_event` replaced with `modify_event`,
      which patches any subset of fields (including title) on an event.
- [ ] The approval message showed a timestamp in a format that's a bit difficult to read - change to YYYY-MM-DD | hh:mm
- [ ] "Weekend" is sometimes misinterpreted instead of always meaning
      Saturday + Sunday in the current timezone — suspected BST/GMT confusion
      (logged in `bugs/bug_log.txt`)
- [x] Desktop redesign PR regressed the chat UI: reverted the NDJSON stream
      reader back to `res.json()` (broke tool-progress display with a JSON
      parse error) and silently dropped the `addCopyButton`/`renderApprovals`
      calls. Restored the streaming reader and re-wired both.
- [x] Approve/Copy buttons rendered oversized after the redesign (inherited
      the full Send-button styling, no `.mini` class defined). Added
      `button.mini` sizing plus proper row padding for the approvals box.
- [x] iOS standby arc-reactor mark rendered as a static (non-spinning) frame
      after returning from `.thinking`/`.processing` back to `.standby` —
      the `@State` spin animation was scoped to `HeaderView`, so it never
      restarted on remount. Moved to a dedicated `ArcReactorMark` view so
      its `onAppear` fires again each time it remounts.
