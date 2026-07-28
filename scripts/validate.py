"""Validate BankTracker JSON state files. Exit 0 if valid, 1 with messages if not."""
import argparse, json, os, re, sys
from datetime import date

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIERS = {"BB", "EB", "MM"}
CONFIDENCES = {"high", "medium", "unverified"}
STATUSES = {"predicted", "open", "closed", "unverified"}
TYPES = {"SA", "insight"}
SLOT_KEYS = {"t_minus_4w", "t_minus_1w", "t_day"}

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
    firms_list = firms_doc.get("firms", [])
    if not isinstance(firms_list, list):
        err(errors, 'firms.json: "firms" must be a list')
        firms_list = []
    for f in firms_list:
        fid = f.get("id", "<missing id>")
        label = f"firms.json[{fid}]"
        if fid in firm_ids: err(errors, f"{label}: duplicate id")
        firm_ids.add(fid)
        if not re.match(r"^[a-z0-9-]+$", fid): err(errors, f"{label}: id must be kebab-case")
        if f.get("tier") not in TIERS: err(errors, f"{label}: bad tier {f.get('tier')!r}")
        if not f.get("name"): err(errors, f"{label}: name required")
        if not f.get("careers_url"): err(errors, f"{label}: careers_url required")

    profile = progs_doc.get("profile")
    my_grad_year = None
    if not isinstance(profile, dict):
        err(errors, 'programs.json: "profile" must be an object with a grad_year')
    else:
        my_grad_year = profile.get("grad_year")
        if not isinstance(my_grad_year, int):
            err(errors, "programs.json.profile: grad_year must be an int")
            my_grad_year = None

    prog_ids = set()
    progs_list = progs_doc.get("programs", [])
    if not isinstance(progs_list, list):
        err(errors, 'programs.json: "programs" must be a list')
        progs_list = []
    for pr in progs_list:
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

        elig = pr.get("eligibility")
        if not isinstance(elig, dict):
            err(errors, f"{label}: eligibility object required")
        else:
            years = elig.get("grad_years")
            if not (isinstance(years, list) and years and all(isinstance(y, int) for y in years)):
                err(errors, f"{label}.eligibility: grad_years must be a non-empty list of ints")
                years = []
            if not isinstance(elig.get("verified"), bool):
                err(errors, f"{label}.eligibility: verified must be true or false")
            if elig.get("verified") and not (elig.get("source") and elig.get("quote")):
                err(errors, f"{label}.eligibility: verified requires both source and quote")
            # The cycle gate: never fire an alert for a program we are not eligible for,
            # and never claim open without having read the posting's own eligibility text.
            if pr.get("status") == "open":
                if my_grad_year is not None and my_grad_year not in years:
                    err(errors, f"{label}: status open but eligibility.grad_years {years} "
                                f"excludes profile grad_year {my_grad_year} — record it under sightings instead")
                if not elig.get("verified"):
                    err(errors, f"{label}: status open requires eligibility.verified true "
                                f"(read the posting's class-year line before promoting)")

        sightings = pr.get("sightings")
        if not isinstance(sightings, list):
            err(errors, f"{label}: sightings must be a list")
        else:
            for i, s in enumerate(sightings):
                slabel = f"{label}.sightings[{i}]"
                if not isinstance(s, dict):
                    err(errors, f"{slabel}: must be an object")
                    continue
                check_date(errors, s.get("date"), f"{slabel}.date")
                if not s.get("url"): err(errors, f"{slabel}: url required")
                if not s.get("cycle"): err(errors, f"{slabel}: cycle required")
                sy = s.get("grad_years")
                if not (isinstance(sy, list) and sy and all(isinstance(y, int) for y in sy)):
                    err(errors, f"{slabel}: grad_years must be a non-empty list of ints")

    event_ids = set()
    events_list = events_doc.get("events", [])
    if not isinstance(events_list, list):
        err(errors, 'bu-events.json: "events" must be a list')
        events_list = []
    for ev in events_list:
        eid = ev.get("id", "<missing id>")
        label = f"bu-events.json[{eid}]"
        if eid in event_ids: err(errors, f"{label}: duplicate id")
        event_ids.add(eid)
        if ev.get("firm_id") is not None and ev.get("firm_id") not in firm_ids:
            err(errors, f"{label}: unknown firm_id {ev.get('firm_id')!r}")
        if not ev.get("title"): err(errors, f"{label}: title required")
        check_date(errors, ev.get("date"), f"{label}.date")
        check_date(errors, ev.get("added"), f"{label}.added")

    sync_programs = sync_doc.get("programs", {})
    if not isinstance(sync_programs, dict):
        err(errors, 'calendar-sync.json: "programs" must be a dict')
        sync_programs = {}
    for pid, slots in sync_programs.items():
        if pid not in prog_ids: err(errors, f"calendar-sync.json: unknown program id {pid!r}")
        if not isinstance(slots, dict):
            err(errors, f"calendar-sync.json.programs[{pid}]: value must be a dict of slot keys")
            continue
        for slot_key, evid in slots.items():
            if slot_key not in SLOT_KEYS:
                err(errors, f"calendar-sync.json.programs[{pid}]: unknown slot key {slot_key!r}")
            if not (isinstance(evid, str) and evid):
                err(errors, f"calendar-sync.json.programs[{pid}].{slot_key}: value must be a non-empty string")
    sync_bu_events = sync_doc.get("bu_events", {})
    if not isinstance(sync_bu_events, dict):
        err(errors, 'calendar-sync.json: "bu_events" must be a dict')
        sync_bu_events = {}
    for eid, evid in sync_bu_events.items():
        if eid not in event_ids: err(errors, f"calendar-sync.json: unknown bu event id {eid!r}")
        if not (isinstance(evid, str) and evid):
            err(errors, f"calendar-sync.json.bu_events[{eid}]: value must be a non-empty string")

    if errors:
        print("\n".join(errors)); sys.exit(1)
    print(f"OK: {len(firm_ids)} firms, {len(prog_ids)} programs, {len(event_ids)} BU events")
    sys.exit(0)

if __name__ == "__main__":
    main()
