# BankTracker

BankTracker tracks investment-banking recruiting timelines — application
postings, early insight/diversity/sophomore programs, and BU campus events —
for roughly 45 firms (bulge bracket, elite boutique, middle market), and
alerts before applications open so networking can happen first.

Core insight: banks post applications on a highly predictable annual rhythm.
A database of historical open dates per firm-program generates predicted
open dates and pre-emptive "start networking now" alerts. A daily monitor
catches the actual posting the moment it goes live.

There is no app server and no database — just plain JSON state files in
this repo, read and updated by a scheduled cloud agent.

## Data files

- `data/firms.json` — firms: id, name, tier (`BB` | `EB` | `MM`), careers
  URL, insight-program page URL.
- `data/programs.json` — one entry per firm-program: type (`insight` |
  `SA`), historical open dates, predicted open date, confidence, status.
- `data/bu-events.json` — BU campus events relevant to recruiting: firm,
  event, date, source URL.
- `state/calendar-sync.json` — program/event id → Google Calendar event
  IDs, so runs are idempotent (update, never duplicate).

The exact shape of each file is documented in [docs/schemas.md](docs/schemas.md).

## Phases

1. **Phase 1 — one-time build.** Populate `firms.json`, research historical
   application-open dates per firm-program, compute predicted open dates,
   and seed initial Google Calendar alerts (T−4w, T−1w, T).
2. **Phase 2 — daily routine (~8am ET).** Check in-window programs' career
   pages, catch live postings, update calendar events and state, and send
   a morning digest.
3. **Phase 3 — weekly deep sweep (Mondays).** Re-validate stale predictions,
   scan for newly announced programs, and best-effort scan for new BU
   events.

See the full design in
[docs/superpowers/specs/2026-07-22-banktracker-design.md](docs/superpowers/specs/2026-07-22-banktracker-design.md)
and the implementation plan in
[docs/superpowers/plans/2026-07-22-banktracker.md](docs/superpowers/plans/2026-07-22-banktracker.md).

## Validating the data

`scripts/validate.py` checks all four JSON state files against the schema
contract in `docs/schemas.md` — referential integrity (e.g., programs
pointing at real firm ids), enum values, date formats, and id uniqueness.

```bash
python scripts/validate.py
```

Exits `0` and prints a summary (e.g., `OK: 0 firms, 0 programs, 0 BU
events`) when everything is valid; exits `1` and prints one message per
problem otherwise. Every later task in this project runs this validator
before considering its work done.

Run the validator's own test suite (stdlib only, no pytest) with:

```bash
python tests/test_validate.py
```
