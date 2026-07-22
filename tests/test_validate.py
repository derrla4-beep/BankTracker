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
