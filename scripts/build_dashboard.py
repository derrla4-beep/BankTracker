"""Rebuild the inlined data blob in dashboard.html from the JSON state files.

dashboard.html is a single self-contained page: it carries its data inline so it
opens straight off disk or GitHub with no server. Everything except the one
`const DATA = {...};` line is hand-maintained markup, so this script rewrites
only that line and leaves the rest of the file untouched.

Run it after every routine update, before committing.
"""
import argparse, json, os, re, sys
from datetime import date

# The file is read with newline="" to preserve its line endings on write, so on a
# Windows checkout (core.autocrlf=true) the line ends ";\r\n". The trailing \r is
# matched by a lookahead rather than consumed: consuming it would drop it from the
# replacement and leave that one line bare-LF in an otherwise CRLF file.
ANCHOR = re.compile(r"(?m)^const DATA = .*;[ \t]*(?=\r?$)")

def load(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as f:
        return json.load(f)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--date", default=date.today().isoformat(),
                    help="value for DATA.generated (default: today)")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the file is out of date instead of writing it")
    args = ap.parse_args()
    root = args.root

    progs_doc = load(root, "data/programs.json")
    data = {
        "generated": args.date,
        "profile": progs_doc.get("profile", {}),
        "firms": load(root, "data/firms.json")["firms"],
        "programs": progs_doc["programs"],
        "events": load(root, "data/bu-events.json")["events"],
        "sync": load(root, "state/calendar-sync.json"),
    }

    path = os.path.join(root, "dashboard.html")
    with open(path, encoding="utf-8", newline="") as f:
        html = f.read()

    if len(ANCHOR.findall(html)) != 1:
        print("dashboard.html: expected exactly one 'const DATA = ...;' line", file=sys.stderr)
        sys.exit(1)

    blob = "const DATA = " + json.dumps(data, ensure_ascii=False, sort_keys=False) + ";"
    # json.dumps can emit "</script>" inside a string and close the tag early.
    blob = blob.replace("</", "<\\/")
    updated = ANCHOR.sub(lambda _: blob, html, count=1)

    if args.check:
        if updated != html:
            print("dashboard.html is stale — run scripts/build_dashboard.py", file=sys.stderr)
            sys.exit(1)
        print("dashboard.html up to date")
        sys.exit(0)

    if updated == html:
        print("dashboard.html already current")
        sys.exit(0)

    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(updated)
    print(f"dashboard.html rebuilt: {len(data['firms'])} firms, "
          f"{len(data['programs'])} programs, {len(data['events'])} events, generated {args.date}")

if __name__ == "__main__":
    main()
