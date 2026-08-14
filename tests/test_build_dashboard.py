"""Tests for scripts/build_dashboard.py. Stdlib only, no pytest."""
import json, subprocess, sys, tempfile, os, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PAGE = ("<html>\n<body>\n<script>\n"
        'const DATA = {"generated": "1999-01-01"};\n'
        "</script>\n</body>\n</html>\n")

def make_repo(newline):
    """A minimal repo whose dashboard.html uses the given line ending."""
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "data")); os.makedirs(os.path.join(d, "state"))
    json.dump({"firms": []}, open(os.path.join(d, "data", "firms.json"), "w"))
    json.dump({"profile": {"grad_year": 2029}, "programs": []},
              open(os.path.join(d, "data", "programs.json"), "w"))
    json.dump({"events": []}, open(os.path.join(d, "data", "bu-events.json"), "w"))
    json.dump({"programs": {}, "bu_events": {}},
              open(os.path.join(d, "state", "calendar-sync.json"), "w"))
    json.dump({"questions": [{"id": "q1", "firm_id": "f1", "program_id": None,
                              "track": "DS", "title": "T", "url": "https://x.com/j",
                              "reason": "no-quotable-line", "first_seen": "2026-08-13",
                              "last_seen": "2026-08-13", "resolved": False}]},
              open(os.path.join(d, "state", "open-questions.json"), "w"))
    with open(os.path.join(d, "dashboard.html"), "w", encoding="utf-8", newline="") as f:
        f.write(PAGE.replace("\n", newline))
    return d

def build(root):
    return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build_dashboard.py"),
                           "--root", root, "--date", "2026-08-13"],
                          capture_output=True, text=True)

def read(root):
    with open(os.path.join(root, "dashboard.html"), encoding="utf-8", newline="") as f:
        return f.read()

def test(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    return cond

ok = True

# 1. LF line endings (how the file is stored in git, and how CI/cloud sees it)
d = make_repo("\n")
r = build(d)
ok &= test("LF dashboard rebuilds", r.returncode == 0)
ok &= test("LF dashboard content updated", '"generated": "2026-08-13"' in read(d))
shutil.rmtree(d)

# 2. CRLF line endings. A Windows checkout with core.autocrlf=true produces these,
#    so the script must not silently fail to find its anchor on the user's machine.
d = make_repo("\r\n")
r = build(d)
ok &= test("CRLF dashboard rebuilds", r.returncode == 0)
ok &= test("CRLF dashboard content updated", '"generated": "2026-08-13"' in read(d))
shutil.rmtree(d)

# 3. Rebuilding must not convert the file's line endings out from under the user.
d = make_repo("\r\n")
build(d)
after = read(d)
ok &= test("CRLF endings preserved on write",
           after.count("\r\n") > 0 and after.count("\n") == after.count("\r\n"))
shutil.rmtree(d)

# 4. Open questions must reach the page, or they live only in an ephemeral digest.
d = make_repo("\n")
build(d)
page = read(d)
ok &= test("open questions inlined into DATA", '"questions"' in page and "no-quotable-line" in page)
shutil.rmtree(d)

sys.exit(0 if ok else 1)
