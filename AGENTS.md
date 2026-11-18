# AGENTS.md — Autopilot HQ (for Chinny / Codex and other agents)

HQ is Nat's personal goals + fleet dashboard. The page is `autopilot/hq/index.html` (single file, vanilla HTML/CSS/JS, no build step, no framework, no npm deps). Data comes from `autopilot/hq/data.json` locally (`/api/data` in production). The supervisor syncs this file to the private ops-bus repo, where Vercel serves it behind Nat's login.

## Rules
- Change only `autopilot/hq/index.html` (and `autopilot/hq/static/*` if the issue says so). Never touch `build.py`, data files, `.github/` or anything outside `autopilot/hq/`.
- Never add real personal data, names, emails, tokens or secrets. Test with the fixture data the issue provides, or with `data.json` as-is.
- Keep `fetch("data.json"` as the data load (the sync rewrites it to `/api/data`).
- Missing fields must render as "no feed yet" or hide; never show 0 for null, never throw.
- Accessibility: buttons are `<button>`, focus visible, contrast AA, works at 390 px wide with no horizontal scroll.
- Match the existing look (CSS variables at the top of the file). No new external requests, fonts or CDNs.
- Small, scoped diffs. One issue = one change.

## Checks (run all; report in the final CHECKS line)
1. `node -e "const h=require('fs').readFileSync('autopilot/hq/index.html','utf8'); const m=h.match(/<script>([\s\S]*?)<\/script>/g)||[]; for (const s of m) new Function(s.replace(/<\/?script>/g,'')); console.log('js parses', m.length)"`
2. `python3 -c "import html.parser,sys; html.parser.HTMLParser().feed(open('autopilot/hq/index.html').read()); print('html ok')"`
3. If Playwright is available: open the page via a static server over `autopilot/hq/` at 1280×900 and 390×844, and assert no console errors and `document.documentElement.scrollWidth <= innerWidth`.
