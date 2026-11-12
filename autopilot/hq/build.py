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
import re
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
tier_of.update({"temasek-1360": "growth", "new-repo": "maintenance", "career": "career-core"})  # career = Nat's #1 goal

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

# Spend by STRATEGY pillar (career / digigov / growth / relationships / fleet_hq) so HQ can compare effort to the split.
PILLAR_OF = {"natwong-dev": "career", "ad-constellation": "career", "skyviu": "career", "jbooks": "career",
             "career": "career", "digitizing-government": "digigov", "digigov": "digigov",
             "relationships": "relationships", "growth": "growth", "exponent": "growth",
             "derby-day": "growth", "temasek-1360": "growth", "ring-studio": "growth",
             "HQ": "fleet_hq", "new-repo": "fleet_hq", "ops-bus": "fleet_hq", "fleet": "fleet_hq"}
spend_rows = sorted(
    ({"project": k, "usd": round(v, 2), "tier": tier_of.get(k, "maintenance"),
      "pillar": PILLAR_OF.get(k, "fleet_hq" if tier_of.get(k, "maintenance") == "maintenance" else "growth")}
     for k, v in spend.items()),
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
    elif not (b["done"] or b["running"] or b["queued"] or b["codex"]): b["status"] = "not attached"  # no session ever touched it
    else: b["status"] = "idle"
ORDER = {"needs you": 0, "running": 1, "queued": 2, "paused": 3, "idle": 4, "not attached": 5, "off": 6}

def _career_filter():
    """Private, owner-maintained filter (ops-bus context/career-filter.json): exclude_companies, exclude_us_person_roles."""
    try: return json.load(open("/home/user/ops-bus/context/career-filter.json"))
    except Exception: return {}

def _md_table(path):
    """Header-driven parse of every '| # | Company | ...' table in Pinny's internship-timelines.md → rows."""
    try:
        text = open(path).read().splitlines()
    except Exception:
        return None
    cells = lambda l: [c.strip().replace("**", "") for c in l.strip().strip("|").split("|")]
    def colkey(h):
        h = h.lower()
        if h == "#": return "n"
        if h.startswith("company"): return "company"
        # Check these before "posted": both headers contain the word (pinny-45 refresh added them, 11-12).
        if h.startswith("on target"): return "on_target"
        if h.startswith("reason"): return "reason"
        if "visa" in h: return "eligibility"
        if "posted" in h: return "posted"
        if "open–close" in h or "open-close" in h or "typical" in h: return "window"
        if "open / check / closed" in h or h == "eligibility": return "elig_class"
        if "visa" in h or "evidence" in h: return "eligibility"
        if "location" in h: return "location"
        if "status" in h: return "status"
        if "source" in h: return "source"
        if "role" in h: return "roles"
        if "fit" in h: return "fit"
        return h[:20]
    rows, keys = [], None
    for l in text:
        if not l.strip().startswith("|"):
            keys = None; continue
        c = cells(l)
        if c and c[0] == "#":
            keys = [colkey(h) for h in c]; continue
        if keys is None or not c or not re.fullmatch(r"N?\d+", c[0].strip()): continue
        r = {k: "" for k in ("company", "roles", "posted", "window", "eligibility", "elig_class", "location", "status", "source", "reason", "on_target")}
        r.update(dict(zip(keys, c)))
        if " (" in r["company"]:
            r["company_note"] = r["company"].split(" (", 1)[1].rstrip(")"); r["company"] = r["company"].split(" (", 1)[0]
        m = re.search(r"\((https?://[^)\s]+)\)", r["posted"]) or re.search(r"(https?://\S+)", r["posted"])
        r["url"] = m.group(1) if m else None
        r["is_posted"] = r["posted"].upper().startswith("Y")
        r["applied"] = bool(re.search(r"applied|interview|rejected|offer|screen", r["status"], re.I))
        e = re.sub(r"\b(no|not|without)\b[^.;]{0,40}?\b(citizenship|clearance|export|itar|u\.?s\.? person)[^.;]*", "", r["eligibility"].lower())
        r["us_person_required"] = None if re.search(r"sentence only|boilerplate", e) else True if re.search(
            r"itar|u\.?s\.? ?(citizen|person|national)|citizenship|clearance|export|permanent resident|green card|lpr", e) else None
        rows.append(r)
    flt = _career_filter()
    for r in rows:
        ec = r["elig_class"].lower()
        excluded = any(k in r["company"].lower() for k in flt.get("exclude_companies", []))
        lean_closed = ec.startswith("lean closed") or "(lean closed)" in ec
        if excluded or ec.startswith("closed") or lean_closed or (not ec and flt.get("exclude_us_person_roles") and r["us_person_required"]):
            r["eligible"] = "no"
        elif ec.startswith("open"):
            r["eligible"] = "yes"
        else:
            r["eligible"] = "check"
    return {"source": "research/career/internship-timelines.md", "rows": rows}

def _gh_issues():
    """Fleet issues mirrored from GitHub: ops-bus issues labelled `fleet` (open + closed in 7 days) and open Chinny
    codex:* issues in the Chinny repos. GitHub is the source of truth; close an issue there and it leaves HQ."""
    import subprocess as sp
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    def api(path):
        r = sp.run(["gh", "api", path], capture_output=True, text=True, timeout=30)
        return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else []
    items, seen = [], set()
    queries = [("ops-bus", f"state=all&labels=fleet&since={since}&per_page=100")]
    queries += [(r, "state=open&per_page=100") for r in ("new-repo", "skyviu", "ad-constellation", "natwong-dev")]
    for repo, q in queries:
        for i in api(f"repos/zuzivian/{repo}/issues?{q}"):
            if "pull_request" in i or i["html_url"] in seen: continue
            L = [l["name"] if isinstance(l, dict) else l for l in i.get("labels", [])]
            codex = next((l for l in L if l.startswith("codex:")), None)
            if "fleet" not in L and not codex: continue
            if codex == "codex:backlog": continue  # the backlog is the pacer's queue, not an issue
            lab = lambda pre: next((l[len(pre):] for l in L if l.startswith(pre)), None)
            seen.add(i["html_url"])
            items.append({"repo": repo, "number": i["number"], "title": i["title"], "url": i["html_url"], "state": i["state"],
                          "severity": lab("sev:") or ("low" if codex else "medium"), "owner": lab("owner:"),
                          "area": lab("area:") or ("chinny" if codex else None), "queue": codex,
                          "since": i["created_at"], "closed": i.get("closed_at")})
    return {"at": dt.datetime.now(dt.timezone.utc).isoformat(), "repos": ["ops-bus", "new-repo", "skyviu", "ad-constellation", "natwong-dev"], "items": items}

OPS = "/home/user/ops-bus"
RUNNER_BY = {"pro": "pinny", "instinct": "binny", "muse": "minny"}

def _requests(sub):
    """Parse requests/<sub>/*.md front-matter + body -> [{file, runner, title, text}] (skips unreadable files)."""
    import glob as _g
    rows = []
    for f in sorted(_g.glob(f"{OPS}/requests/{sub}/*.md")):
        try:
            text = open(f).read()
        except Exception:
            continue
        fm = {}
        m = re.match(r"---\n(.*?)\n---", text, re.S)
        for line in (m.group(1).splitlines() if m else []):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
        rows.append({"file": os.path.basename(f), "runner": fm.get("runner", ""), "title": fm.get("title", ""), "text": text})
    return rows

def _short(title):
    t = re.sub(r"^(\(retry[^)]*\)\s*)?((Binny|Minny|Pinny)(\s*\([^)]*\))?|Research)\s*[-:\u2013]\s*", "", title or "").strip()
    return t if len(t) <= 40 else t[:40].rsplit(" ", 1)[0] + "\u2026"

def _doing_from_requests(agents):
    """(a) Replace generic Pinny/Binny/Minny `doing` text with a summary of their pending requests."""
    try:
        pend = _requests("pending")
        for a in agents:
            runner = next((k for k, v in RUNNER_BY.items() if v == a.get("key")), None)
            if not runner: continue
            mine = [r for r in pend if r["runner"] == runner]
            if not mine: continue
            noun = {"binny": "browser", "minny": "browser", "pinny": "research"}[a["key"]]
            titles = ", ".join(_short(r["title"]) for r in mine[:3] if r["title"])
            a["doing"] = f"{len(mine)} {noun} task{'s' if len(mine) != 1 else ''} in flight: {titles}" + ("\u2026" if len(mine) > 3 and not titles.endswith("\u2026") else "")
    except Exception:
        pass
    return agents

def _truncate(s, n=60):
    s = s or ""
    if len(s) <= n: return s
    cut = s[:n - 1].rsplit(" ", 1)[0].rstrip(" ,;:-\u2013") if " " in s[:n - 1] else s[:n - 1]
    return cut + "\u2026"

def _research_by(rows):
    """(b) Attribute each research row to an agent: requests/done mention first, then commit-subject hint, else sinny."""
    import subprocess as sp
    reqs = _requests("done") + _requests("pending") + _requests("failed")
    for r in rows:
        by = None
        try:
            base = os.path.basename(r["path"])
            for q in reqs:
                if r["path"] in q["text"] or base in q["text"] or (r["title"] and len(r["title"]) > 12 and r["title"].lower() in q["text"].lower()):
                    by = RUNNER_BY.get(q["runner"])
                    if by: break
            if not by:
                s = sp.run(["git", "-C", OPS, "log", "-1", "--format=%s", "--", r["path"]], capture_output=True, text=True, timeout=15).stdout
                if "(muse)" in s: by = "minny"
                elif "(instinct)" in s: by = "binny"
                elif "ops-bus run" in s: by = "pinny"
        except Exception:
            pass
        r["by"] = by or "sinny"
    return rows

def _watchdog():
    """(f) usage/watchdog.json plus fixes_24h = actions with an `at` in the last 24h (or all actions if untimed)."""
    w = load(f"{OPS}/usage/watchdog.json")
    if not isinstance(w, dict): return None
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
    n = 0
    for a in w.get("actions") or []:
        at = a.get("at") if isinstance(a, dict) else None
        try:
            ts = dt.datetime.fromisoformat(str(at).replace("Z", "+00:00"))
            if ts.tzinfo is None: ts = ts.replace(tzinfo=dt.timezone.utc)
            n += ts >= cutoff
        except Exception:
            n += 1  # untimed entry: the file only keeps the latest run, so count it
    # Self-healing also counts fixes Fleet Ops logs as decisions with kind "fix" (watchdog.json keeps only its last run).
    m = 0
    for d in state.get("decisions", []):
        if d.get("kind") != "fix": continue
        try:
            ts = dt.datetime.fromisoformat(str(d.get("at")).replace("Z", "+00:00"))
            m += ts >= cutoff
        except Exception:
            pass
    return {**w, "fixes_24h": n + m, "fixes_watchdog_24h": n, "fixes_fleet_ops_24h": m}

def _nat_actions():
    """(g) Pass through issue/options; default options."""
    rows = []
    for r in state.get("nat_actions", []) or []:
        r = dict(r)
        if not r.get("options"): r["options"] = ["Done", "Snooze 1 day"]
        rows.append(r)
    return rows

def _decisions():
    """(c) decision headline <=60 chars; the detail lives in `why`."""
    rows = sorted(state.get("decisions", []), key=lambda d: d.get("at", ""), reverse=True)[:30]
    return [{**d, "decision": _truncate(d.get("decision"))} for d in rows]

def _research():
    """Research library: every markdown file under ops-bus research/, newest first, with ops-bus blob links."""
    import subprocess as sp, glob as _g
    rows = []
    for f in _g.glob("/home/user/ops-bus/research/**/*.md", recursive=True):
        rel = f.split("/home/user/ops-bus/", 1)[1]
        r = sp.run(["git", "-C", "/home/user/ops-bus", "log", "-1", "--format=%cI|%s", "--", rel], capture_output=True, text=True)
        at, _, msg = (r.stdout.strip() or "|").partition("|")
        title = ""
        try:
            for line in open(f):
                if line.startswith("# "): title = line[2:].strip(); break
        except Exception:
            pass
        area = rel.split("/")[1] if rel.count("/") >= 2 else "other"
        rows.append({"title": title or os.path.basename(f)[:-3], "area": area, "path": rel, "at": at,
                     "url": f"https://github.com/zuzivian/ops-bus/blob/main/{rel}"})
    return _research_by(sorted(rows, key=lambda x: x["at"], reverse=True))

def _goals():
    g = dict(state.get("goals") or {})
    try:
        g["progress"] = json.load(open("/home/user/ops-bus/goals/progress.json"))
    except Exception:
        g["progress"] = None
    # Supervisor-measured values (e.g. calendar coffee-chat count, build slices) merged into progress by pillar.
    # Gmail recruiting scan (Sinny, daily): application confirmations, interviews and rejections since Sep 1.
    try:
        ce = json.load(open("/home/user/ops-bus/goals/career_email.json"))
        if g["progress"] is None: g["progress"] = {}
        car = g["progress"].setdefault("career", {})
        for k in ("applied", "interviews", "rejections", "offers"):
            if k in (ce.get("counts") or {}): car["email_" + k] = ce["counts"][k]
        car["email_scan_at"] = ce.get("at")
        car["email_not_in_tracker"] = ce.get("not_in_tracker_count")
    except Exception:
        pass
    # Growth tracker (daily scan): mock interviews from the calendar, Exponent % from Minny's weekly read.
    try:
        gr = json.load(open("/home/user/ops-bus/goals/growth.json"))
        if g.get("progress") is not None:
            gp = g["progress"].setdefault("growth", {})
            for k in ("mock_interviews", "exponent_progress_pct", "exponent_source"):
                if gr.get(k) is not None: gp[k] = gr[k]
            gp["growth_scan_at"] = gr.get("at")
    except Exception:
        pass
    # Career quality metric (Nat, 11-12): target companies where he has a warm contact (had a real conversation),
    # from Pinny's research/career/warm-paths.md (Warm / identified / none per company).
    try:
        rows = [l for l in open("/home/user/ops-bus/research/career/warm-paths.md") if re.match(r"\|\s*\d+\s*\|", l)]
        kinds = [l.split("|")[3].replace("*", "").strip().lower() for l in rows]
        car = (g.get("progress") or {}).setdefault("career", {}) if g.get("progress") is not None else None
        if car is not None and rows:
            car["warm_companies"] = sum(k.startswith("warm") for k in kinds)
            car["identified_companies"] = sum(k.startswith("identified") for k in kinds)
            car["target_companies"] = len(rows)
    except Exception:
        pass
    # One career headline: applications sent = the larger of Notion (applied-or-later) and the Gmail scan.
    try:
        car = (g.get("progress") or {}).get("career") or {}
        notion_sent = sum(int(car.get(k) or 0) for k in ("applied", "interviewing", "offers", "rejected"))
        car["applied_total"] = max(notion_sent, int(car.get("email_applied") or 0))
        car["applied_total_note"] = f"max of Notion {notion_sent} (applied+interviewing+offers+rejected) and Gmail scan {car.get('email_applied')}"
        car["email_not_in_tracker"] = max(0, int(car.get("email_applied") or 0) - notion_sent) if car.get("email_applied") is not None else car.get("email_not_in_tracker")
    except Exception:
        pass
    for pillar, vals in (g.pop("overrides", None) or {}).items():
        if g["progress"] is None: g["progress"] = {}
        g["progress"].setdefault(pillar, {}).update(vals)
    return g

# Last activity per project (latest push via the GitHub REST API; skipped when the repo isn't reachable) and
# the supervisor's next step (state.next_steps).
import subprocess as _sp
_ns = state.get("next_steps", {})
for b in board.values():
    b["next_step"] = _ns.get(b["project"], "")
    if b["project"] == "ops-bus":
        # Derive from the live queue instead of a hand-written line (it said "nothing queued" with work pending).
        import glob as _g, re as _re
        _names = {"pro": "Pinny", "instinct": "Binny", "muse": "Minny"}
        _cnt = {}
        for _f in _g.glob("/home/user/ops-bus/requests/pending/*.md"):
            _m = _re.search(r"^runner:\s*(\S+)", open(_f).read(), _re.M)
            if _m: _cnt[_names.get(_m.group(1), _m.group(1))] = _cnt.get(_names.get(_m.group(1), _m.group(1)), 0) + 1
        _q = {k: len(_g.glob(f"/home/user/ops-bus/queue/{d}/*.md")) for k, d in (("Pinny", "pinny"), ("Binny", "binny"), ("Minny", "minny"), ("shared", "shared"))}
        _inf = ", ".join(f"{k} {v}" for k, v in sorted(_cnt.items())) or "none"
        b["next_step"] = f"In flight: {_inf} · queued: " + ", ".join(f"{k} {v}" for k, v in _q.items() if v)
    try:
        out = _sp.run(["gh", "api", f"repos/zuzivian/{b['project']}", "--jq", ".pushed_at"],
                      capture_output=True, text=True, timeout=15).stdout.strip()
        b["last_activity"] = out if out.startswith("20") else None
    except Exception:
        b["last_activity"] = None
try:  # (e) HQ has no repo of its own: use the newest commit on the HQ branch
    _hq = _sp.run(["gh", "api", "repos/zuzivian/new-repo/branches/claude/token-usage-auto-allocation-1hmsvv",
                   "--jq", ".commit.commit.committer.date"], capture_output=True, text=True, timeout=15).stdout.strip()
    if _hq.startswith("20") and "HQ" in board: board["HQ"]["last_activity"] = _hq
except Exception:
    pass
projects_board = sorted(board.values(), key=lambda b: (ORDER[b["status"]], b["project"]))

# ---- HQ strip data: done counts, blocked, allocation, watchdog fixes (all defensive) ----
def _iso(x):
    try:
        t = dt.datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None

def _gh_json(path):
    try:
        r = _sp.run(["gh", "api", path], capture_output=True, text=True, timeout=30)
        return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else []
    except Exception:
        return []

def _done_stats(agents):
    try:
        t24 = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
        t7 = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)
        landed, cur = {}, None
        try:
            log = _sp.run(["git", "-C", OPS, "log", "--diff-filter=A", "--name-only", "--format=%cI", "--since=8.days",
                           "--", "requests/done"], capture_output=True, text=True, timeout=60).stdout
            for line in log.splitlines():
                line = line.strip()
                if not line: continue
                if line.startswith("requests/"):
                    landed.setdefault(line, cur)  # log is newest first; keep the newest add
                else:
                    cur = line
        except Exception:
            pass
        by = {"pinny": [], "binny": [], "minny": []}
        for r in _requests("done"):
            a = RUNNER_BY.get(r["runner"])
            at = _iso(landed.get("requests/done/" + r["file"]))
            if a and at:
                title = re.sub(r"^(Pinny|Binny|Research)\s*[-\u2013:]\s*", "", r["title"] or r["file"]).strip()
                by[a].append((at, {"title": title, "at": at.isoformat(),
                                   "url": "https://github.com/zuzivian/ops-bus/blob/main/requests/done/" + r["file"]}))
        chin = []
        for repo in ("natwong-dev", "new-repo"):
            for pr in _gh_json(f"repos/zuzivian/{repo}/pulls?state=closed&per_page=50") or []:
                at = _iso(pr.get("merged_at"))
                if at and str((pr.get("head") or {}).get("ref", "")).startswith("codex/"):
                    chin.append((at, {"title": pr.get("title"), "at": at.isoformat(), "url": pr.get("html_url")}))
        for a in agents:
            k = a.get("key")
            rows = chin if k in ("chinny", "cinny") else by.get(k)
            if rows is None: continue
            rows.sort(key=lambda x: x[0], reverse=True)
            a["done_24h"] = sum(1 for t, _ in rows if t >= t24)
            a["done_7d"] = sum(1 for t, _ in rows if t >= t7)
            a["last_done"] = rows[0][1] if rows else None
            # Topic of each done item -> STRATEGY pillar (from the request file name/title), for effort vs plan.
            bp = {}
            for t, d in rows:
                if t < t7: continue
                txt = (d.get("url") or "") + " " + (d.get("title") or "")
                low = txt.lower()
                pil = ("digigov" if re.search(r"digigov|digitizing|govtech|login\.gov|govil", low) else
                       "career" if re.search(r"career|deepdive|postings|cpt|h1b|comp-bench|apply|skydio|zoox|waymo|zipline", low) else
                       "growth" if re.search(r"growth|exponent|aced|mock|drill|behavioral", low) else
                       "relationships" if re.search(r"\brel-|relationship|coffee|keep-in-touch|events|alumni|conference", low) else
                       "fleet_hq" if re.search(r"\bhq\b|hq-|fleet|usage|report-test|codex|natwong-dev|new-repo", low) else "other")
                if k in ("chinny", "cinny"): pil = "career" if "natwong-dev" in low else "fleet_hq"
                bp[pil] = bp.get(pil, 0) + 1
            a["done_7d_by_pillar"] = bp
    except Exception:
        pass
    return agents

def _blocked():
    rows = []
    # Nat's own items live in Needs; this strip shows agent and external blockers only.
    try:
        w = load(f"{OPS}/usage/watchdog.json") or {}
        for x in (w.get("stuck") or []):
            rows.append({"agent": "fleet", "title": f"Stuck >6h: {x}", "since": None, "waiting_on": "agent", "url": None})
        for x in (w.get("failed_runs") or []):
            t = x if isinstance(x, str) else x.get("name", "failed run")
            u = None if isinstance(x, str) else x.get("url")
            rows.append({"agent": "actions", "title": f"Failed run: {t}", "since": None, "waiting_on": "external", "url": u})
    except Exception:
        pass
    try:
        for r in _requests("pending"):
            fm_held = re.search(r"^status:\s*held", r["text"], re.M | re.I)
            res = re.split(r"^## Result\s*$", r["text"], maxsplit=1, flags=re.M)
            res_held = len(res) > 1 and re.search(r"\bheld\b", res[1], re.I)
            if fm_held or res_held:
                at = _iso(re.search(r"^requested_at:\s*(\S+)", r["text"], re.M).group(1)) if re.search(r"^requested_at:\s*(\S+)", r["text"], re.M) else None
                rows.append({"agent": RUNNER_BY.get(r["runner"], r["runner"] or "fleet"), "title": r["title"] or r["file"],
                             "since": at.isoformat() if at else None, "waiting_on": "agent",
                             "url": "https://github.com/zuzivian/ops-bus/blob/main/requests/pending/" + r["file"]})
    except Exception:
        pass
    try:
        for i in _gh_json("repos/zuzivian/ops-bus/issues?state=open&labels=fleet&per_page=100") or []:
            if "pull_request" in i: continue
            L = [l["name"] if isinstance(l, dict) else l for l in i.get("labels", [])]
            if "owner:nat" not in L:
                own = next((l.split(":", 1)[1] for l in L if l.startswith("owner:")), "fleet")
                rows.append({"agent": own, "title": i["title"], "since": i.get("created_at"), "waiting_on": "agent", "url": i["html_url"]})
    except Exception:
        pass
    rows.sort(key=lambda r: (r["since"] is None, str(r["since"] or "")))
    return rows[:14]

def _allocation():
    try:
        line = next(l for l in open(OPS + "/STRATEGY.md") if re.match(r"\s*Career\s+\d+", l))
        keys = {"career": "career", "digitizing government": "digigov", "growth": "growth",
                "relationships": "relationships", "fleet/hq": "fleet_hq"}
        al = {}
        for name, n in re.findall(r"([A-Za-z/ ]+?)\s+(\d+)\s*%?", line.split("(")[0].replace("\u00b7", " ")):
            k = keys.get(name.strip().lower())
            if k: al[k] = int(n)
        return al or None
    except Exception:
        return None

def _fixes():
    rows = []
    try:
        for d in state.get("decisions", []):
            if d.get("kind") == "fix":
                rows.append({"at": d.get("at"), "agent": "fleet-ops", "what": d.get("decision"), "link": d.get("link")})
    except Exception:
        pass
    try:
        w = load(f"{OPS}/usage/watchdog.json")
        if isinstance(w, dict):
            for a in w.get("actions") or []:
                if isinstance(a, dict):
                    rows.append({"at": a.get("at") or w.get("at"), "agent": "watchdog", "what": a.get("what") or a.get("action") or json.dumps(a), "link": a.get("link")})
                else:
                    rows.append({"at": w.get("at"), "agent": "watchdog", "what": str(a), "link": None})
    except Exception:
        pass
    rows.sort(key=lambda r: (_iso(r["at"]) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)), reverse=True)
    return rows[:20]


now = dt.datetime.now(dt.timezone.utc)
meetings = []
for p in primers.get("primers", []):
    when = dt.datetime.fromisoformat(p["when"])
    if when > now - dt.timedelta(minutes=30):
        meetings.append({**p, "ready": True})
meetings.sort(key=lambda m: m["when"])

MERGE_REPOS = ["natwong-dev", "skyviu", "ad-constellation"]  # new-repo: session drafts + the HQ branch PR, never one-click

def _merge_queue():
    """Open PRs awaiting Nat for HQ one-click merge. Repos this builder can't reach fall back to
    ops-bus supervisor/merge-queue.json rows (Sinny writes them: same fields). Bus PRs (ops-bus) are excluded."""
    rows, reached = [], set()
    for repo in MERGE_REPOS:
        r = _sp.run(["gh", "api", f"repos/zuzivian/{repo}/pulls?state=open&per_page=50"], capture_output=True, text=True, timeout=30)
        if r.returncode != 0: continue
        reached.add(repo)
        for pr in json.loads(r.stdout or "[]"):
            if "DO NOT MERGE" in pr.get("title", ""): continue
            labels = [l["name"] for l in pr.get("labels", [])]
            sha = pr["head"]["sha"]
            st = _gh_json(f"repos/zuzivian/{repo}/commits/{sha}/status") or {}
            cr = (_gh_json(f"repos/zuzivian/{repo}/commits/{sha}/check-runs?per_page=100") or {}).get("check_runs", [])
            # sinny-gate mirrors the review label (shown as `reviewed`), so leave it out of `checks` to keep real CI visible.
            gate = lambda n: "sinny-gate" in (n or "")
            states = [s.get("state") for s in (st.get("statuses") or []) if not gate(s.get("context"))]
            cr = [c for c in cr if not gate(c.get("name"))]
            states += ["pending" if c.get("status") != "completed" else
                       ("success" if c.get("conclusion") in ("success", "neutral", "skipped") else "failure") for c in cr]
            checks = ("failing" if any(x in ("failure", "error") for x in states) else
                      "pending" if any(x == "pending" for x in states) else "green")
            rows.append({"repo": repo, "number": pr["number"], "title": pr["title"], "url": pr["html_url"],
                         **({"waiting": "Nat review"} if "nat:review" in labels else {}),
                         "reviewed": "sinny:reviewed" in labels, "checks": checks, "draft": bool(pr.get("draft")),
                         "since": pr.get("updated_at") or pr.get("created_at"), "author": pr["user"]["login"]})
    try:
        extra = json.load(open("/home/user/ops-bus/supervisor/merge-queue.json"))
        for x in extra.get("rows", extra if isinstance(extra, list) else []):
            if x.get("repo") not in reached and x.get("url", "").startswith("https://github.com/"):
                rows.append({k: x.get(k) for k in ("repo", "number", "title", "url", "reviewed", "checks", "draft", "since", "author", "waiting") if k in x})
    except Exception:
        pass
    # waiting: explicit reason override, e.g. Sinny's own workflow PRs it can't self-merge -> "Nat review".
    # Sources: label "nat:review", a fallback row's "waiting", or state.json merge_waiting {"repo#n": reason}.
    try:
        mw = state.get("merge_waiting", {})
    except Exception:
        mw = {}
    for r in rows:
        w = mw.get(f"{r['repo']}#{r['number']}") or r.get("waiting")
        if w: r["waiting"] = w
    rows = [r for r in rows if not (r["draft"] and r.get("author", "").endswith("[bot]"))]
    return sorted(rows, key=lambda r: (not r["reviewed"], r["checks"] != "green", r["draft"], r["since"] or ""))

out = {
    "updated": now.isoformat(),
    "week": state["week"],
    "pacing": cfg["pacing"],
    "allocation": cfg.get("allocation", {}).get("tiers", {}),
    "needs": state.get("needs", []),
    # Live rows first; keep only the 6 most recent finished rows so the list doesn't grow forever.
    # Nat's goals (targets from Binny gsb-year1-goals; live counts from Pinny's Notion feed in ops-bus goals/progress.json).
    "goals": _goals(),
    # Fleet pacer (scratchpad pace_fleet.py → ops-bus usage/pacing.json): Pinny/Minny/Chinny vs a 92%-by-reset line.
    # Career targets: Pinny's research/career/internship-timelines.md table (ops-bus, private) as rows.
    "career_targets": (lambda: _md_table("/home/user/ops-bus/research/career/internship-timelines.md"))(),
    # Warm leads per eligible target company (Pinny, ops-bus goals/career_warm.json; counts only, no names).
    "career_warm": (lambda: (lambda f: json.load(open(f)) if os.path.exists(f) else [])("/home/user/ops-bus/goals/career_warm.json"))(),
    # Overdue keep-in-touch contacts (Pinny, ops-bus goals/keep_in_touch.json: first name, company, Notion link, reason).
    "keep_in_touch": (lambda f: json.load(open(f)) if os.path.exists(f) else [])("/home/user/ops-bus/goals/keep_in_touch.json"),
    "gh_issues": _gh_issues(),
    "nat_actions": _nat_actions(),
    "watchdog": _watchdog(),
    # Key decisions the supervisor made on Nat's behalf (newest first), so he can review or reverse them.
    "research": _research(),
    "overnight": state["overnight"] if isinstance(state.get("overnight"), dict) else None,
    "decisions": _decisions(),
    "fleet_pacing": (lambda: (json.load(open("/home/user/ops-bus/usage/pacing.json")) if os.path.exists("/home/user/ops-bus/usage/pacing.json") else None))(),
    "workers": [w for w in state.get("workers", []) if not str(w.get("status","")).startswith("done")]
               + [w for w in state.get("workers", []) if str(w.get("status","")).startswith("done")][:6],
    "spend": spend_rows,
    "meetings": meetings,
    "pro": state.get("pro", {"note": "Not connected yet."}),
    "supervisor": state.get("supervisor"),
    "cost": cost,
    "board": projects_board,
    "agents": _done_stats(_doing_from_requests(state.get("agents", []))),
    "blocked": _blocked(),
    "issues": sorted(state.get("issues", []), key=lambda i: ({"critical": 0, "high": 1, "medium": 2, "low": 3}.get(i.get("severity"), 4), i.get("since", ""))),
}
_al = _allocation()
if _al: out["allocation"] = _al
try:
    out["merge_queue"] = _merge_queue()
except Exception:
    out["merge_queue"] = []
try:
    out["watchdog"] = {**(out.get("watchdog") or {}), "fixes": _fixes()}
except Exception:
    pass
with open(os.path.join(HERE, "data.json"), "w") as fh:
    json.dump(out, fh, indent=1)
print(f"data.json: {len(spend_rows)} projects, {len(meetings)} meetings, {len(out['needs'])} needs")
