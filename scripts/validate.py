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
