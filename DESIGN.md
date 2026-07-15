# Jarvis — Design

A personal daily-planning assistant. Ben talks to an iPhone app for ~10 minutes each
morning to align priorities, triage to-dos, and time-box the day into his calendar —
like a chief-of-staff stand-up. The conversation produces real calendar events and
draft messages, giving each day a clearer sense of purpose.

## Architecture

```
iPhone (SwiftUI)                 Raspberry Pi (over tailnet)         Cloud APIs
─────────────────                ───────────────────────────        ──────────
push-to-talk + text  ──HTTPS──▶  orchestrator service         ──▶   Claude Haiku (the brain)
Apple STT + TTS                  holds all secrets/tokens      ──▶   Google Calendar (read+write)
morning reminder                 memory store (files)          ──▶   Trello (read)
approval / draft view  ◀──────   returns transcript + actions
```

- **iOS app (native SwiftUI):** conversation UI (push-to-talk + text), on-device
  speech-to-text (`SFSpeechRecognizer`) and text-to-speech (`AVSpeechSynthesizer`),
  a daily morning reminder (local notification), and a view to approve/copy message
  drafts and see proposed/created calendar changes. Talks to the Pi over one HTTPS
  endpoint.
- **Backend (Raspberry Pi, single-user):** a small orchestrator service, reached over
  the existing Tailscale tailnet. Holds all secrets (Anthropic key, Google OAuth token,
  Trello key/token). Runs the Claude conversation with tool-use and returns the
  transcript plus proposed/executed actions.
- **LLM:** Claude Haiku to start, kept behind a single call site so it can be swapped
  later (no abstraction layer built up front).

### Why the Pi (latency vs security)

The Pi is an **I/O-bound orchestrator** — no model runs on it; it just relays kilobytes
of text to Claude/Google/Trello. So its CPU and home broadband are irrelevant to speed;
the tailnet hop is ~1–5% of a turn's latency, which is dominated by the LLM and voice.
In exchange you get a real security win (secrets never leave hardware you own; no public
attack surface) and zero hosting cost. The genuine constraints are uptime (single point
of failure) and no inbound webhooks — so we **poll** calendar/Trello on demand each
morning rather than subscribing to push. If the Pi ever proves flaky, moving the same
backend to a cheap cloud box is a config change, not a redesign.

## Memory (two tiers, stored on the Pi)

1. **"About Ben" profile** — perpetual, edited rarely, fed into every session's system
   prompt:
   - priorities: short / medium / long-term, split life vs work
   - explicit scheduling rules: work hours, lunch, focus blocks, **sacred family time**
   - preferences: exercise habits, in-person vs remote meeting patterns
   - delighters: what makes a day feel good and performant
2. **Rolling state** — the fluid layer: yesterday's plan, what slipped, priorities being
   pushed forward, recent session summaries. This is what makes it feel like an assistant
   who remembers.

Live calendar and Trello state are pulled fresh each session.

## Behaviour

- **Autonomy:** writes Ben's own time-boxes directly to Google Calendar; messages to
  other people are drafted for Ben to copy/paste (no automatic send).
- **Scheduling constraints:** taken from explicit rules in the profile, treated as
  guardrails.
- **Session trigger:** a daily morning reminder (local notification).

## Build phases

Ship the smallest thing that delivers the magic first.

| Phase | Deliverable |
|---|---|
| **0** | Pi backend reachable over tailnet; phone → Pi → Claude text round-trip |
| **1** | Read-only: Calendar + Trello + "About Ben" profile → a **proposed** morning plan (no writes) |
| **2** | Calendar **writes** (own time-boxes) + message drafts to copy |
| **3** | Voice both ways (Apple STT/TTS) + morning reminder notification |

### Later (earn-their-place TODOs)

- Realtime cloud voice API (nicer, customisable voice) instead of Apple TTS
- Work calendar via Microsoft Graph / Outlook (security permitting)
- Gmail drafts instead of copy/paste messages
- Swap Claude Haiku for another model (possibly open-source)

## Visual identity — "Jarvis Interface" (Mark I)

A HUD-inspired visual language drawn from Tony Stark's interface in *Iron Man* (2008):
a black void ground, pale bright-cyan wireframe, radial "calculating" motion, and the
suit's gold as a single warm accent. Committed **dark only** — the arc reactor glows in
darkness, so there is no light theme by design. One token set drives both platforms so
the web console and the iOS app read as the same machine.

### Core tokens (single source of truth)

| Token | Hex | Role | CSS var | SwiftUI (Asset Catalog) |
|---|---|---|---|---|
| Void | `#03070D` | Ground | `--void` | `Color("Void")` |
| Void-2 | `#061019` | Raised ground / fields | `--void-2` | `Color("VoidRaised")` |
| Panel | `#08151F` | Surface | `--panel` | `Color("Panel")` |
| Line | `#123246` | Hairline / grid | `--line` | `Color("Line")` |
| Line-hot | `#1D4E6B` | Active hairline | `--line-hot` | `Color("LineHot")` |
| Jarvis Cyan | `#5FE3FF` | Primary — Jarvis voice, focus, glow | `--cyan` | `Color("JarvisCyan")` |
| Wireframe | `#2F8FC4` | Strokes / structural lines | `--cyan-deep` | `Color("Wireframe")` |
| Hologram | `#E8FBFF` | Peak text | `--holo` | `Color("Hologram")` |
| Stark Gold | `#FFB547` | Secondary accent — user voice, alerts | `--gold` | `Color("StarkGold")` |
| Alert | `#FF5D4A` | Critical / errors | `--alert` | `Color("Alert")` |
| Ink | `#CFEEFC` | Default reading text | `--ink` | `Color("Ink")` |

Neutrals are blue-biased, never plain grey, so the whole surface reads as lit from within.

### Typography

- **Display / wordmark / headings:** Orbitron (geometric, futuristic).
- **Chrome / data / readouts:** JetBrains Mono (the "codey" voice; a free stand-in for the
  film's *Arame Mono*), uppercase and letter-spaced for labels.
- **Reading text:** system sans.
- Robust monospace fallbacks are declared so the look never silently breaks offline. iOS
  bundles the faces; web self-hosts or links them.

### Signature motion — the calculating ring

One reusable component in three tiers, replacing any plain "…" spinner:
**Thinking** (inline in a reply), **Processing** (full-screen, running tools),
**Listening** (voice capture / iOS push-to-talk). Concentric cyan rings rotate and pulse
while Jarvis works. All motion respects `prefers-reduced-motion`.

### Convention

Jarvis speaks in **cyan** (left-aligned); the user answers in **gold** (right-aligned).

### Status

- **Web console** (`backend/static/index.html`) — implemented (Mark I).
- **iOS app** (`ios/Jarvis/`) — to follow, reading the identical tokens from an Asset Catalog.

## Deployment

Native app for personal daily use — skip the App Store.

- **Free Apple ID sideload:** works but the install expires every 7 days and must be
  re-signed via Xcode. Painful for daily use.
- **Paid Apple Developer ($99/yr) — recommended:** installs last a year, plus TestFlight.
  Worth it to never think about re-signing something you open every morning.

### iOS toolchain (as built)

- **Xcode 16.4**, not the latest. The App Store only offers the newest Xcode (26), which
  requires macOS 26; the dev MacBook runs macOS 15.6.1 (Sequoia), so Xcode 16.4 — the last
  release supporting Sequoia — was installed via the `xcodes` CLI. A future macOS upgrade is
  the only path to newer Xcode, and isn't needed for this app.
- **Project generated with XcodeGen** from `ios/project.yml` (committed) rather than a
  hand-managed `.xcodeproj`. The spec is the source of truth — it pins the iOS 17 deployment
  target, iPhone-only, bundle id, and the ATS exception that allows plain-HTTP calls to the Pi
  over the tailnet. Regenerate with `xcodegen generate` in `ios/`.
