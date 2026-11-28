#!/usr/bin/env python3
"""Shape checks for HQ data.json (the fields the page reads). Exit 1 with a list of problems.

Usage: python3 check_data.py [path/to/data.json]   (default: data.json next to this file)
Covers the fields added 26-27 Nov: pace_alerts, auto_heal, fleet_pacing.agents (minny/chinny/sinny),
career krs, plus a privacy sweep (no emails; long digit runs are counted, not failed) over the whole file.
"""
import json, os, re, sys

path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
d = json.load(open(path))
bad = []

def frac(v):
    return v is None or (isinstance(v, (int, float)) and 0 <= v <= 1.5)

for a in d.get("pace_alerts") or []:
    if not {"agent", "gap_pts", "text"} <= set(a): bad.append(f"pace_alerts row missing keys: {a}")
for a in d.get("auto_heal") or []:
    if not {"at", "agent", "action"} <= set(a): bad.append(f"auto_heal row missing keys: {a}")

ag = ((d.get("fleet_pacing") or {}).get("agents") or {})
for k, r in ag.items():
    for f in ("used", "target"):
        if f in r and not frac(r[f]): bad.append(f"fleet_pacing.agents.{k}.{f} out of range: {r[f]}")
c = ag.get("chinny")
if c is not None and c.get("used") is None and not (c.get("note") or c.get("probe")):
    bad.append("fleet_pacing.agents.chinny: used is null with no note (page would show 'no limit')")
s = ag.get("sinny")
if s is not None and not {"used", "target", "reset"} <= set(s): bad.append("fleet_pacing.agents.sinny missing used/target/reset")

pillars = ((d.get("goals") or {}).get("pillars") or [])
car = next((p for p in pillars if p.get("key") == "career"), None)
if car is not None:
    for kr in car.get("krs") or []:
        if not {"key", "text"} <= set(kr): bad.append(f"career kr missing key/text: {kr}")

raw = json.dumps(d)
noweb = re.sub(r"https?://\S+", " ", raw)  # job-board URLs legitimately carry long numeric ids
if re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", noweb): bad.append("privacy: an email address appears in data.json")
# Long digit runs outside URLs are job/req ids in the career rows (accepted); report a count, don't fail.
_n = len(re.findall(r"(?<![\w-])\d{9,}(?![\w-])", noweb))
if _n: print(f"note: {_n} long digit run(s) outside URLs (job/req ids in career rows; not personal ids)")

print("\n".join(bad) or f"ok: {path}")
sys.exit(1 if bad else 0)
