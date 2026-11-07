# Autopilot: use the weekly Claude limit without thinking about it

**The problem:** the weekly limit resets Saturday at 3:00pm PT (23:00 UTC, so
4:00pm while daylight time is on). By Friday, a lot of it is usually unused,
and 5-hour session limits make it impossible to burn it all at the end.

**What this does:** a scheduled task wakes a small **runner** session every 3
hours. The runner reads the account's real usage (cloud sessions record
`seven_day` and `five_hour` utilisation in their `rate_limit_event`s) and
compares it with a pacing curve:

```
target = 92% × (fraction of the week elapsed)     # linear
target = 92%                                      # in the last 24 h ("final sweep")
```

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
