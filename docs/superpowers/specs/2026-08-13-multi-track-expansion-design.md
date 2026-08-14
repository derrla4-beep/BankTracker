# BankTracker Multi-Track Expansion — Design

**Date:** 2026-08-13
**Status:** Approved design, pending implementation plan

## Problem

BankTracker tracks 46 investment banks. When Capital One dropped a finance
internship, it never reached the calendar — not because of any keyword filter
(none exists), but because the entire pipeline is closed-world over
`data/firms.json`. A posting must clear four gates to reach the calendar, and
Capital One fails the first:

1. `validate.py` rejects any program whose `firm_id` is not in `firms.json`.
2. `ROUTINE.md` step 1 builds its check set only from existing `programs.json` rows.
3. The discovery sweep's queries are IB-worded by construction
   (`"...investment banking summer analyst..."`), so an untracked non-IB firm
   can never enter the system.
4. `tier` is `{BB, EB, MM}` and `type` is `{SA, insight}` — no slot for a
   consumer bank or a data-science internship.

The user is a dual major (finance + data science, BU class of 2029) and needs
coverage of corporate-finance and data-science recruiting alongside IB.

## Goals

- Track corporate-finance (CF) and data-science (DS) opportunities alongside IB.
- Never silently drop a live posting the routine cannot classify.
- Keep the existing IB data, workflow, and seeded calendar events bit-identical.
- Keep the per-run cost increase bounded and explicit.

## Non-goals

- Building prediction machinery (historical open dates → predicted dates) for
  CF/DS. Those tracks use detection, not prediction.
- Comprehensive firm coverage on day one. The seed is deliberately narrow.
- Ranking non-IB firms by prestige.

---

## 1. Data model

### 1.1 `data/firms.json`

Two field changes:

| Field | Change |
|---|---|
| `track` | **New, required.** `"IB"` \| `"CF"` \| `"DS"` |
| `tier` | Required `BB`/`EB`/`MM` when `track == "IB"`; must be `null` otherwise |
| `sweep_cadence` | **New.** `"every_run"` \| `"weekly"` for CF/DS; `null` for IB |

```json
{
  "id": "capital-one",
  "name": "Capital One",
  "track": "CF",
  "tier": null,
  "sweep_cadence": "weekly",
  "careers_url": "https://...",
  "insight_programs_url": null,
  "notes": ""
}
```

All 46 existing firms gain `"track": "IB"`, `"sweep_cadence": null`, and keep
their existing tier. No other change to IB rows.

**Null means present-and-null.** For `tier` and `sweep_cadence`, the validator
requires the key to be present with an explicit `null` value where the table
says null — a missing key is an error, not an implicit null. This keeps a
typo'd or forgotten field from silently reading as "intentionally empty".

**Why a separate `track` rather than extending `tier`:** `BB`/`EB`/`MM` is a
prestige grade *within* investment banking; `CF`/`DS` are domains. Conflating
them forces every "is this an IB firm?" check to become a hardcoded
`tier in (BB, EB, MM)` list — in the validator, the routine's cycle-ahead rule,
the digest tagger, and four places in the dashboard. Splitting the axes means
per-domain behavior keys off one field, and a fourth track later costs one enum
value plus one set of sweep queries.

`tier` is null for CF/DS rather than inventing a grade, because a prestige
ranking for tech companies is subjective and would not change any decision.

### 1.2 `data/programs.json`

Programs do **not** store `track`. It is derived through `firm_id`.
Denormalizing would let a program's track drift out of sync with its firm's,
and `validate.py` already enforces that `firm_id` resolves.

| Field | Change |
|---|---|
| `type` | Enum gains `"internship"` → `{SA, insight, internship}` |
| `target_summer` | **No change.** `2027 \| 2028` already covers sophomore and junior summer for a 2029 grad |

- `SA` becomes IB-only — "Summer Analyst" is an IB term of art. The validator
  rejects `type: "SA"` on a non-IB firm as an integrity check.
- `insight` stays cross-track (CF firms run sophomore insight programs too).
- `internship` is the CF/DS workhorse type.

The catch-it-fast CF/DS program shape needs **no new fields**:
`confidence: "unverified"`, `status: "unverified"`, `predicted_open: null`,
`historical_opens: {}` — already a valid combination under the existing
validator rules.

### 1.3 New file: `state/open-questions.json`

Persists unresolved ambiguous postings so the digest can age-tag them.

```json
{
  "questions": [
    {
      "id": "capital-one-fap-2026-08-13",
      "firm_id": "capital-one",
      "program_id": null,
      "track": "CF",
      "title": "<posting title exactly as seen>",
      "url": "https://...",
      "reason": "eligibility-unreadable",
      "first_seen": "2026-08-13",
      "last_seen": "2026-08-19",
      "resolved": false
    }
  ]
}
```

- `program_id` is **nullable on purpose** — it carries the case where the sweep
  finds a live posting at a firm with no program row yet. This is exactly the
  Capital One situation that motivated this work.
- `reason` is one of: `eligibility-unreadable`, `no-quotable-line`,
  `title-body-mismatch`, `page-load-failed`, `prediction-overdue`,
  `unverified-seen-posted`.
- `url` and `title` are nullable, and are null exactly when the entry has no
  posting behind it (`reason: "prediction-overdue"`). For every other reason
  both are required, since the whole point is to let the user click through.
- Age tag in the digest renders from `first_seen`.
- Resolved items keep `resolved: true` as history and drop out of the digest.

**Why not reuse `sightings`:** `validate.py` requires a non-empty `grad_years`
on every sighting. The defining property of these items is that the grad years
are unknown; forcing a value would write a guess into a field that holds facts.

---

## 2. The never-silently-drop invariant

Today a live IB posting that looks eligible but yields no quotable eligibility
line is correctly refused promotion to `open` by the cycle gate — and then
nothing happens. It is not a wrong-cycle sighting, so it misses 👀 WRONG CYCLE.
It is not promoted, so it misses 🚨 NEWLY OPEN. The user never learns a posting
went live. This is a real defect in the current system, independent of the
multi-track work.

> **Invariant: every live posting a run touches must exit through exactly one of
> three doors — promoted to `open`, recorded as a wrong-cycle sighting, or
> reported under ⚠️ NEEDS ATTENTION. Never none of them.**

This applies to **all three tracks**. ⚠️ NEEDS ATTENTION therefore catches:

1. Eligibility text absent or unparseable (all tracks)
2. Live and plausibly eligible, but no quotable line → cannot promote
3. Title cycle and eligibility text disagree
4. Page failed to load or was JS-blocked *(exists today)*
5. Overdue predictions; unverified programs seen posted *(exists today)*

Each entry carries firm, track tag, and a one-line reason. Entries arising from
a posting (reasons 1–4) also carry the posting title and **URL**, so the user
can settle it manually in seconds. Entries with no posting behind them
(`prediction-overdue`) carry the program id instead, and their `url` field is
null.

**Boundaries:**

- Confirmed wrong-cycle sightings stay in 👀 WRONG CYCLE. They are resolved,
  not ambiguous; routing ~35 known prior-cycle postings here every run would
  bury the genuinely unclear ones.
- **Nothing in ⚠️ NEEDS ATTENTION gets a calendar event.** The calendar stays
  the "this is real, act on it" channel; the digest is the "eyeball this"
  channel.
- ⚠️ NEEDS ATTENTION is **exempt from the ~25-line digest cap**. The other six
  lines stay tight.
- Unresolved items **re-report every run with an age tag** (`unresolved 6d`).
  New items this run are listed first. This keeps a skipped item from vanishing
  while signalling at a glance that it is not new.

### The cycle gate itself does not change

`validate.py`'s rule — `status: "open"` requires `profile.grad_year ∈
eligibility.grad_years` **and** `eligibility.verified == true` — is already
track-agnostic and correct for all three tracks. It is not modified.

What is IB-specific is the *inference rule* used to determine the audience, and
that lives in `ROUTINE.md` prose, not in the validator.

---

## 3. Per-track eligibility inference

This is the highest-risk correctness change. Applying the banking rule to a
tech posting would reject every eligible one.

**IB (unchanged, now under an explicit IB-only heading):** banks run a cycle
ahead. A live "2027 Summer Analyst" posting is for 2028 grads and is *not*
applicable to a 2029 grad. It belongs in `sightings`.

**CF and DS:** postings run roughly 6–12 months ahead, not 18. A Summer 2027
posting is the user's **sophomore summer and is applicable**. Sophomores are
genuinely hired for real DS/CF internships. The cycle-ahead rule must **not**
be applied.

**Satisfying the `quote` requirement on non-bank postings.** Tech postings
often do not state class years in bank dialect. The quote requirement is
satisfied by any one of:

- an explicit class-year list;
- a graduation-date window containing June 2029;
- a class-standing phrase ("rising junior", "sophomore") mapped to a grad year
  via `profile.grad_year`.

All three are quoted verbatim into `eligibility.quote` exactly as today. A
posting stating *nothing* about eligibility is never auto-promoted and goes to
⚠️ NEEDS ATTENTION.

This preserves the safety property — never alert on something inapplicable,
never claim open without the posting's own words — while making it satisfiable
on postings that do not speak in bank dialect.

---

## 4. Routine changes (`ROUTINE.md`)

### 4.1 Check set per run

| Track | Cadence |
|---|---|
| IB | Unchanged — in-window set from `predicted_open` (currently 1 program) |
| CF/DS with `sweep_cadence: "every_run"` | All 3 runs/week (~6–8 firms) |
| CF/DS with `sweep_cadence: "weekly"` | Monday deep sweep only (~25 firms) |

**Cost rationale.** The current Wed/Fri run checks ~1 program and is nearly
free; Monday is the expensive run because it already sweeps 45 unverified
programs. Checking all ~30 new CF/DS firms every run would take Wed/Fri from ~1
check to ~31 — a ~30× increase on those runs. The split keeps Wed/Fri at ~8
while the remaining firms ride along with a Monday sweep whose marginal cost is
near zero.

### 4.2 Sweep queries

Per-track generic searches in step 3, replacing the two IB-only queries. Concrete
starting strings (the implementation may refine wording, but the *number* of
searches per run should stay at two per track to bound cost):

- **IB** (unchanged): `2028 investment banking summer analyst application open`;
  `2027 sophomore insight program investment banking open`; plus the WSO
  SA-timeline thread.
- **CF:** `2027 corporate finance summer internship application open`;
  `2027 financial analyst development program sophomore internship open`.
- **DS:** `2027 data science summer internship undergraduate application open`;
  `2027 machine learning internship sophomore application open`.

Because CF/DS postings for the user's sophomore summer are applicable (§3), the
CF/DS queries target cycle year 2027, while the IB queries target 2028. This is
intentional and is the query-level expression of the per-track inference rule.

### 4.3 Digest

- Entries prefixed with `[IB]` / `[CF]` / `[DS]`.
- ⚠️ NEEDS ATTENTION uncapped, age-tagged, URLs included, new items first.
- ✅ RUN OK footer counts break out per track.
- Push notification stays one line under 200 characters, leading with the most
  actionable item regardless of track.

### 4.4 Calendar

CF/DS programs have no `predicted_open`, therefore **no T−4w/T−1w/T chain**.
They receive a calendar event only at the moment a posting is caught live. The
existing 32 predicted IB programs and their seeded events are untouched. No
re-seeding occurs.

---

## 5. Dashboard changes (`dashboard.html`)

Four hardcoded locations gain the track axis:

| Location | Change |
|---|---|
| `:174-175` tier filter | Add a track filter alongside; tier filter applies only to IB rows |
| `:217` `TIER` map | Add a `TRACK` map |
| `:237` stat rollup | Group by track |
| `:319` tag cell | Render track for non-IB, tier for IB |

`build_dashboard.py` needs one change: include `open-questions.json` in the
`DATA` blob so unresolved items are visible on the dashboard.

---

## 6. Seed data

Narrow starter set, grown over time by the widened sweep.

- ~12 CF firms, ~18 DS firms.
- All seeded `status: "unverified"`, `confidence: "unverified"`,
  `predicted_open: null`, `historical_opens: {}`.
- **No dates are invented.** Seeding requires only a real firm name and a real
  careers URL, both verified by fetching. Anything unverifiable is not seeded.
- ~6–8 firms marked `sweep_cadence: "every_run"`; the rest `"weekly"`. The
  priority set is chosen by the user during spec review.

---

## 7. Testing

`tests/test_validate.py` extends to cover:

- `track` enum accepts `IB`/`CF`/`DS`, rejects others
- `tier` required and valid when `track == "IB"`; must be null otherwise
- `type: "SA"` rejected on a non-IB firm
- `type: "internship"` accepted
- `sweep_cadence` required for CF/DS, null for IB
- `open-questions.json` shape: required fields, date formats, nullable
  `program_id`, `firm_id` referential integrity, id uniqueness

Verification before completion: `python scripts/validate.py`,
`python scripts/build_dashboard.py`, and `python tests/test_validate.py` all
pass.

---

## 8. Infrastructure notes

The routine (`trig_01XsSKnLsxa26JZhVBfybwjt`, "BankTracker monitor (Mon/Wed/Fri)")
runs `claude-sonnet-5` on `0 12 * * 1,3,5` (8am ET). **No model change.**
Dropping to a weaker model is not advised: the routine's core task is reading a
posting's eligibility line and judging applicability, and a confident misread
passes the validator's gate — which checks that a quote exists, not that it was
read correctly — putting a false 🚨 event on the calendar.

The routine prompt itself needs a small update: it currently describes the repo
as tracking "investment-banking recruiting timelines" for "a Boston University
sophomore". That framing should widen to the three tracks.

---

## 9. Implementation ordering

The pieces are tightly coupled (nothing can be seeded before the schema exists,
nothing validates before the validator knows the new fields), so this is one
plan with a strict sequence rather than parallel workstreams:

1. **Schema + validator + tests** — `docs/schemas.md`, `validate.py`,
   `tests/test_validate.py`. Ends green with the existing data untouched except
   the mechanical `track`/`sweep_cadence` backfill on 46 IB firms.
2. **`state/open-questions.json`** — empty file, validator coverage, dashboard
   builder wiring.
3. **Seed CF/DS firms and programs** — research and verify URLs; validator green.
4. **`ROUTINE.md`** — per-track inference, cadence, sweep queries, three-door
   invariant, digest format.
5. **`dashboard.html`** — track axis in the four hardcoded locations; rebuild
   and eyeball the rendered page, since the dashboard has no automated test.
6. **Routine prompt update** — widen the framing via `RemoteTrigger` update.

Step 1 is the only step that touches existing IB data. It must leave
`validate.py` and `tests/test_validate.py` passing before anything else starts.

## Open items for user review

1. Which ~6–8 CF/DS firms should be `sweep_cadence: "every_run"`.
2. Confirm the CF and DS starter firm lists once researched.
