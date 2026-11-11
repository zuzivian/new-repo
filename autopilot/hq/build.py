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
# API-equivalent cost by provider -> model. cost_usd comes from the Claude Code CLI, which prices tokens at
# API list rates. Providers without token data (Codex, Pro) come in as "other" rows with a note.
prov = {}
for s in usage.get("sessions", []):
    u = s.get("usage") or {}
    created = dt.datetime.fromisoformat(s["created_at"].replace("Z", "+00:00"))
    if created < week_start or not u.get("cost_usd"):
        continue
    P = prov.setdefault(s.get("provider") or "anthropic", {})
    m = P.setdefault(s.get("model") or "unknown", {"usd": 0.0, "sessions": 0, "tokens": 0})
    m["usd"] += float(u["cost_usd"]); m["sessions"] += 1
    m["tokens"] += sum(int(u.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"))
cost = {"providers": sorted(({"provider": k, "usd": round(sum(m["usd"] for m in v.values()), 2),
          "models": sorted(({"model": mk, "usd": round(mv["usd"], 2), "sessions": mv["sessions"], "tokens": mv["tokens"]}
                            for mk, mv in v.items()), key=lambda r: -r["usd"])} for k, v in prov.items()),
                        key=lambda r: -r["usd"]),
        "other": usage.get("other", [])}
cost["total"] = round(sum(p["usd"] for p in cost["providers"]), 2)

spend_rows = sorted(
    ({"project": k, "usd": round(v, 2), "tier": tier_of.get(k, "maintenance")} for k, v in spend.items()),
    key=lambda r: -r["usd"])

# Project board: one tile per repo with a status derived from workers, needs and config.
def _repo_of(name):
    return {"temasek-1360-server": "temasek-1360"}.get(name, name)
board = {}
for pcfg in cfg["projects"]:
    r = _repo_of(pcfg["name"])
    b = board.setdefault(r, {"project": r, "tier": pcfg.get("tier", "maintenance"), "enabled": False,
                             "running": 0, "queued": 0, "codex": 0, "done": 0, "needs": 0, "paused": False})
    b["enabled"] = b["enabled"] or bool(pcfg.get("enabled", True))
for w in state.get("workers", []):
    r = _repo_of(w.get("project", ""))
    b = board.setdefault(r, {"project": r, "tier": "maintenance", "enabled": True, "running": 0, "queued": 0,
                             "codex": 0, "done": 0, "needs": 0, "paused": False})
    st = (w.get("status") or "").lower()
    if "codex" in st: b["codex"] += 1
    elif st.startswith("queued"): b["queued"] += 1
    elif st in ("working", "running", "in progress"): b["running"] += 1
    elif st.startswith("done") or st == "archived": b["done"] += 1
    elif "paused" in st: b["paused"] = True
for n in state.get("needs", []):
    # Prefer an explicit project field; fall back to the repo named in the URL (github.com/<owner>/<repo>), then the title.
    import re as _re
    proj = n.get("project")
    if not proj:
        m = _re.search(r"github\.com/[^/]+/([^/#?]+)", n.get("url", ""))
        proj = m.group(1) if m else None
        if proj == "new-repo" and n.get("title", "").startswith("HQ"): proj = "HQ"
    if proj and _repo_of(proj) in board:
        board[_repo_of(proj)]["needs"] += 1; continue
    t = n.get("title", "").lower()
    for r, b in board.items():
        if r.lower() in t:
            b["needs"] += 1; break
for b in board.values():
    if not b["enabled"]: b["status"] = "off"
    elif b["needs"]: b["status"] = "needs you"
    elif b["paused"]: b["status"] = "paused"
    elif b["running"]: b["status"] = "running"
    elif b["queued"] or b["codex"]: b["status"] = "queued"
    else: b["status"] = "idle"
ORDER = {"needs you": 0, "running": 1, "queued": 2, "paused": 3, "idle": 4, "off": 5}
projects_board = sorted(board.values(), key=lambda b: (ORDER[b["status"]], b["project"]))

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
    # Live rows first; keep only the 6 most recent finished rows so the list doesn't grow forever.
    "workers": [w for w in state.get("workers", []) if not str(w.get("status","")).startswith("done")]
               + [w for w in state.get("workers", []) if str(w.get("status","")).startswith("done")][:6],
    "spend": spend_rows,
    "meetings": meetings,
    "pro": state.get("pro", {"note": "Not connected yet."}),
    "supervisor": state.get("supervisor"),
    "cost": cost,
    "board": projects_board,
    "agents": state.get("agents", []),
    "issues": sorted(state.get("issues", []), key=lambda i: ({"critical": 0, "high": 1, "medium": 2, "low": 3}.get(i.get("severity"), 4), i.get("since", ""))),
}
with open(os.path.join(HERE, "data.json"), "w") as fh:
    json.dump(out, fh, indent=1)
print(f"data.json: {len(spend_rows)} projects, {len(meetings)} meetings, {len(out['needs'])} needs")
