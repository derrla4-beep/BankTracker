# BankTracker — Design Spec

**Date:** 2026-07-22
**Owner:** Dhruv (BU Class of 2029, Finance + Data Science)
**Status:** Approved by user (Approach A)

## Purpose

Track investment banking recruiting timelines — application postings, early insight/diversity/sophomore programs, and BU campus events — for ~45 firms (bulge bracket, elite boutique, middle market), and alert Dhruv **before** applications open so he can network into each firm first.

Core insight: banks post applications on a highly predictable annual rhythm. A database of historical open dates per firm-program generates predicted open dates and pre-emptive "start networking now" alerts. A daily monitor catches the actual posting the moment it goes live.

## User context

- Rising sophomore (Class of 2029). Two overlapping recruiting tracks:
  1. **Early insight / diversity / sophomore programs for Summer 2027** — many open August–October 2026 (weeks away). Highest priority.
  2. **Junior Summer Analyst 2028 applications** — open roughly February–June 2027.
- Existing `Banking-Outreach` system (separate folder) handles networking. **Tracker stays standalone** — no integration (user decision).
- Geography: **US only** (NYC-focused programs).

## Decisions (user-confirmed)

| Decision | Choice |
|---|---|
| Runtime | Scheduled cloud agent (Claude Code routine), daily ~8am ET |
| Alerts | Google Calendar events + routine run-summary email as morning digest |
| Firm scope | BB + EB + MM, ~45 firms |
| Outreach integration | None — keep separate |
| Alert lead time | 4 weeks before predicted open, reminder at 1 week, alert on actual posting |
| Approach | A — prediction database + windowed monitoring |

## Architecture

No app server, no database. Plain JSON state files in a **private GitHub repo** (this folder), which the cloud agent reads/updates each run.

### Data files

- `data/firms.json` — ~45 firms: name, tier (`BB` | `EB` | `MM`), careers URL, insight-program page URL.
- `data/programs.json` — one entry per firm-program (e.g., "GS 2028 Summer Analyst IBD," "MS Early Insights 2027"): program type (`insight` | `SA`), historical open dates (by year), predicted open date, confidence, status (`predicted` → `open` → `closed`, or `unverified`), application link once live.
- `data/bu-events.json` — in-person/campus events relevant to BU students: firm, event, date, source URL.
- `state/calendar-sync.json` — program → Google Calendar event IDs, so runs are idempotent (update, never duplicate).

### Phase 1 — one-time build (Opus; judgment-heavy research)

1. Populate `firms.json` (all 9 BBs, ~12 EBs, ~15–20 MM firms).
2. Research historical application-open dates for every firm-program via web research (career pages, WSO threads, press/blog posts, community trackers). Insight programs for Summer 2027 first.
3. Compute predicted open dates; mark predictions with no historical basis `unverified`.
4. Create initial Google Calendar events per predicted program:
   - T−4 weeks: "Start networking — [firm] [program] opens in ~4 weeks"
   - T−1 week: reminder
   - T: tentative "[firm] [program] apps expected to open"
5. Record all created event IDs in `state/calendar-sync.json`.

### Phase 2 — daily routine (Sonnet; scheduled cloud agent, ~8am ET)

1. Load `programs.json`; select programs **in window** (within 5 weeks of predicted open, or `open`).
2. Check those programs' career pages; quick sweep of community aggregators (WSO tracker threads, job boards) to catch surprises outside the window.
3. On a live posting: status → `open`, save direct application link, update the calendar event to "🚨 [firm] [program] IS LIVE — apply," note it in the digest.
4. Run summary = morning digest: newly opened, opening soon (next 2 weeks), action items, anything `unverified` or failed to load.
5. Commit updated JSON state back to the repo.

### Phase 3 — weekly deep sweep (Mondays; same routine, extended)

- Re-validate predictions drifting stale (e.g., firm announced a different timeline).
- Scan for newly announced insight programs not yet in the database.
- BU events: BU CCD public events calendar, Questrom events, firms' campus-recruiting event pages. Best-effort (Handshake is login-walled). New events → `bu-events.json` + calendar events.

## Error handling

- Career page fails to load or scrape → flag in digest, don't guess; retry next run.
- Prediction with no historical evidence → `unverified`, surfaced in digest, never silently invented.
- Calendar writes idempotent via `state/calendar-sync.json`; on missing/deleted event IDs, recreate and re-record.
- Predicted dates are ±1–2 weeks accurate at best; the 4-week lead alert absorbs drift, and the daily monitor is the exactness backstop.

## Model division of labor

- **Fable:** design (this doc) + implementation plan.
- **Opus:** Phase 1 historical-dates research and database seeding.
- **Sonnet:** repo scaffolding, JSON schemas, calendar-sync logic, all recurring daily/weekly runs.

## Out of scope

- Networking/outreach management (lives in `Banking-Outreach`).
- EMEA/London programs.
- A live dashboard (declined; may revisit later).
- Handshake-authenticated event scraping.

## Success criteria

- Every in-scope firm-program has a calendar alert chain (T−4w / T−1w / T) before its predicted open.
- A posting that goes live is reflected in the calendar + digest within one daily run (≤24h).
- Zero duplicate calendar events across repeated runs.
- Daily runs are cheap: most days touch only in-window programs.
