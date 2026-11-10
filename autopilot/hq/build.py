#!/usr/bin/env python3
"""Assemble autopilot/hq/data.json for the Autopilot HQ artifact.

Inputs (all optional except state.json):
  state.json    supervisor-written: week timeline, u5, needs, workers, pro note
  usage.json    session usage export (sessions[].usage.cost_usd, repo, created_at)
  primers.json  meeting primers (crm-brief-me output)
  ../config.json  pacing + allocation + project tiers
Usage: python3 autopilot/hq/build.py <scratch_dir>
"""
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
scratch = sys.argv[1]


def load(path, default=None):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


cfg = load(os.path.join(HERE, "..", "config.json"))
state = load(os.path.join(scratch, "state.json"))
usage = load(os.path.join(scratch, "usage.json"), {})
primers = load(os.path.join(scratch, "primers.json"), {"primers": []})

reset = dt.datetime.fromisoformat(state["week"]["reset"])
week_start = reset - dt.timedelta(days=7)
tier_of = {p["name"]: p.get("tier", "maintenance") for p in cfg["projects"]}
tier_of.update({"temasek-1360": "growth", "new-repo": "maintenance"})

spend = {}
for s in usage.get("sessions", []):
    u = s.get("usage") or {}
    created = dt.datetime.fromisoformat(s["created_at"].replace("Z", "+00:00"))
    if created < week_start or not u.get("cost_usd"):
        continue
    repo = s.get("repo") or "none"
    spend[repo] = spend.get(repo, 0.0) + float(u["cost_usd"])
spend_rows = sorted(
    ({"project": k, "usd": round(v, 2), "tier": tier_of.get(k, "maintenance")} for k, v in spend.items()),
    key=lambda r: -r["usd"])

now = dt.datetime.now(dt.timezone.utc)
meetings = []
for p in primers.get("primers", []):
    when = dt.datetime.fromisoformat(p["when"])
    if when > now - dt.timedelta(minutes=30):
        meetings.append({**p, "ready": True})
meetings.sort(key=lambda m: m["when"])

out = {
    "updated": now.isoformat(),
    "week": state["week"],
    "pacing": cfg["pacing"],
    "allocation": cfg.get("allocation", {}).get("tiers", {}),
    "needs": state.get("needs", []),
    "workers": state.get("workers", []),
    "spend": spend_rows,
    "meetings": meetings,
    "pro": state.get("pro", {"note": "Not connected yet."}),
}
with open(os.path.join(HERE, "data.json"), "w") as fh:
    json.dump(out, fh, indent=1)
print(f"data.json: {len(spend_rows)} projects, {len(meetings)} meetings, {len(out['needs'])} needs")
