# Multi-Track Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend BankTracker from investment-banking-only to three tracks — investment banking (IB), corporate finance (CF), and data science (DS) — so a dual-major student sees all three in one dashboard and one digest.

**Architecture:** Firms gain a `tracks` list; programs gain a single authoritative `track` that the validator constrains to be a member of its firm's `tracks`. Per-domain behavior (cycle inference, sweep cadence, digest tag) keys off that one axis. CF/DS use detection, not prediction: they carry no `predicted_open` and no T−4w/T−1w/T calendar chain, only a live-catch event.

**Tech Stack:** Python 3 (stdlib only — no third-party deps anywhere in this repo), plain JSON state files, a single self-contained `dashboard.html` with inlined data, and a scheduled cloud agent driven by `ROUTINE.md`.

**Spec:** `docs/superpowers/specs/2026-08-13-multi-track-expansion-design.md`

## Global Constraints

- **Stdlib only.** No pip installs. Tests are plain Python scripts run with `python tests/<name>.py`, exiting 0/1. Do not introduce pytest.
- **Never fabricate a date, a URL, or a posting.** Every seeded `careers_url` must be confirmed by actually fetching it. Anything unconfirmed is dropped, not guessed.
- **`profile.grad_year` is 2029.** Sophomore summer is 2027, junior summer is 2028.
- **`target_summer` accepts only `2027` or `2028`.** Do not widen this.
- **Never widen `eligibility.grad_years` to make a validator error go away.** If the validator rejects a change, the posting is the problem.
- **Never delete calendar events**, and never re-seed the existing IB calendar chain.
- **Line endings:** files are stored LF; the working copy is CRLF on Windows (`core.autocrlf=true`). Do not "fix" line endings in files you touch.
- **Commit after every task.** Run `python scripts/validate.py` and both test suites before each commit.

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `scripts/validate.py` | Schema contract for all five JSON files | 1 |
| `tests/test_validate.py` | Validator behavior, incl. the cycle gate | 1 |
| `data/firms.json` | Firm registry; gains `tracks`, `sweep_cadence` | 1, 2 |
| `data/programs.json` | Program registry; gains `track` | 1, 2 |
| `docs/schemas.md` | Human-readable schema contract | 1 |
| `ROUTINE.md` | The cloud agent's operating instructions | 3 |
| `scripts/build_dashboard.py` | Inlines JSON into `dashboard.html` | 4 |
| `tests/test_build_dashboard.py` | Builder behavior | 4 |
| `dashboard.html` | The one page the student actually reads | 4 |

Tasks are strictly sequential: nothing can be seeded before the schema exists, and nothing validates before the validator knows the new fields.

---

### Task 1: Track-aware schema and validator

**Files:**
- Modify: `scripts/validate.py:6-10` (constants), firm loop, program loop
- Modify: `tests/test_validate.py:20-27` (fixtures), append new tests
- Modify: `data/firms.json` (backfill 46 firms)
- Modify: `data/programs.json` (backfill 79 programs)
- Modify: `docs/schemas.md`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `firms[].tracks: list[str]`, `firms[].sweep_cadence: str | None`, `programs[].track: str`. Validator constants `TRACKS = {"IB","CF","DS"}` (already present) and new `CADENCES = {"every_run","weekly"}`. Tasks 2–4 depend on all of these.

- [ ] **Step 1: Update the test fixtures to carry the new fields**

In `tests/test_validate.py`, replace the `GOOD_FIRM` and `GOOD_PROG` constants:

```python
GOOD_FIRM = {"id": "goldman-sachs", "name": "Goldman Sachs", "tracks": ["IB"], "tier": "BB",
             "sweep_cadence": None, "careers_url": "https://x.com",
             "insight_programs_url": None, "notes": ""}
GOOD_PROG = {"id": "goldman-sachs-2028-sa-ib", "firm_id": "goldman-sachs",
             "name": "2028 SA IB", "track": "IB", "type": "SA", "target_summer": 2028,
             "eligibility": {"grad_years": [2029], "verified": False, "source": None, "quote": None},
             "historical_opens": {"2027": "2026-03-02"}, "predicted_open": "2027-03-01",
             "confidence": "medium", "status": "predicted", "application_url": None,
             "sources": ["https://x.com"], "sightings": [], "last_checked": None, "notes": ""}
```

Also add a CF firm fixture directly below `VERIFIED_ELIG`:

```python
CF_FIRM = {"id": "capital-one", "name": "Capital One", "tracks": ["CF"], "tier": None,
           "sweep_cadence": "weekly", "careers_url": "https://x.com/co",
           "insight_programs_url": None, "notes": ""}
CF_PROG = {"id": "capital-one-2027-cf-internship", "firm_id": "capital-one",
           "name": "2027 Finance Internship", "track": "CF", "type": "internship",
           "target_summer": 2027,
           "eligibility": {"grad_years": [2029], "verified": False, "source": None, "quote": None},
           "historical_opens": {}, "predicted_open": None,
           "confidence": "unverified", "status": "unverified", "application_url": None,
           "sources": ["https://x.com/co"], "sightings": [], "last_checked": None, "notes": ""}
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_validate.py`, immediately before the final `sys.exit(0 if ok else 1)`:

```python
# --- tracks ---
# 33. A CF firm with a CF program is valid
d = make_fixture([CF_FIRM], [CF_PROG], [], {"programs": {}, "bu_events": {}})
ok &= test("CF firm and program accepted", run_validator(d).returncode == 0); shutil.rmtree(d)
# 34. A firm may span tracks, and carry a program on each
multi = dict(CF_FIRM, id="amazon", name="Amazon", tracks=["CF", "DS"], sweep_cadence="every_run")
p_cf = dict(CF_PROG, id="amazon-2027-cf", firm_id="amazon", track="CF")
p_ds = dict(CF_PROG, id="amazon-2027-ds", firm_id="amazon", track="DS")
d = make_fixture([multi], [p_cf, p_ds], [], {"programs": {}, "bu_events": {}})
ok &= test("multi-track firm accepted", run_validator(d).returncode == 0); shutil.rmtree(d)
# 35. A program cannot claim a track its firm does not have
stray = dict(CF_PROG, track="DS")
d = make_fixture([CF_FIRM], [stray], [], {"programs": {}, "bu_events": {}})
ok &= test("program track outside firm tracks rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 36. Empty tracks list fails
d = make_fixture([dict(CF_FIRM, tracks=[])], [], [], {"programs": {}, "bu_events": {}})
ok &= test("empty tracks rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 37. Unknown track value fails
d = make_fixture([dict(CF_FIRM, tracks=["BANKING"])], [], [], {"programs": {}, "bu_events": {}})
ok &= test("unknown track rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 38. Duplicate entries in tracks fail
d = make_fixture([dict(CF_FIRM, tracks=["CF", "CF"])], [], [], {"programs": {}, "bu_events": {}})
ok &= test("duplicate tracks rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 39. A non-IB firm must not carry a tier
d = make_fixture([dict(CF_FIRM, tier="BB")], [], [], {"programs": {}, "bu_events": {}})
ok &= test("tier on non-IB firm rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 40. An IB firm must carry a valid tier
d = make_fixture([dict(GOOD_FIRM, tier=None)], [], [], {"programs": {}, "bu_events": {}})
ok &= test("null tier on IB firm rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 41. A missing key is not an implicit null
nokey = {k: v for k, v in CF_FIRM.items() if k != "tier"}
d = make_fixture([nokey], [], [], {"programs": {}, "bu_events": {}})
ok &= test("missing tier key rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 42. A firm with any non-IB track needs a cadence
d = make_fixture([dict(CF_FIRM, sweep_cadence=None)], [], [], {"programs": {}, "bu_events": {}})
ok &= test("null cadence on CF firm rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 43. An IB-only firm is paced by predicted_open, so its cadence must be null
d = make_fixture([dict(GOOD_FIRM, sweep_cadence="weekly")], [], [], {"programs": {}, "bu_events": {}})
ok &= test("cadence on IB-only firm rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 44. A firm on both IB and DS still needs a cadence for its DS side
both = dict(GOOD_FIRM, id="jp-morgan", name="J.P. Morgan", tracks=["IB", "DS"],
            sweep_cadence="weekly")
d = make_fixture([both], [], [], {"programs": {}, "bu_events": {}})
ok &= test("IB+DS firm with cadence accepted", run_validator(d).returncode == 0); shutil.rmtree(d)
# 45. "SA" is an investment-banking term and must not appear off the IB track
d = make_fixture([CF_FIRM], [dict(CF_PROG, type="SA")], [], {"programs": {}, "bu_events": {}})
ok &= test("SA type on non-IB track rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 46. "internship" is accepted
d = make_fixture([CF_FIRM], [CF_PROG], [], {"programs": {}, "bu_events": {}})
ok &= test("internship type accepted", run_validator(d).returncode == 0); shutil.rmtree(d)
# 47. Unknown program track fails
d = make_fixture([CF_FIRM], [dict(CF_PROG, track="OTHER")], [], {"programs": {}, "bu_events": {}})
ok &= test("unknown program track rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python tests/test_validate.py`

Expected: tests 1–32 FAIL too, because the fixtures now carry fields the validator does not know and lack the `tier` the old code demands. That is expected at this step — the whole suite goes red. Confirm you see `FAIL` lines among tests 33–47 specifically, then proceed.

- [ ] **Step 4: Add the new constants**

In `scripts/validate.py`, below the existing `TRACKS` line, add:

```python
CADENCES = {"every_run", "weekly"}
```

And change the `TYPES` line to:

```python
TYPES = {"SA", "insight", "internship"}
```

- [ ] **Step 5: Make the firm loop track-aware**

In `scripts/validate.py`, replace this line inside the firm loop:

```python
        if f.get("tier") not in TIERS: err(errors, f"{label}: bad tier {f.get('tier')!r}")
```

with:

```python
        tracks = f.get("tracks")
        if not (isinstance(tracks, list) and tracks and all(t in TRACKS for t in tracks)):
            err(errors, f"{label}: tracks must be a non-empty list over {sorted(TRACKS)}")
            tracks = []
        elif len(set(tracks)) != len(tracks):
            err(errors, f"{label}: duplicate entries in tracks {tracks}")
        firm_tracks[fid] = tracks
        # tier grades investment banks; it has no meaning off the IB track.
        if "IB" in tracks:
            if f.get("tier") not in TIERS: err(errors, f"{label}: bad tier {f.get('tier')!r}")
        elif "tier" not in f or f["tier"] is not None:
            err(errors, f"{label}: tier must be present and null for a non-IB firm")
        # Cadence paces CF/DS checks. IB programs are paced by predicted_open instead,
        # so a firm that is only IB carries no cadence.
        if set(tracks) - {"IB"}:
            if f.get("sweep_cadence") not in CADENCES:
                err(errors, f"{label}: bad sweep_cadence {f.get('sweep_cadence')!r}")
        elif "sweep_cadence" not in f or f["sweep_cadence"] is not None:
            err(errors, f"{label}: sweep_cadence must be present and null for an IB-only firm")
```

Then, immediately above the `for f in firms_list:` line, add:

```python
    firm_tracks = {}
```

- [ ] **Step 6: Make the program loop track-aware**

In `scripts/validate.py`, immediately after this line inside the program loop:

```python
        if pr.get("type") not in TYPES: err(errors, f"{label}: bad type {pr.get('type')!r}")
```

add:

```python
        track = pr.get("track")
        if track not in TRACKS:
            err(errors, f"{label}: bad track {track!r}")
        elif track not in firm_tracks.get(pr.get("firm_id"), []):
            err(errors, f"{label}: track {track!r} is not among its firm's tracks "
                        f"{firm_tracks.get(pr.get('firm_id'), [])}")
        # "Summer Analyst" is an investment-banking term of art.
        if pr.get("type") == "SA" and track != "IB":
            err(errors, f"{label}: type 'SA' is investment-banking only (track is {track!r})")
```

- [ ] **Step 7: Backfill the existing 46 firms and 79 programs**

Run this one-off script from the repo root:

```bash
python - <<'EOF'
import json
p = "data/firms.json"
doc = json.load(open(p, encoding="utf-8"))
for f in doc["firms"]:
    f["tracks"] = ["IB"]
    f["sweep_cadence"] = None
json.dump(doc, open(p, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
open(p, "a", encoding="utf-8").write("\n")

p = "data/programs.json"
doc = json.load(open(p, encoding="utf-8"))
for pr in doc["programs"]:
    pr["track"] = "IB"
json.dump(doc, open(p, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
open(p, "a", encoding="utf-8").write("\n")
print("backfilled", len(doc["programs"]), "programs")
EOF
```

- [ ] **Step 8: Run everything to verify green**

Run: `python tests/test_validate.py && python scripts/validate.py`

Expected: all 47 tests print `PASS`, then `OK: 46 firms, 79 programs, 0 BU events, 0 open questions`.

If any of tests 1–32 still fail, the fixture edit in Step 1 is incomplete — fix the fixture, not the validator.

- [ ] **Step 9: Update `docs/schemas.md`**

In the `data/firms.json` section, replace the bullet reading ``- `id`: kebab-case, unique. `tier`: `"BB"` | `"EB"` | `"MM"`.`` with:

```markdown
- `id`: kebab-case, unique.
- `tracks`: non-empty list, no duplicates, over `"IB"` | `"CF"` | `"DS"`. A firm
  may recruit on several tracks (Amazon runs both corporate-finance and
  data-science pipelines).
- `tier`: `"BB"` | `"EB"` | `"MM"` when `"IB"` is in `tracks`; otherwise must be
  present and `null`. Tier grades investment banks and has no meaning off that
  track.
- `sweep_cadence`: `"every_run"` | `"weekly"` when `tracks` holds any non-IB
  track; otherwise present and `null`. IB programs are paced by `predicted_open`
  instead.
- A *missing* `tier` or `sweep_cadence` key is an error, not an implicit null.
```

In the `data/programs.json` section, replace ``- `type`: `"SA"` | `"insight"`. `target_summer`: int (2027 or 2028).`` with:

```markdown
- `track`: `"IB"` | `"CF"` | `"DS"`, and must be one of the owning firm's
  `tracks`. Programs carry the authoritative track because behavior is decided
  per posting and a firm may span several tracks.
- `type`: `"SA"` | `"insight"` | `"internship"`. `"SA"` is investment-banking
  only. `target_summer`: int (2027 or 2028).
```

- [ ] **Step 10: Commit**

```bash
git add scripts/validate.py tests/test_validate.py data/firms.json data/programs.json docs/schemas.md
git commit -m "feat: track-aware schema for IB, CF and DS"
```

---

### Task 2: Seed corporate-finance and data-science firms

**Files:**
- Modify: `data/firms.json`
- Modify: `data/programs.json`

**Interfaces:**
- Consumes: `tracks`, `sweep_cadence`, `track` from Task 1.
- Produces: firm ids used by Tasks 3–4 for reporting. Priority firm ids: `anthropic`, `exxonmobil`, `spacex`, `google`, `amazon`.

This is a research task. The firm names below are fixed; every URL is an output you must confirm, never recall.

- [ ] **Step 1: Verify each careers URL by fetching it**

For each firm below, find its university/student careers page and fetch it. Record the URL only if the fetch succeeds and the page is actually a student/intern careers page. **If a URL cannot be confirmed, drop that firm from the seed entirely and note it in the commit message.** Do not guess a URL from a pattern.

Priority firms (`sweep_cadence: "every_run"`):

| id | name | tracks |
|---|---|---|
| `anthropic` | Anthropic | `["DS"]` |
| `spacex` | SpaceX | `["DS"]` |
| `google` | Google | `["CF", "DS"]` |
| `amazon` | Amazon | `["CF", "DS"]` |
| `exxonmobil` | ExxonMobil | `["CF", "DS"]` |

Remaining firms (`sweep_cadence: "weekly"`):

| id | name | tracks |
|---|---|---|
| `capital-one` | Capital One | `["CF", "DS"]` |
| `american-express` | American Express | `["CF"]` |
| `fidelity-investments` | Fidelity Investments | `["CF"]` |
| `charles-schwab` | Charles Schwab | `["CF"]` |
| `discover` | Discover Financial Services | `["CF"]` |
| `synchrony` | Synchrony Financial | `["CF"]` |
| `paypal` | PayPal | `["CF", "DS"]` |
| `visa` | Visa | `["CF", "DS"]` |
| `mastercard` | Mastercard | `["CF", "DS"]` |
| `johnson-and-johnson` | Johnson & Johnson | `["CF"]` |
| `procter-and-gamble` | Procter & Gamble | `["CF"]` |
| `ge-aerospace` | GE Aerospace | `["CF"]` |
| `openai` | OpenAI | `["DS"]` |
| `meta` | Meta | `["DS"]` |
| `microsoft` | Microsoft | `["DS"]` |
| `apple` | Apple | `["DS"]` |
| `nvidia` | NVIDIA | `["DS"]` |
| `databricks` | Databricks | `["DS"]` |
| `palantir` | Palantir | `["DS"]` |
| `stripe` | Stripe | `["DS"]` |
| `netflix` | Netflix | `["DS"]` |
| `two-sigma` | Two Sigma | `["DS"]` |
| `jane-street` | Jane Street | `["DS"]` |
| `citadel` | Citadel | `["DS"]` |
| `de-shaw` | D. E. Shaw | `["DS"]` |

- [ ] **Step 2: Append the firm entries**

For each confirmed firm, append to `data/firms.json` in this exact shape (example shown for Anthropic; substitute the confirmed URL):

```json
{
  "id": "anthropic",
  "name": "Anthropic",
  "tracks": ["DS"],
  "tier": null,
  "sweep_cadence": "every_run",
  "careers_url": "<the URL you confirmed>",
  "insight_programs_url": null,
  "notes": ""
}
```

- [ ] **Step 3: Append one program per firm per track**

Seed `target_summer: 2027` — that is the student's sophomore summer, and it is the cycle that opens during autumn 2026. Every seeded program uses the catch-it-fast shape: no invented dates, nothing predicted.

```json
{
  "id": "anthropic-2027-ds-internship",
  "firm_id": "anthropic",
  "name": "2027 Data Science / ML Internship",
  "track": "DS",
  "type": "internship",
  "target_summer": 2027,
  "eligibility": {"grad_years": [2029], "verified": false, "source": null, "quote": null},
  "historical_opens": {},
  "predicted_open": null,
  "confidence": "unverified",
  "status": "unverified",
  "application_url": null,
  "sources": ["<the same confirmed careers URL>"],
  "sightings": [],
  "last_checked": null,
  "notes": ""
}
```

Program id pattern: `<firm-id>-2027-<track lowercased>-internship`. A dual-track firm gets two rows, e.g. `amazon-2027-cf-internship` and `amazon-2027-ds-internship`.

- [ ] **Step 4: Validate**

Run: `python scripts/validate.py`

Expected: `OK: <N> firms, <M> programs, 0 BU events, 0 open questions` with N and M grown by exactly the number you seeded. Any error here means a seeded row is malformed — fix the row.

- [ ] **Step 5: Commit**

```bash
git add data/firms.json data/programs.json
git commit -m "feat: seed corporate-finance and data-science firms"
```

---

### Task 3: Teach ROUTINE.md the three tracks

**Files:**
- Modify: `ROUTINE.md`

**Interfaces:**
- Consumes: `tracks`, `sweep_cadence`, `track` from Task 1; seeded firms from Task 2.
- Produces: no code interface. Changes agent behavior only.

This task has no automated test — `ROUTINE.md` is prose read by the cloud agent. Its correctness gate is Step 5's read-through.

- [ ] **Step 1: Widen the "Who this is for" section**

In `ROUTINE.md`, immediately after the paragraph ending "...does the posting's own stated eligibility include a 2029 grad?", insert:

```markdown
### Three tracks, two different clocks

Programs carry a `track`: `IB` (investment banking), `CF` (corporate finance),
`DS` (data science). The student is a dual major — finance and data science —
so all three matter. Firms carry a `tracks` list and may appear on several.

**The cycle-ahead rule above applies to IB only.** Banks run roughly 18 months
ahead, which is why a live "2027 Summer Analyst" posting is for 2028 grads and
is not ours.

**CF and DS run 6–12 months ahead, not 18.** For those tracks a Summer 2027
posting is the student's *sophomore summer* and **is applicable**. Sophomores
are genuinely hired into real CF and DS internships, unlike IB where sophomore
year is insight programs only. Never apply the cycle-ahead rule to a CF or DS
posting — doing so would reject every posting the student can actually take.

**Reading eligibility off a non-bank posting.** Tech and corporate postings
rarely name class years the way banks do. Treat the `quote` requirement as
satisfied by any one of: an explicit class-year list; a graduation-date window
that contains June 2029; or a class-standing phrase ("rising junior",
"sophomore") that maps to a grad year via `profile.grad_year`. Quote whichever
one you find, verbatim, as always. A posting that says nothing at all about
eligibility is never promoted — file it as an open question.
```

- [ ] **Step 2: Replace the in-window definition in step 1**

Replace the whole of numbered step 1 with:

```markdown
1. Read `data/programs.json` and `data/firms.json`. Build the **check set** for this run:
   - **IB programs:** status `"predicted"` with `predicted_open` within the next 35 days or in the past, plus all status `"open"` programs whose deadline has not clearly passed. (Unchanged.)
   - **CF/DS programs** at a firm with `sweep_cadence: "every_run"`: always, on every run.
   - **CF/DS programs** at a firm with `sweep_cadence: "weekly"`: on Monday runs only.

   CF/DS programs have no `predicted_open`, so the in-window notion does not apply to them; cadence replaces it. A firm carrying both IB and non-IB tracks uses the IB rule for its IB programs and its cadence for the rest — the two coexist without interacting.
```

- [ ] **Step 3: Add per-track sweep queries to step 3**

Replace numbered step 3 with:

```markdown
3. Quick surprise sweep (once per run, not per firm) — two searches per track, six total:
   - **IB:** WebSearch `2028 investment banking summer analyst application open` and `2027 sophomore insight program investment banking open`, and scan the current WSO SA-timeline thread.
   - **CF:** WebSearch `2027 corporate finance summer internship application open` and `2027 financial analyst development program sophomore internship open`.
   - **DS:** WebSearch `2027 data science summer internship undergraduate application open` and `2027 machine learning internship sophomore application open`.

   The IB queries target cycle 2028 while CF/DS target 2027. That is deliberate: it is the query-level expression of the two clocks described above. If a NOT-in-check-set program turns out to be live, treat it like a check-set hit. If a live posting belongs to a firm not in `firms.json` at all, do not discard it — file an open question with `program_id: null` so it surfaces for triage.
```

- [ ] **Step 4: Tag digest lines by track**

In the Digest section's fenced format block, prefix the five content lines so each entry carries its track. Replace the block's first five lines with:

```
🚨 NEWLY OPEN (apply + use your contacts): [IB|CF|DS] <firm — program — application link>, or "none"
📅 OPENING SOON (next 14 days): [IB] <firm — program — predicted date>, or "none"
🎯 START NETWORKING (4-week window entered today/this week): [IB] <firm — program>, or "none"
👀 WRONG CYCLE (intel only — do not apply): [IB|CF|DS] <firm — posting title — cycle — who it's for>, or "none"
🏫 BU EVENTS ADDED/UPCOMING (7 days): <event — date>, or "none"
```

Then below the fence, immediately after the "Keep it under ~25 lines" paragraph, add:

```markdown
📅 OPENING SOON and 🎯 START NETWORKING are IB-only by construction: CF/DS programs carry no `predicted_open`, so there is no date to count down to. They reach the digest by going live (🚨) or by becoming an open question (⚠️), never by prediction.
```

- [ ] **Step 5: Update the RUN OK footer**

Replace the `✅ RUN OK` line inside the fence with:

```
✅ RUN OK <date> — checked <N> (<I> IB in-window, <C> CF/DS by cadence), <M> open, <U> unverified swept; next predicted open: <firm> <date> (T−<days>d); commit <sha7>
```

- [ ] **Step 6: Read the whole file back and check for contradictions**

Run: `python -c "print(open('ROUTINE.md',encoding='utf-8').read())"` and read it end to end.

Confirm all four hold:
1. The cycle-ahead rule appears only under the IB heading, never as a global rule.
2. No rule seeds a T−4w/T−1w/T chain for a CF/DS program *by default* — they carry no `predicted_open`, so there is nothing to count down to, and they reach the calendar only by being caught live. (The existing Monday rule that promotes a program to `"predicted"` when a firm *announces* a concrete open date still applies to all tracks and correctly earns a chain; that is not a contradiction.)
3. The three-door rule from step 4 is intact and still applies to all tracks.
4. Step 1's check set and the footer's `<I>`/`<C>` counts refer to the same sets.

Fix any contradiction before committing.

- [ ] **Step 7: Commit**

```bash
git add ROUTINE.md
git commit -m "feat: teach the routine three tracks and two clocks"
```

---

### Task 4: Surface tracks and open questions on the dashboard

**Files:**
- Modify: `scripts/build_dashboard.py:29-37`
- Modify: `tests/test_build_dashboard.py`
- Modify: `dashboard.html:174-175, 217, 237, 319, 333` and the section markup

**Interfaces:**
- Consumes: `tracks`, `track` from Task 1; `state/open-questions.json` (already shipped).
- Produces: `DATA.questions` in the inlined blob.

- [ ] **Step 1: Write the failing test for the data blob**

In `tests/test_build_dashboard.py`, add `open-questions.json` to `make_repo` — inside the function, after the `calendar-sync.json` line:

```python
    json.dump({"questions": [{"id": "q1", "firm_id": "f1", "program_id": None,
                              "track": "DS", "title": "T", "url": "https://x.com/j",
                              "reason": "no-quotable-line", "first_seen": "2026-08-13",
                              "last_seen": "2026-08-13", "resolved": False}]},
              open(os.path.join(d, "state", "open-questions.json"), "w"))
```

Then append this test before the final `sys.exit`:

```python
# 4. Open questions must reach the page, or they live only in an ephemeral digest.
d = make_repo("\n")
build(d)
page = read(d)
ok &= test("open questions inlined into DATA", '"questions"' in page and "no-quotable-line" in page)
shutil.rmtree(d)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python tests/test_build_dashboard.py`

Expected: FAIL on `open questions inlined into DATA` — the builder does not read that file yet. Tests 1–3 must still PASS.

- [ ] **Step 3: Add open questions to the blob**

In `scripts/build_dashboard.py`, inside the `data = {...}` literal, add one entry after the `"sync"` line:

```python
        "questions": load(root, "state/open-questions.json")["questions"],
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python tests/test_build_dashboard.py`

Expected: all 4 tests PASS.

- [ ] **Step 5: Add the track vocabulary to the page**

In `dashboard.html`, at line 217 beside the existing `const TIER = ...` line, add:

```javascript
const TRACK = {IB:"Banking",CF:"Corporate finance",DS:"Data science"};
```

At line 174, immediately after the existing tier `<select>` closing tag, add a track filter:

```html
<select id="fTrack" aria-label="Filter by track"><option value="">All tracks</option>
  <option value="IB">Banking</option><option value="CF">Corporate finance</option><option value="DS">Data science</option></select>
```

- [ ] **Step 6: Render track in the table**

**Scope warning:** the tag cell lives inside `progs.map(p=>{ const f=firms[p.firm_id]||{}; ... })`, where the locals are bare `p` and `f`. The `r.p` / `r.f` form used further down in `render()` is a *different* scope and will throw here. Use bare names in this step.

Replace the tier cell (the `<td><span class="tag">${TIER[f.tier]||""}</span></td>` line):

```javascript
    <td><span class="tag">${p.track==="IB"?(TIER[f.tier]||""):(TRACK[p.track]||"")}</span></td>
```

Replace the Type cell on the next line. It currently hardcodes two types, so every seeded `internship` row would mislabel as "Insight":

```javascript
    <td>${p.type==="SA"?("SA "+p.target_summer):p.type==="insight"?"Insight":"Internship"}</td>
```

- [ ] **Step 7: Wire the track filter**

Three edits, all required — omitting any one leaves `fTrack` undefined and the `render()` call throws, blanking the whole table.

Add the element lookup to the existing declaration block:

```javascript
const q=document.getElementById("q"),fTier=document.getElementById("fTier"),
      fTrack=document.getElementById("fTrack"),
      fType=document.getElementById("fType"),fStatus=document.getElementById("fStatus");
```

Add the predicate inside `render()`'s `rows.filter(...)`, immediately after the `fTier` line:

```javascript
    (!fTrack.value||r.p.track===fTrack.value)&&
```

Add it to the listener array on the last line of that block:

```javascript
[q,fTier,fTrack,fType,fStatus].forEach(el=>el.addEventListener("input",render));
```

- [ ] **Step 8: Swap the tier rollup for a track rollup**

Immediately after the existing `const tierN = ...` line, add:

```javascript
const trackN = DATA.programs.reduce((a,p)=>(a[p.track]=(a[p.track]||0)+1,a),{});
```

Then replace the rollup's `d:` value (the line reading ``d:["BB","EB","MM"].filter(t=>tierN[t])...``):

```javascript
   d:["IB","CF","DS"].filter(t=>trackN[t]).map(t=>trackN[t]+" "+t).join(" · ")},
```

- [ ] **Step 9: Add the open-questions section**

In `dashboard.html`, immediately before the `<h2>BU campus events</h2>` line, add:

```html
  <h2>Needs attention <span class="count" id="qCount"></span></h2>
  <div id="questions"></div>
```

Then add the renderer beside the other render functions:

```javascript
const openQs=(DATA.questions||[]).filter(q=>!q.resolved);
document.getElementById("qCount").textContent=openQs.length?openQs.length:"";
document.getElementById("questions").innerHTML = openQs.length
  ? openQs.map(q=>`<div class="card"><span class="tag">${TRACK[q.track]||q.track}</span>
      <strong>${q.title||q.program_id||q.firm_id}</strong> — ${q.reason}
      ${q.url?`<a href="${q.url}" target="_blank" rel="noopener">open posting</a>`:""}
      <em>first seen ${q.first_seen}</em></div>`).join("")
  : `<p>Nothing unresolved.</p>`;
```

- [ ] **Step 10: Rebuild and eyeball the page**

Run: `python scripts/build_dashboard.py && python scripts/validate.py`

Then open `dashboard.html` in a browser and confirm all five:
1. The table renders at all — a blank table means `fTrack` was missed in one of Step 7's three edits. Check the browser console for a ReferenceError.
2. The track filter narrows the table.
3. CF/DS rows show a track label rather than an empty tag; IB rows still show BB/EB/MM.
4. CF/DS rows show "Internship" in the Type column, not "Insight".
5. The "Needs attention" section reads "Nothing unresolved." while `open-questions.json` is empty.

The dashboard has no automated rendering test — this visual check is the gate. Do not skip it.

- [ ] **Step 11: Commit**

```bash
git add scripts/build_dashboard.py tests/test_build_dashboard.py dashboard.html
git commit -m "feat: show tracks and open questions on the dashboard"
```

---

### Task 5: Widen the routine prompt

**Files:**
- Modify: routine `trig_01XsSKnLsxa26JZhVBfybwjt` via the `RemoteTrigger` tool (no repo file)

**Interfaces:**
- Consumes: the widened `ROUTINE.md` from Task 3.
- Produces: nothing downstream.

The routine's own prompt still calls this repo an investment-banking tracker for "a Boston University sophomore". Left alone, it primes the cloud agent against the CF/DS work.

- [ ] **Step 1: Read the current prompt**

Load the tool, then fetch the routine:

```
ToolSearch: select:RemoteTrigger
RemoteTrigger: {action: "get", trigger_id: "trig_01XsSKnLsxa26JZhVBfybwjt"}
```

Copy `job_config.ccr.events[0].data.message.content` verbatim before editing.

- [ ] **Step 2: Update only the framing sentence**

Send a partial update whose `job_config` is the object you just read, with **only** the first sentence of the prompt changed from:

> You are the BankTracker daily monitoring agent. This repo tracks investment-banking recruiting timelines (insight programs + Summer Analyst applications) for a Boston University sophomore, and keeps their Google Calendar in sync...

to:

> You are the BankTracker monitoring agent. This repo tracks recruiting timelines across three tracks — investment banking, corporate finance, and data science — for a Boston University student in the class of 2029 who is a dual major in finance and data science, and keeps their Google Calendar in sync...

Leave `model`, `cron_expression`, `allowed_tools`, `sources`, and `mcp_connections` untouched. Changing the model is out of scope: the routine reads eligibility lines and judges applicability, and a weaker model's confident misread passes the validator's gate and puts a false alert on the calendar.

- [ ] **Step 3: Verify the update took**

```
RemoteTrigger: {action: "get", trigger_id: "trig_01XsSKnLsxa26JZhVBfybwjt"}
```

Confirm the prompt shows the new first sentence, `model` is still `claude-sonnet-5`, and `cron_expression` is still `0 12 * * 1,3,5`.

- [ ] **Step 4: Push everything**

```bash
git push origin main
```

If the push is rejected, the routine has pushed runs since you started: `git fetch origin && git rebase origin/main`. Resolve any `dashboard.html` conflict by taking the remote copy (`git checkout --ours dashboard.html`), then re-run `python scripts/build_dashboard.py` after the rebase so the page is rebuilt from merged data.

---

## Verification

After all five tasks:

```bash
python tests/test_validate.py          # every line PASS, exit 0
python tests/test_build_dashboard.py   # every line PASS, exit 0
python scripts/validate.py             # OK: <N> firms, <M> programs, ...
python scripts/build_dashboard.py      # dashboard.html rebuilt: ...
git status --porcelain                 # empty
```

The first live proof is the next scheduled run (Mon/Wed/Fri 8am ET). Its digest should carry `[IB]`/`[CF]`/`[DS]` tags and a footer whose `<C>` count matches the number of CF/DS programs at `every_run` firms.
