import json, subprocess, sys, tempfile, os, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run_validator(root):
    return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "validate.py"), "--root", root],
                          capture_output=True, text=True)

def make_fixture(firms, programs, events, sync, questions=None):
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "data")); os.makedirs(os.path.join(d, "state"))
    json.dump({"firms": firms}, open(os.path.join(d, "data", "firms.json"), "w"))
    json.dump({"profile": PROFILE, "programs": programs},
              open(os.path.join(d, "data", "programs.json"), "w"))
    json.dump({"events": events}, open(os.path.join(d, "data", "bu-events.json"), "w"))
    json.dump(sync, open(os.path.join(d, "state", "calendar-sync.json"), "w"))
    json.dump({"questions": questions or []},
              open(os.path.join(d, "state", "open-questions.json"), "w"))
    return d

PROFILE = {"grad_year": 2029, "school": "Boston University", "notes": ""}
GOOD_FIRM = {"id": "goldman-sachs", "name": "Goldman Sachs", "tracks": ["IB"], "tier": "BB",
             "sweep_cadence": None, "careers_url": "https://x.com",
             "insight_programs_url": None, "notes": ""}
GOOD_PROG = {"id": "goldman-sachs-2028-sa-ib", "firm_id": "goldman-sachs",
             "name": "2028 SA IB", "track": "IB", "type": "SA", "target_summer": 2028,
             "eligibility": {"grad_years": [2029], "verified": False, "source": None, "quote": None},
             "historical_opens": {"2027": "2026-03-02"}, "predicted_open": "2027-03-01",
             "confidence": "medium", "status": "predicted", "application_url": None,
             "sources": ["https://x.com"], "sightings": [], "last_checked": None, "notes": ""}
# An eligibility block that has actually been read off a live posting.
VERIFIED_ELIG = {"grad_years": [2029], "verified": True,
                 "source": "https://x.com/apply", "quote": "Open to candidates graduating in 2029."}

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

# --- open questions (never-silently-drop) ---
# A live posting the run could not classify must be recorded here rather than
# vanishing: it is neither promotable to "open" nor a wrong-cycle sighting.
GOOD_QUESTION = {"id": "goldman-sachs-2028-sa-ib-2026-08-13",
                 "firm_id": "goldman-sachs", "program_id": "goldman-sachs-2028-sa-ib",
                 "track": "IB", "title": "2028 Summer Analyst",
                 "url": "https://x.com/2028-sa", "reason": "no-quotable-line",
                 "first_seen": "2026-08-13", "last_seen": "2026-08-13", "resolved": False}

# 20. A well-formed open question is valid
d = make_fixture([GOOD_FIRM], [GOOD_PROG], [], {"programs": {}, "bu_events": {}}, [GOOD_QUESTION])
ok &= test("open question accepted", run_validator(d).returncode == 0); shutil.rmtree(d)
# 21. state/open-questions.json is required, like the other state files
d = make_fixture([GOOD_FIRM], [GOOD_PROG], [], {"programs": {}, "bu_events": {}})
os.remove(os.path.join(d, "state", "open-questions.json"))
ok &= test("missing open-questions.json rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 22. Question pointing at an unknown firm fails
bad = dict(GOOD_QUESTION, firm_id="nonexistent")
d = make_fixture([GOOD_FIRM], [GOOD_PROG], [], {"programs": {}, "bu_events": {}}, [bad])
ok &= test("open question unknown firm_id rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 23. Question pointing at an unknown program fails
bad = dict(GOOD_QUESTION, program_id="nonexistent")
d = make_fixture([GOOD_FIRM], [GOOD_PROG], [], {"programs": {}, "bu_events": {}}, [bad])
ok &= test("open question unknown program_id rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 24. program_id null is allowed: the sweep can find a live posting at a firm
#     that has no program row yet (the Capital One case).
nullprog = dict(GOOD_QUESTION, program_id=None)
d = make_fixture([GOOD_FIRM], [GOOD_PROG], [], {"programs": {}, "bu_events": {}}, [nullprog])
ok &= test("open question null program_id accepted", run_validator(d).returncode == 0); shutil.rmtree(d)
# 25. Duplicate question ids fail
d = make_fixture([GOOD_FIRM], [GOOD_PROG], [], {"programs": {}, "bu_events": {}},
                 [GOOD_QUESTION, dict(GOOD_QUESTION)])
ok &= test("duplicate open question ids rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 26. Bad date fails
bad = dict(GOOD_QUESTION, first_seen="08/13/2026")
d = make_fixture([GOOD_FIRM], [GOOD_PROG], [], {"programs": {}, "bu_events": {}}, [bad])
ok &= test("open question bad first_seen rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 27. Unknown reason fails
bad = dict(GOOD_QUESTION, reason="just-because")
d = make_fixture([GOOD_FIRM], [GOOD_PROG], [], {"programs": {}, "bu_events": {}}, [bad])
ok &= test("open question bad reason rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 28. A posting-backed reason must carry the url the user is meant to click
bad = dict(GOOD_QUESTION, url=None)
d = make_fixture([GOOD_FIRM], [GOOD_PROG], [], {"programs": {}, "bu_events": {}}, [bad])
ok &= test("open question missing url rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 29. prediction-overdue has no posting behind it, so null url/title is correct
overdue = dict(GOOD_QUESTION, reason="prediction-overdue", url=None, title=None)
d = make_fixture([GOOD_FIRM], [GOOD_PROG], [], {"programs": {}, "bu_events": {}}, [overdue])
ok &= test("prediction-overdue with null url accepted", run_validator(d).returncode == 0); shutil.rmtree(d)
# 30. resolved must be a boolean
bad = dict(GOOD_QUESTION, resolved="no")
d = make_fixture([GOOD_FIRM], [GOOD_PROG], [], {"programs": {}, "bu_events": {}}, [bad])
ok &= test("open question non-boolean resolved rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 31. Bad track fails
bad = dict(GOOD_QUESTION, track="BANKING")
d = make_fixture([GOOD_FIRM], [GOOD_PROG], [], {"programs": {}, "bu_events": {}}, [bad])
ok &= test("open question bad track rejected", run_validator(d).returncode == 1); shutil.rmtree(d)
# 32. Wrong container type fails cleanly (not a crash)
d = make_fixture([GOOD_FIRM], [GOOD_PROG], [], {"programs": {}, "bu_events": {}})
json.dump({"questions": {}}, open(os.path.join(d, "state", "open-questions.json"), "w"))
ok &= test("wrong questions container type rejected", run_validator(d).returncode == 1); shutil.rmtree(d)

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

sys.exit(0 if ok else 1)
