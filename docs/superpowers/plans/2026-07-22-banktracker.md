# BankTracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a recruiting tracker that predicts when ~45 IB firms open applications (2027 insight programs + 2028 Summer Analyst), alerts via Google Calendar 4 weeks / 1 week / day-of, and runs a daily scheduled cloud agent that catches live postings.

**Architecture:** Plain JSON state files in a private git repo — no server, no database. One-time research seeds `data/firms.json` and `data/programs.json` with historical open dates and predictions; a seeding pass creates the calendar alert chain; a scheduled Claude routine (Sonnet) does windowed daily checks and updates state + calendar.

**Tech Stack:** JSON data files, Python 3 (stdlib only) for validation, Google Calendar MCP tools (`mcp__claude_ai_Google_Calendar__*`), WebSearch/WebFetch for research, Claude Code scheduled routines.

**Model assignment (set via Agent `model` param):** Tasks 2, 3, 4 → `opus` (judgment-heavy research). Tasks 1, 5, 6, 7 → `sonnet` (mechanical).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-22-banktracker-design.md` — read it before starting any task.
- All dates in JSON are ISO `YYYY-MM-DD` strings; times are US Eastern.
- US programs only. No EMEA. No integration with the separate Banking-Outreach folder.
- Never invent a historical date. A program with zero sourced historical dates gets `"confidence": "unverified"` and `"status": "unverified"` — never a fabricated prediction presented as real.
- Every data-changing task ends with `python scripts/validate.py` passing and a git commit.
- Calendar events go on the user's primary Google Calendar, timezone `America/New_York`.
- The Google Calendar MCP tools are deferred: load them with one ToolSearch call, e.g. `select:mcp__claude_ai_Google_Calendar__create_event,mcp__claude_ai_Google_Calendar__list_events,mcp__claude_ai_Google_Calendar__update_event`.

---

### Task 1: Repo scaffolding, schemas, and validation script — `sonnet`

**Files:**
- Create: `README.md`, `.gitignore`, `data/firms.json`, `data/programs.json`, `data/bu-events.json`, `state/calendar-sync.json`, `scripts/validate.py`, `tests/test_validate.py`, `docs/schemas.md`

**Interfaces:**
- Produces: the four JSON state files (empty but schema-valid) and `python scripts/validate.py` (exit 0 = valid, exit 1 + messages = invalid). Every later task runs this validator.

- [ ] **Step 1: Write `docs/schemas.md`** documenting the four schemas exactly as follows (this is the contract for all later tasks):

````markdown
# BankTracker JSON Schemas

## data/firms.json
```json
{
  "firms": [
    {
      "id": "goldman-sachs",
      "name": "Goldman Sachs",
      "tier": "BB",
      "careers_url": "https://www.goldmansachs.com/careers/students",
      "insight_programs_url": "https://...",
      "notes": ""
    }
  ]
}
```
- `id`: kebab-case, unique. `tier`: `"BB"` | `"EB"` | `"MM"`.
- `insight_programs_url` may be `null` if the firm has no insight-program page.

## data/programs.json
```json
{
  "programs": [
    {
      "id": "goldman-sachs-2028-sa-ib",
      "firm_id": "goldman-sachs",
      "name": "2028 Summer Analyst — Investment Banking (NYC)",
      "type": "SA",
      "target_summer": 2028,
      "historical_opens": { "2026": "2025-03-04", "2027": "2026-03-02" },
      "predicted_open": "2027-03-01",
      "confidence": "high",
      "status": "predicted",
      "application_url": null,
      "sources": ["https://..."],
      "last_checked": null,
      "notes": ""
    }
  ]
}
```
- `type`: `"SA"` | `"insight"`. `target_summer`: int (2027 or 2028).
- `historical_opens`: map of cycle-year → the date that cycle's app opened. May be `{}`.
- `confidence`: `"high"` (2+ historical years), `"medium"` (1 year), `"unverified"` (0 years).
- `status`: `"predicted"` | `"open"` | `"closed"` | `"unverified"`.
- `predicted_open` must be `null` when confidence is `"unverified"`; otherwise a date.
- `application_url`: null until status is `"open"`.
- `last_checked`: ISO date of last live check, or null.

## data/bu-events.json
```json
{
  "events": [
    {
      "id": "gs-questrom-info-session-2026-09-15",
      "firm_id": "goldman-sachs",
      "title": "Goldman Sachs Info Session @ Questrom",
      "date": "2026-09-15",
      "time": "18:00",
      "location": "Questrom School of Business",
      "source_url": "https://...",
      "added": "2026-07-22"
    }
  ]
}
```
- `firm_id` may be `null` for multi-firm events (career fairs). `time`/`location` may be `null`.

## state/calendar-sync.json
```json
{
  "programs": {
    "goldman-sachs-2028-sa-ib": {
      "t_minus_4w": "<google event id>",
      "t_minus_1w": "<google event id>",
      "t_day": "<google event id>"
    }
  },
  "bu_events": { "gs-questrom-info-session-2026-09-15": "<google event id>" }
}
```
- Keys are program/event ids from the data files. Missing key = no events created yet.
- Any of the three alert slots may be absent (e.g., T−4w was already in the past at seed time).
````

- [ ] **Step 2: Create the four state files** with empty valid content: `data/firms.json` = `{"firms": []}`, `data/programs.json` = `{"programs": []}`, `data/bu-events.json` = `{"events": []}`, `state/calendar-sync.json` = `{"programs": {}, "bu_events": {}}`.

- [ ] **Step 3: Write the failing test** `tests/test_validate.py` (stdlib only, no pytest):

```python
import json, subprocess, sys, tempfile, os, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run_validator(root):
    return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "validate.py"), "--root", root],
                          capture_output=True, text=True)

def make_fixture(firms, programs, events, sync):
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "data")); os.makedirs(os.path.join(d, "state"))
    json.dump({"firms": firms}, open(os.path.join(d, "data", "firms.json"), "w"))
    json.dump({"programs": programs}, open(os.path.join(d, "data", "programs.json"), "w"))
    json.dump({"events": events}, open(os.path.join(d, "data", "bu-events.json"), "w"))
    json.dump(sync, open(os.path.join(d, "state", "calendar-sync.json"), "w"))
    return d

GOOD_FIRM = {"id": "goldman-sachs", "name": "Goldman Sachs", "tier": "BB",
             "careers_url": "https://x.com", "insight_programs_url": None, "notes": ""}
GOOD_PROG = {"id": "goldman-sachs-2028-sa-ib", "firm_id": "goldman-sachs",
             "name": "2028 SA IB", "type": "SA", "target_summer": 2028,
             "historical_opens": {"2027": "2026-03-02"}, "predicted_open": "2027-03-01",
             "confidence": "medium", "status": "predicted", "application_url": None,
             "sources": ["https://x.com"], "last_checked": None, "notes": ""}

def test(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    return cond

ok = True
# 1. Empty repo state is valid
d = make_fixture([], [], [], {"programs": {}, "bu_events": {}})
ok &= test("empty state valid", run_validator(d).returncode == 0); shutil.rmtree(d)
# 2. Good firm + program is valid
d = make_fixture([GOOD_FIRM], [GOOD_PROG], [], {"programs": {}, "bu_events": {}})
ok &= test("good data valid", run_validator(d).returncode == 0); shutil.rmtree(d)
# 3. Program referencing unknown firm fails
bad = dict(GOOD_PROG, firm_id="nonexistent")
d = make_fixture([GOOD_FIRM], [bad], [], {"programs": {}, "bu_events": {}})
ok &= test("unknown firm_id rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 4. Bad date format fails
bad = dict(GOOD_PROG, predicted_open="03/01/2027")
d = make_fixture([GOOD_FIRM], [bad], [], {"programs": {}, "bu_events": {}})
ok &= test("bad date rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 5. unverified confidence must have null predicted_open
bad = dict(GOOD_PROG, confidence="unverified", status="unverified")
d = make_fixture([GOOD_FIRM], [bad], [], {"programs": {}, "bu_events": {}})
ok &= test("unverified with predicted_open rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 6. Duplicate program ids fail
d = make_fixture([GOOD_FIRM], [GOOD_PROG, dict(GOOD_PROG)], [], {"programs": {}, "bu_events": {}})
ok &= test("duplicate ids rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 7. Bad tier fails
bad_firm = dict(GOOD_FIRM, tier="BOUTIQUE")
d = make_fixture([bad_firm], [], [], {"programs": {}, "bu_events": {}})
ok &= test("bad tier rejected", run_validator(d).returncode == 1); shutil.rmtree(d)

sys.exit(0 if ok else 1)
```

- [ ] **Step 4: Run it to verify it fails**

Run: `python tests/test_validate.py`
Expected: crash or FAIL lines (validate.py doesn't exist yet).

- [ ] **Step 5: Write `scripts/validate.py`**:

```python
"""Validate BankTracker JSON state files. Exit 0 if valid, 1 with messages if not."""
import argparse, json, os, re, sys
from datetime import date

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIERS = {"BB", "EB", "MM"}
CONFIDENCES = {"high", "medium", "unverified"}
STATUSES = {"predicted", "open", "closed", "unverified"}
TYPES = {"SA", "insight"}

def err(errors, msg):
    errors.append(msg)

def check_date(errors, value, label, allow_null=False):
    if value is None:
        if not allow_null:
            err(errors, f"{label}: date required, got null")
        return
    if not (isinstance(value, str) and DATE_RE.match(value)):
        err(errors, f"{label}: bad date {value!r} (want YYYY-MM-DD)")
        return
    try:
        date.fromisoformat(value)
    except ValueError:
        err(errors, f"{label}: invalid calendar date {value!r}")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    root = p.parse_args().root
    errors = []

    def load(rel):
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            err(errors, f"{rel}: cannot load ({e})")
            return None

    firms_doc = load("data/firms.json")
    progs_doc = load("data/programs.json")
    events_doc = load("data/bu-events.json")
    sync_doc = load("state/calendar-sync.json")
    if errors:
        print("\n".join(errors)); sys.exit(1)

    firm_ids = set()
    for f in firms_doc.get("firms", []):
        fid = f.get("id", "<missing id>")
        label = f"firms.json[{fid}]"
        if fid in firm_ids: err(errors, f"{label}: duplicate id")
        firm_ids.add(fid)
        if not re.match(r"^[a-z0-9-]+$", fid): err(errors, f"{label}: id must be kebab-case")
        if f.get("tier") not in TIERS: err(errors, f"{label}: bad tier {f.get('tier')!r}")
        if not f.get("name"): err(errors, f"{label}: name required")
        if not f.get("careers_url"): err(errors, f"{label}: careers_url required")

    prog_ids = set()
    for pr in progs_doc.get("programs", []):
        pid = pr.get("id", "<missing id>")
        label = f"programs.json[{pid}]"
        if pid in prog_ids: err(errors, f"{label}: duplicate id")
        prog_ids.add(pid)
        if pr.get("firm_id") not in firm_ids: err(errors, f"{label}: unknown firm_id {pr.get('firm_id')!r}")
        if pr.get("type") not in TYPES: err(errors, f"{label}: bad type {pr.get('type')!r}")
        if pr.get("target_summer") not in (2027, 2028): err(errors, f"{label}: bad target_summer")
        conf = pr.get("confidence")
        if conf not in CONFIDENCES: err(errors, f"{label}: bad confidence {conf!r}")
        if pr.get("status") not in STATUSES: err(errors, f"{label}: bad status {pr.get('status')!r}")
        for year, d in pr.get("historical_opens", {}).items():
            check_date(errors, d, f"{label}.historical_opens[{year}]")
        if conf == "unverified":
            if pr.get("predicted_open") is not None:
                err(errors, f"{label}: unverified confidence requires predicted_open null")
            if pr.get("status") not in ("unverified", "open", "closed"):
                err(errors, f"{label}: unverified confidence requires unverified status (unless open/closed)")
        else:
            check_date(errors, pr.get("predicted_open"), f"{label}.predicted_open",
                       allow_null=(pr.get("status") in ("open", "closed")))
        if pr.get("status") == "open" and not pr.get("application_url"):
            err(errors, f"{label}: open status requires application_url")
        check_date(errors, pr.get("last_checked"), f"{label}.last_checked", allow_null=True)

    event_ids = set()
    for ev in events_doc.get("events", []):
        eid = ev.get("id", "<missing id>")
        label = f"bu-events.json[{eid}]"
        if eid in event_ids: err(errors, f"{label}: duplicate id")
        event_ids.add(eid)
        if ev.get("firm_id") is not None and ev.get("firm_id") not in firm_ids:
            err(errors, f"{label}: unknown firm_id {ev.get('firm_id')!r}")
        if not ev.get("title"): err(errors, f"{label}: title required")
        check_date(errors, ev.get("date"), f"{label}.date")
        check_date(errors, ev.get("added"), f"{label}.added")

    for pid in sync_doc.get("programs", {}):
        if pid not in prog_ids: err(errors, f"calendar-sync.json: unknown program id {pid!r}")
    for eid in sync_doc.get("bu_events", {}):
        if eid not in event_ids: err(errors, f"calendar-sync.json: unknown bu event id {eid!r}")

    if errors:
        print("\n".join(errors)); sys.exit(1)
    print(f"OK: {len(firm_ids)} firms, {len(prog_ids)} programs, {len(event_ids)} BU events")
    sys.exit(0)

if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python tests/test_validate.py`
Expected: 7 PASS lines, exit 0. Also run `python scripts/validate.py` — expected: `OK: 0 firms, 0 programs, 0 BU events`.

- [ ] **Step 7: Write `README.md`** (what the system is, the three phases from the spec, how to run the validator, pointer to `docs/schemas.md` and the spec) and `.gitignore` (contents: `__pycache__/` and `*.pyc`).

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: scaffolding, JSON schemas, and validator"
```

---

### Task 2: Populate firms.json (~45 firms) — `opus`

**Files:**
- Modify: `data/firms.json`

**Interfaces:**
- Consumes: schema in `docs/schemas.md`, validator `python scripts/validate.py`.
- Produces: `data/firms.json` with ~45 firms whose `id`s Tasks 3–4 reference as `firm_id`.

- [ ] **Step 1: Seed from this list**, then verify/adjust via web research (drop defunct firms, fix names). Tier assignments below are final unless a firm no longer exists:
  - **BB:** Goldman Sachs, Morgan Stanley, J.P. Morgan, Bank of America, Citi, Barclays, Deutsche Bank, UBS, Wells Fargo
  - **EB:** Evercore, Lazard, Centerview Partners, PJT Partners, Moelis & Company, Perella Weinberg Partners, Guggenheim Securities, Qatalyst Partners, LionTree, Allen & Company, Rothschild & Co, Greenhill
  - **MM (incl. in-between banks):** RBC Capital Markets, Jefferies, Houlihan Lokey, William Blair, Baird, Piper Sandler, Raymond James, Harris Williams, Lincoln International, Stifel, Oppenheimer, Truist Securities, BMO Capital Markets, TD Securities, Nomura, Mizuho Americas, MUFG, Macquarie, Cantor Fitzgerald, Solomon Partners, Leerink Partners, PNC (Harris Williams parent — skip if redundant), Santander CIB, HSBC
- [ ] **Step 2: For each firm, find via WebSearch/WebFetch** the US student/early-careers page (`careers_url`) and, where one exists, the insight/early-programs page (`insight_programs_url`, else null). Write all entries to `data/firms.json` per schema.
- [ ] **Step 3: Validate**

Run: `python scripts/validate.py`
Expected: `OK: ~45 firms, 0 programs, 0 BU events` (exact count printed).

- [ ] **Step 4: Commit**

```bash
git add data/firms.json
git commit -m "data: seed ~45 firms (BB/EB/MM) with careers URLs"
```

---

### Task 3: Research Summer 2027 insight/sophomore programs — `opus`

**Files:**
- Modify: `data/programs.json`

**Interfaces:**
- Consumes: `data/firms.json` firm ids; schema in `docs/schemas.md`.
- Produces: `programs.json` entries with `"type": "insight"`, `"target_summer": 2027`. Task 6 creates calendar events from these.

This is the highest-priority research: many of these open **August–October 2026**, weeks from now.

- [ ] **Step 1: For each firm in `firms.json`, research US early-insight / sophomore / diversity programs** that a current sophomore (Class of 2029) can use toward Summer 2027. Examples to look for (verify, don't assume): Goldman Sachs Possibilities Summits / Undergraduate Camp, Morgan Stanley Early Insights & sophomore diversity programs, J.P. Morgan Advancing Black Pathways / Winning Women / sophomore Launching Leaders, Bank of America sophomore programs, Citi Early ID, Barclays sophomore springboard/discovery, Evercore/Lazard/Moelis/PWP diversity & women's programs, Houlihan Lokey/Baird/Blair early access programs. Also search generically: `"<firm>" 2027 sophomore program site:careers page`, WSO threads, firm early-careers pages.
- [ ] **Step 2: For each program found, dig for historical open dates** (when applications opened in the 2025 and 2026 cycles): careers-page announcements, WSO "[program] open" threads with dates, LinkedIn posts, archived pages (web.archive.org of the program page). Record every sourced date in `historical_opens` with the source URL in `sources`. Set `confidence` per schema rule (2+ years = high, 1 = medium, 0 = unverified).
- [ ] **Step 3: Set `predicted_open`**: same month/day-of-week pattern as the most recent historical year, adjusted to 2026 for Summer-2027 programs (e.g., opened 2025-08-12 → predict 2026-08-11, the nearest same-weekday). If confidence is unverified: `predicted_open: null`, `status: "unverified"`, and put the program page URL in `sources` so the weekly sweep can watch it. If a program's 2027-cycle application is **already open** as of the research date: `status: "open"` with `application_url` filled.
- [ ] **Step 4: Validate**

Run: `python scripts/validate.py`
Expected: `OK: ...` with the new program count; fix any errors it prints.

- [ ] **Step 5: Commit**

```bash
git add data/programs.json
git commit -m "data: Summer 2027 insight/sophomore programs with historical opens"
```

---

### Task 4: Research 2028 Summer Analyst application timelines — `opus`

**Files:**
- Modify: `data/programs.json`

**Interfaces:**
- Consumes: `data/firms.json` firm ids; schema in `docs/schemas.md`; existing insight entries (do not touch them).
- Produces: `programs.json` entries with `"type": "SA"`, `"target_summer": 2028` (one IB/NYC entry per firm). Task 6 creates calendar events from these.

- [ ] **Step 1: For each firm, research when its Investment Banking Summer Analyst application opened** for the 2026 and 2027 cycles (i.e., apps posted in 2025 and 2026). Best sources: WSO "2027 SA timeline" megathreads, firm career-page announcements, LinkedIn/Simplify-style posting archives, news articles about accelerated recruiting. Record sourced dates in `historical_opens` + `sources`.
- [ ] **Step 2: Predict the 2028-cycle open date** (posting expected in 2027) using the same-pattern rule from Task 3 Step 3. Same unverified rule: no sourced history → null prediction, `status: "unverified"`. If a firm's 2028 SA app is somehow already open, mark `open` with `application_url`.
- [ ] **Step 3: Validate**

Run: `python scripts/validate.py`
Expected: `OK: ...`, program count now insight + ~45 SA entries.

- [ ] **Step 4: Commit**

```bash
git add data/programs.json
git commit -m "data: 2028 SA timelines with historical opens and predictions"
```

---

### Task 5: Initial BU campus events scan — `sonnet`

**Files:**
- Modify: `data/bu-events.json`

**Interfaces:**
- Consumes: `data/firms.json` firm ids; schema in `docs/schemas.md`.
- Produces: `bu-events.json` entries. Task 6 creates calendar events from these.

- [ ] **Step 1: Search public BU sources for upcoming (fall 2026) in-person finance recruiting events:** BU Center for Career Development public events calendar (bu.edu/careers), Questrom events pages, BU finance/IB club pages (BU Finance & Investment Club, BUWIB), and the campus-events pages of the BB firms in `firms.json`. Handshake is login-walled — skip it, note in README that Handshake coverage is manual.
- [ ] **Step 2: Write found events** per schema (`firm_id` null for multi-firm fairs). Zero events found is an acceptable outcome in July — leave the file empty and say so in the task report.
- [ ] **Step 3: Validate and commit**

Run: `python scripts/validate.py` → `OK: ...`

```bash
git add data/bu-events.json
git commit -m "data: initial BU campus events scan"
```

---

### Task 6: Seed Google Calendar alert chain — `sonnet`

**Files:**
- Modify: `state/calendar-sync.json`

**Interfaces:**
- Consumes: `data/programs.json`, `data/bu-events.json`, `state/calendar-sync.json` schema.
- Produces: calendar events on the user's primary Google Calendar; `calendar-sync.json` fully populated. The daily routine (Task 7) updates these events by ID.

- [ ] **Step 1: Load the Google Calendar MCP tools** in ONE ToolSearch call: `select:mcp__claude_ai_Google_Calendar__list_calendars,mcp__claude_ai_Google_Calendar__create_event,mcp__claude_ai_Google_Calendar__list_events`. Call `list_calendars` once to confirm the primary calendar id.
- [ ] **Step 2: For every program with `status: "predicted"` and a `predicted_open` date T, create up to three all-day events** (timezone America/New_York, with a popup reminder at 9am via the event's default reminders — if the MCP create_event schema lacks reminder options, all-day events alone are acceptable):
  - T−28 days: title `🎯 Start networking: <Firm> — <program name> opens ~<T>`, description listing the program's careers URL and predicted date ± "1-2 week accuracy".
  - T−7 days: title `⏳ 1 week out: <Firm> <program name> — finish outreach`
  - T: title `📋 Expected open: <Firm> <program name>` , description: careers URL, "watch the daily digest".
  - **Edge cases:** skip any alert date already in the past. If T−28 is past but T is future, additionally create a single all-day event **tomorrow** titled `🚨 Networking window open NOW: <Firm> <program name> (opens ~<T>)`. If T itself is past, create no events and add `"notes": "predicted date passed at seed time — daily routine must check immediately"` to the program.
  - For programs already `open`: one all-day event tomorrow titled `🚨 OPEN NOW — apply: <Firm> <program name>` with the application URL in the description.
- [ ] **Step 3: Record every created event id** in `state/calendar-sync.json` under the program id with slot keys `t_minus_4w`, `t_minus_1w`, `t_day` (use `t_day` for the NOW/OPEN single events). Write the file incrementally (after each program) so a failure mid-run doesn't lose ids — this is what makes re-runs idempotent: **skip any program whose id already exists in calendar-sync.json**.
- [ ] **Step 4: Create one all-day event per BU event** in `bu-events.json` (title `🏫 <title>`, date, location in description) and record ids under `bu_events`.
- [ ] **Step 5: Verify:** call `list_events` for a sample week containing a known created event and confirm it appears exactly once. Run `python scripts/validate.py` → OK.
- [ ] **Step 6: Commit**

```bash
git add state/calendar-sync.json data/programs.json
git commit -m "feat: seed calendar alert chain for all predicted programs"
```

---

### Task 7: Daily routine instructions + GitHub + schedule — `sonnet` (schedule step done by main session)

**Files:**
- Create: `ROUTINE.md`

**Interfaces:**
- Consumes: everything above.
- Produces: `ROUTINE.md` — the complete instruction prompt the scheduled cloud agent follows every run.

- [ ] **Step 1: Write `ROUTINE.md`** with exactly this content:

````markdown
# BankTracker Daily Routine

You are the BankTracker monitoring agent. Repo layout: `data/firms.json`, `data/programs.json`, `data/bu-events.json`, `state/calendar-sync.json`; schemas in `docs/schemas.md`. All dates ISO, timezone America/New_York. Today's date = run date.

## Every run (daily ~8am ET)

1. Read `data/programs.json`. Build the **in-window set**: programs where status is `"predicted"` and `predicted_open` is within the next 35 days or in the past, plus all status `"open"` programs whose deadline hasn't clearly passed.
2. For each in-window program, check whether the application is live: fetch the firm's careers/program URL (from `firms.json` / `sources`); if fetch fails or is JS-blocked, WebSearch `"<firm> <program name> application 2027/2028"` and check reputable hits (firm domain, WSO, LinkedIn). Set `last_checked` to today.
3. Quick surprise sweep (once per run, not per firm): WebSearch for `2028 investment banking summer analyst application open` and `2027 sophomore insight program investment banking open`, and scan the current WSO SA-timeline thread. If a NOT-in-window program turns out to be live, treat it like an in-window hit.
4. When a posting is live: set `status: "open"`, fill `application_url`, and update the program's `t_day` calendar event (id in `state/calendar-sync.json`) — retitle to `🚨 LIVE — apply: <Firm> <program name>`, move it to today if its date differs, put the application URL first in the description. If the program has no `t_day` event, create one today and record the id.
5. When a firm's page shows the application closed: set `status: "closed"`.
6. If a `"predicted"` program's date passes with no posting found, leave status `"predicted"` (it stays in-window) and note `"prediction overdue"` in `notes`.
7. Load Google Calendar MCP tools with one ToolSearch call. Never create a duplicate event: always consult `calendar-sync.json` first and update by id.
8. Run `python scripts/validate.py`; fix any errors you introduced. Commit all changes: `git add -A && git commit -m "routine: daily update <date>" && git push`.

## Monday runs only (weekly deep sweep) — do this in addition

- Re-validate stale predictions: for predicted programs 5–10 weeks out not checked in 14+ days, quick-check their pages for announced timelines; adjust `predicted_open` if the firm announced differently, and update the T−4w/T−1w/T calendar events (by id) to match.
- Hunt for newly announced insight programs not in `programs.json` (search per BB/EB firm + generic searches). Add them per schema; new predicted programs get the full T−28/T−7/T event chain (skip past dates; if inside 28 days, create the 🚨 NOW event tomorrow) and calendar-sync entries.
- BU events: check bu.edu/careers public events, Questrom event pages, and BB firms' campus-event pages for new in-person BU-accessible events. Add to `bu-events.json`, create 🏫 calendar events, record ids.

## Digest (your final run summary — the user reads this as their morning email)

Format exactly:

```
🚨 NEWLY OPEN (apply + use your contacts): <firm — program — application link>, or "none"
📅 OPENING SOON (next 14 days): <firm — program — predicted date>, or "none"
🎯 START NETWORKING (4-week window entered today/this week): <firm — program>, or "none"
🏫 BU EVENTS ADDED/UPCOMING (7 days): <event — date>, or "none"
⚠️ NEEDS ATTENTION: overdue predictions, unverified programs seen posted, pages that failed to load, or "none"
```

Keep it under ~25 lines. No preamble.

## Rules

- Never fabricate a date or a posting. Uncertain → ⚠️ NEEDS ATTENTION.
- Never delete calendar events; only create/update via calendar-sync ids.
- Cheap by default: most days only in-window programs get checked.
````

- [ ] **Step 2: Commit**

```bash
git add ROUTINE.md
git commit -m "feat: daily routine instructions"
```

- [ ] **Step 3 (main session, not subagent): Push repo to GitHub.** Check `gh auth status`. If authenticated: `gh repo create BankTracker --private --source . --push`. If not authenticated, ask the user to run `! gh auth login` first. OneDrive path caveat: repo works fine locally; the push just mirrors it.
- [ ] **Step 4 (main session): Create the scheduled routine** by invoking the `schedule` skill: daily 8:00 AM America/New_York, model sonnet, repo BankTracker, prompt = "Follow ROUTINE.md in this repo exactly." Confirm with a listed schedule entry. **Contingency:** if scheduled cloud agents can't access the Google Calendar connector, fall back to: routine updates JSON + digest only, and instruct the user that calendar updates happen when they next open Claude Code locally (offer a `/sync-calendar` local command as follow-up work).
- [ ] **Step 5 (main session): Verification run.** Trigger the routine once (or run its steps manually in-session) and confirm: digest produced in the exact format, no duplicate calendar events (spot-check `list_events` on a seeded week), state committed and pushed.

---

## Self-review notes (done at plan time)

- Spec coverage: firms (T2), insight programs (T3), SA (T4), BU events (T5 + weekly sweep), calendar chain T−4w/T−1w/T (T6), daily windowed monitor + digest + Monday sweep (T7), idempotency via calendar-sync (T1/T6/T7), unverified rule (global constraint + validator), error handling (ROUTINE.md rules + ⚠️ section). No gaps found.
- Type consistency: slot keys `t_minus_4w`/`t_minus_1w`/`t_day` used identically in schema, T6, and ROUTINE.md; status/confidence enums identical in schema and validator.
