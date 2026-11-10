# Autopilot: use the weekly Claude limit without thinking about it

**The problem:** the weekly limit resets Saturday at 3:00pm PT (23:00 UTC, so
4:00pm while daylight time is on). By Friday, a lot of it is usually unused,
and 5-hour session limits make it impossible to burn it all at the end.

**What this does:** a scheduled task wakes a small **runner** session every 3
hours. The runner reads the account's real usage (cloud sessions record
`seven_day` and `five_hour` utilisation in their `rate_limit_event`s) and
compares it with a pacing curve:

```
slow phase  Sat 3pm → Tue 3pm: target rises gently 0 → 15%, max 2 workers
fast phase  Tue 3pm → Sat 3pm: target rises linearly 15% → 92%, max 6 workers
final sweep last 24 h:         target = 92% (all-out)
```

| Time left | Sat 3pm | Sun 3pm | Mon 3pm | Tue 3pm | Wed 3pm | Thu 3pm | Fri 3pm |
|---|---|---|---|---|---|---|---|
| Target | 0% | 5% | 10% | 15% | 34% | 54% | 92% |

Saturday to Tuesday runs slowly, so most of the budget stays free for Nat's own
big ideas. From Tuesday it speeds up. The fast phase needs about 0.8% of the
week per hour, against a ceiling of about 2.8% per hour (one 5-hour window, at
about 14% of the week, every 5 hours), so it is reachable with room to spare.
The knobs are `ramp_start_hours_before_reset` (96), `slow_phase_target` (0.15)
and `max_workers_slow_phase` (2).

**Decision digest.** Nat misses questions spread across many sessions, so the
supervisor collects them in its own thread as one numbered list. Each item comes
with a recommended answer. The list covers sessions blocked on him for more than
2 hours, Autopilot PRs he hasn't touched in more than 24 hours, and proposed new
tasks for idle projects. Pings: the digest in the thread, plus a best-effort phone push. No email or calendar writes, because those need approval each time. He replies there, e.g. "1 → new branch, 4 → yes", and
the supervisor relays each answer to its session or starts the approved work.

If usage is more than 3 points behind target, it starts up to 3 **worker**
sessions (1 while Nat is actively using Claude). It never lets the 5-hour window
go past 70%, so Nat always has headroom of his own. Each worker moves one enabled
project forward by one reviewable unit of work on branch `autopilot/<project>`,
behind a single draft PR per repo named `Autopilot: <project>`.

| File | What it is |
|---|---|
| `config.json` | On/off switch, pacing knobs, project list with per-project briefs |
| `pace.py` | Deterministic "how many workers now?" calculator (stdlib only) |
| `RUNNER.md` | Instructions the scheduled runner follows |
| `WORKER.md` | Instructions and hard limits every worker gets |
| `tests/` | `python3 -m unittest discover -s autopilot/tests` |

## Status (2026-11-07): the timer is blocked
Scheduled tasks are **off for the Stanford Claude org**. Both recurring and
one-shot scheduling are refused ("Organization settings → Capabilities"), so
the runner can't wake itself yet. Everything else is verified: usage reads from
a cloud session, `pace.py` decides, and `create_session` starts workers. Ways to
unblock, best first:
1. A Stanford org admin turns on scheduled tasks. Then create a 3-hourly
   scheduled task (new session per run) whose prompt is: *follow
   autopilot/RUNNER.md in zuzivian/new-repo*.
2. Run the same scheduled task from an account that allows it. Note: pacing is
   per account. A runner only spends the limit of the account it runs on.
3. Until then, run it manually: open a cloud session on this repo and say
   "follow autopilot/RUNNER.md". A run takes about a minute.

## Stalls: limits, crashes, restarts
A session that hits the 5-hour limit, errors out, or loses its container just
sits idle, so long tasks quietly stall. The runner handles this (RUNNER.md step 3b):
- **Detect:** workers must end with `AUTOPILOT-DONE` / `AUTOPILOT-NOTHING-TO-DO`.
  An idle worker without that line counts as stalled. Nat's own long sessions
  opt in by adding the tag `autopilot-watch`.
- **Wait:** if the session's last rate-limit event shows it was blocked, the
  runner leaves it alone until that window's reset time.
- **Resume:** the runner messages the session to continue, as long as the
  5-hour window has room. That takes priority over starting new work.
- **Cap:** after 3 resumes, the session is tagged `autopilot-stuck` and reported
  to Nat.
- **Cheap restarts:** workers push after every verified step and keep an
  "Autopilot in progress" note in NOTES.md, so a resumed session, or a fresh
  worker on the same branch, picks up where the last one stopped.

## Supervisor mode (works with scheduling off)
One cloud session can act as the timer: it runs a background `sleep`, and when
that ends, the session wakes, follows RUNNER.md, and re-arms. To start it, open a
cloud session on this repo and say *"be the autopilot supervisor: follow
autopilot/RUNNER.md now and every 90 minutes using a background sleep"*. It
stops when that session is archived or reclaimed, so check it once a week.

## Controls
- **Pause:** set `"enabled": false` in `config.json`, or pause the "Claude plan
  autopilot" scheduled task in claude.ai → Code → Scheduled.
- **Add or remove a project:** flip `enabled`, edit `brief`, or change `weight`.
- **Less aggressive:** lower `weekly_target`, `max_workers` or
  `five_hour_ceiling`.
- **Review backlog brake:** a project pauses itself once its Autopilot PR has more
  than 12 unreviewed commits.

## Safety
Workers never merge, never push to default branches, never touch secrets or
deploy config, and never skip tests. Nat reviews and merges every Autopilot PR.

## Calibrating
`worker_cost_7d` (2%) and `worker_cost_5h` (15%) are starting guesses. After a
week, compare runner reports (u7 before vs. after) and adjust.
