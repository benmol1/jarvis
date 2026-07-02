# Jarvis — TODO

Task breakdown for the phases in [DESIGN.md](DESIGN.md). Ship each phase end-to-end
before starting the next.

## Phase 0 — Plumbing

Prove the phone → Pi → Claude text round-trip.

- [ ] Pick backend language/framework (default: Python + FastAPI)
- [ ] Set up the orchestrator service on the Pi (single `/chat` endpoint, takes text, returns text)
- [ ] Store the Anthropic API key as a secret on the Pi (env file, not in code)
- [ ] Wire the `/chat` endpoint to Claude Haiku (single call site, easy to swap later)
- [ ] Confirm the Pi is reachable over the tailnet (Tailscale hostname + port)
- [ ] Minimal SwiftUI app: text box, send button, shows reply
- [ ] Round-trip works: type on phone → Pi → Claude → reply on phone

## Phase 1 — Read-only proposed plan

The core value, zero write risk.

- [ ] Create the "About Ben" profile store (a file on the Pi: priorities, scheduling rules, preferences, delighters)
- [ ] Google Calendar OAuth: one-time setup, store token on the Pi
- [ ] Calendar **read** tool for Claude (fetch today's / this week's events)
- [ ] Trello auth (API key + token) stored on the Pi
- [ ] Trello **read** tool for Claude (fetch cards/lists)
- [ ] Rolling-state store (yesterday's plan, what slipped, carried-forward priorities)
- [ ] System prompt assembles: profile + rolling state + live calendar + Trello
- [ ] Morning conversation produces a **proposed** time-boxed plan (text only, no writes)
- [ ] Display the proposed plan clearly in the app

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
