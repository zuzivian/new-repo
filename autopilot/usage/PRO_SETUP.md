# Connect the Pro account to Autopilot HQ

The Stanford supervisor can't see the Pro account. The Pro account therefore
publishes one small usage snapshot a day to this repo, and HQ merges it in.

**Nat:** open Claude Code in your **Pro** account, start a cloud session on
`zuzivian/new-repo`, and paste the prompt below. That's all.

---

You are setting up a daily usage snapshot for Nat's **Pro** Claude account, so
his Autopilot HQ dashboard (run from his Stanford account) can merge it in.

1. Take a snapshot now:
   - `get_session` (no id) → your own session id. Then `list_events` on it with
     `kinds: ["rate_limit_event"]`, `limit: 100`, and take the newest
     `rate_limit_info.unifiedWindows`: `seven_day` and `five_hour` utilization
     and `resetsAt`.
   - `list_sessions` (`mine: true`), paging back over the last 24 hours. For each
     one, `get_session`, and sum `external_metadata.usage.cost_usd` and tokens by
     repo name (from `session_context.sources`).
   - **Privacy:** this repo is public. Record **only** numbers and the names of
     public repos. Sum private repos and sessions with no repo into
     `"private"`. Never write session titles, prompts, messages or people.
2. Write `usage/pro/<YYYY-MM-DD>.json` (date in America/Los_Angeles) on branch
   `usage-data` of `zuzivian/new-repo`. Create the branch from `master` if it
   doesn't exist. Push directly; no PR. Use this shape:
   `{"account":"pro","date":"…","taken_at":"<UTC ISO>","seven_day":{"utilization":0.0,"resetsAt":0},"five_hour":{"utilization":0.0,"resetsAt":0},"cost_usd_24h":{"<repo>":0.0,"private":0.0},"sessions_24h":0}`
3. Create a **daily** scheduled task in this Pro account that starts a fresh
   session at 11:41pm America/Los_Angeles
   (`CRON_TZ=America/Los_Angeles 41 23 * * *`) and runs steps 1–2. Its prompt is
   this whole block minus step 3. If scheduled tasks are unavailable, say so
   plainly and stop after the first snapshot.
4. Reply in three lines: snapshot pushed (the file path), whether the daily task
   was created, and the Pro account's weekly utilization and reset time in PT.
