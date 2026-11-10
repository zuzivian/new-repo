#!/usr/bin/env python3
"""Decide how many autopilot workers to start right now.

Pure stdlib. Given the account's current limit utilisation (from a cloud
session's rate_limit_event), compare weekly usage against a pacing curve
that ends near `weekly_target` at the weekly reset, and return how many
worker sessions to dispatch without crowding the 5-hour window.

Usage:
  python3 autopilot/pace.py --u7 0.24 --u5 0.04 --reset7 1794092400 \
      [--now 1794060000] [--in-flight 1] [--user-active] [--config path]

Prints one JSON object: {"workers": n, "target": t, "gap": g, "reason": "..."}.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

WEEK_HOURS = 168.0

DEFAULTS = {
    "weekly_target": 0.92,       # aim to have used this much by reset
    "ramp_start_hours_before_reset": 72,  # target is 0 before this (Wed 3pm)
    "final_sweep_hours": 24,     # in the last N hours, target = weekly_target
    "min_gap": 0.03,             # do nothing if within 3 pts of the curve
    "five_hour_ceiling": 0.70,   # never push the 5h window past this
    "worker_cost_7d": 0.004,     # est. weekly utilisation one worker uses
    "worker_cost_5h": 0.025,     # est. 5h-window utilisation one worker uses
    "max_workers": 6,            # per run
    "max_workers_when_user_active": 1,
}


def load_pacing(config_path: str | None) -> dict:
    cfg = dict(DEFAULTS)
    if config_path and os.path.exists(config_path):
        with open(config_path) as fh:
            cfg.update(json.load(fh).get("pacing", {}))
    return cfg


def target_utilisation(hours_left: float, cfg: dict) -> float:
    """Back-loaded pacing curve.

    Target is 0 until `ramp_start_hours_before_reset` (default 72 h = Wed 3pm
    for a Sat 3pm reset), so Sat-Wed stays free for Nat's own ideas. It then
    rises linearly to weekly_target at reset; in the final sweep it jumps to
    weekly_target so autopilot goes all-out on the last day.
    """
    if hours_left <= cfg["final_sweep_hours"]:
        return cfg["weekly_target"]
    ramp = min(max(cfg["ramp_start_hours_before_reset"], 1.0), WEEK_HOURS)
    if hours_left >= ramp:
        return 0.0
    return cfg["weekly_target"] * (1.0 - hours_left / ramp)


def decide(u7: float, u5: float, reset7: float, now: float, cfg: dict,
           in_flight: int = 0, user_active: bool = False) -> dict:
    hours_left = max((reset7 - now) / 3600.0, 0.0)
    target = target_utilisation(hours_left, cfg)
    gap = target - u7
    out = {"workers": 0, "target": round(target, 3), "gap": round(gap, 3),
           "hours_left": round(hours_left, 1), "u7": u7, "u5": u5,
           "in_flight": in_flight}

    if hours_left <= 0:
        return {**out, "reason": "weekly reset time has passed; usage data is stale"}
    if u7 >= cfg["weekly_target"]:
        return {**out, "reason": "weekly target reached"}
    if u5 >= cfg["five_hour_ceiling"]:
        return {**out, "reason": "5-hour window is busy; leaving headroom"}
    if gap < cfg["min_gap"]:
        return {**out, "reason": "on pace"}

    want = math.ceil(gap / cfg["worker_cost_7d"])
    room_5h = math.floor((cfg["five_hour_ceiling"] - u5) / cfg["worker_cost_5h"] + 1e-9)
    cap = cfg["max_workers_when_user_active"] if user_active else cfg["max_workers"]
    n = max(0, min(want, room_5h, cap) - in_flight)
    reason = f"behind pace by {gap:.0%}"
    if n == 0:
        reason += "; no room after in-flight workers / 5h headroom"
    elif user_active:
        reason += "; Nat is active, capped"
    return {**out, "workers": n, "reason": reason}


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--u7", type=float, required=True, help="seven_day utilization 0..1")
    p.add_argument("--u5", type=float, required=True, help="five_hour utilization 0..1")
    p.add_argument("--reset7", type=float, required=True, help="seven_day resetsAt (unix s)")
    p.add_argument("--now", type=float, default=None)
    p.add_argument("--in-flight", type=int, default=0)
    p.add_argument("--user-active", action="store_true")
    p.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "config.json"))
    a = p.parse_args(argv)
    cfg = load_pacing(a.config)
    res = decide(a.u7, a.u5, a.reset7, a.now if a.now is not None else time.time(),
                 cfg, a.in_flight, a.user_active)
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
