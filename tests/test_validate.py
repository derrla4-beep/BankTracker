import json, subprocess, sys, tempfile, os, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run_validator(root):
    return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "validate.py"), "--root", root],
                          capture_output=True, text=True)

def make_fixture(firms, programs, events, sync):
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "data")); os.makedirs(os.path.join(d, "state"))
    json.dump({"firms": firms}, open(os.path.join(d, "data", "firms.json"), "w"))
    json.dump({"profile": PROFILE, "programs": programs},
              open(os.path.join(d, "data", "programs.json"), "w"))
    json.dump({"events": events}, open(os.path.join(d, "data", "bu-events.json"), "w"))
    json.dump(sync, open(os.path.join(d, "state", "calendar-sync.json"), "w"))
    return d

PROFILE = {"grad_year": 2029, "school": "Boston University", "notes": ""}
GOOD_FIRM = {"id": "goldman-sachs", "name": "Goldman Sachs", "tier": "BB",
             "careers_url": "https://x.com", "insight_programs_url": None, "notes": ""}
GOOD_PROG = {"id": "goldman-sachs-2028-sa-ib", "firm_id": "goldman-sachs",
             "name": "2028 SA IB", "type": "SA", "target_summer": 2028,
             "eligibility": {"grad_years": [2029], "verified": False, "source": None, "quote": None},
             "historical_opens": {"2027": "2026-03-02"}, "predicted_open": "2027-03-01",
             "confidence": "medium", "status": "predicted", "application_url": None,
             "sources": ["https://x.com"], "sightings": [], "last_checked": None, "notes": ""}
# An eligibility block that has actually been read off a live posting.
VERIFIED_ELIG = {"grad_years": [2029], "verified": True,
                 "source": "https://x.com/apply", "quote": "Open to candidates graduating in 2029."}

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
# 8. Bad calendar-sync slot key fails
bad_sync = {"programs": {"goldman-sachs-2028-sa-ib": {"t_minus4w": "evt1"}}, "bu_events": {}}
d = make_fixture([GOOD_FIRM], [GOOD_PROG], [], bad_sync)
ok &= test("bad sync slot key rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 9. Valid calendar-sync slot key is valid
good_sync = {"programs": {"goldman-sachs-2028-sa-ib": {"t_day": "evt1"}}, "bu_events": {}}
d = make_fixture([GOOD_FIRM], [GOOD_PROG], [], good_sync)
ok &= test("valid sync slot key accepted", run_validator(d).returncode == 0); shutil.rmtree(d)
# 10. Unverified confidence with verifiably open status is intentionally allowed
open_prog = dict(GOOD_PROG, confidence="unverified", status="open", eligibility=VERIFIED_ELIG,
                  predicted_open=None, application_url="https://x.com/apply")
d = make_fixture([GOOD_FIRM], [open_prog], [], {"programs": {}, "bu_events": {}})
ok &= test("unverified confidence with open status accepted", run_validator(d).returncode == 0); shutil.rmtree(d)
# 11. Wrong container type for bu_events fails cleanly (not a crash)
d = make_fixture([GOOD_FIRM], [GOOD_PROG], [], {"programs": {}, "bu_events": []})
ok &= test("wrong bu_events container type rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 12. Wrong container type for firms fails cleanly (not a crash)
d = tempfile.mkdtemp()
os.makedirs(os.path.join(d, "data")); os.makedirs(os.path.join(d, "state"))
json.dump({"firms": {}}, open(os.path.join(d, "data", "firms.json"), "w"))
json.dump({"programs": []}, open(os.path.join(d, "data", "programs.json"), "w"))
json.dump({"events": []}, open(os.path.join(d, "data", "bu-events.json"), "w"))
json.dump({"programs": {}, "bu_events": {}}, open(os.path.join(d, "state", "calendar-sync.json"), "w"))
ok &= test("wrong firms container type rejected", run_validator(d).returncode == 1); shutil.rmtree(d)

# --- eligibility / cycle gate ---
# 13. Regression for 2026-07-27: a live posting for a cycle we are not eligible for
#     must not be recorded as open, however real the posting is.
wrong_cycle = dict(GOOD_PROG, status="open", application_url="https://x.com/2027-sa",
                   eligibility={"grad_years": [2028], "verified": True,
                                "source": "https://x.com/2027-sa",
                                "quote": "For candidates graduating in 2028."})
d = make_fixture([GOOD_FIRM], [wrong_cycle], [], {"programs": {}, "bu_events": {}})
ok &= test("open status for wrong grad year rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 14. Cannot claim open without having read the posting's own eligibility line
unread = dict(GOOD_PROG, status="open", application_url="https://x.com/apply")
d = make_fixture([GOOD_FIRM], [unread], [], {"programs": {}, "bu_events": {}})
ok &= test("open status with unverified eligibility rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 15. verified=True demands its evidence
noquote = dict(GOOD_PROG, eligibility={"grad_years": [2029], "verified": True,
                                       "source": None, "quote": None})
d = make_fixture([GOOD_FIRM], [noquote], [], {"programs": {}, "bu_events": {}})
ok &= test("verified eligibility without source/quote rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 16. Missing eligibility block fails
noelig = {k: v for k, v in GOOD_PROG.items() if k != "eligibility"}
d = make_fixture([GOOD_FIRM], [noelig], [], {"programs": {}, "bu_events": {}})
ok &= test("missing eligibility rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 17. A well-formed wrong-cycle sighting is fine on a non-open program
sighted = dict(GOOD_PROG, status="unverified", confidence="unverified", predicted_open=None,
               sightings=[{"date": "2026-07-27", "url": "https://x.com/2027-sa",
                           "cycle": "Summer 2027", "grad_years": [2028], "note": "prior cycle"}])
d = make_fixture([GOOD_FIRM], [sighted], [], {"programs": {}, "bu_events": {}})
ok &= test("wrong-cycle sighting accepted", run_validator(d).returncode == 0); shutil.rmtree(d)
# 18. Malformed sighting fails
badsight = dict(GOOD_PROG, sightings=[{"date": "2026-07-27", "url": "https://x.com/2027-sa"}])
d = make_fixture([GOOD_FIRM], [badsight], [], {"programs": {}, "bu_events": {}})
ok &= test("malformed sighting rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 19. Missing profile fails
d = make_fixture([GOOD_FIRM], [GOOD_PROG], [], {"programs": {}, "bu_events": {}})
json.dump({"programs": [GOOD_PROG]}, open(os.path.join(d, "data", "programs.json"), "w"))
ok &= test("missing profile rejected", run_validator(d).returncode == 1); shutil.rmtree(d)

sys.exit(0 if ok else 1)
