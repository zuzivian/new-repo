# One-click merge from HQ

HQ lists PRs that are ready for Nat. Each row has a **Merge on GitHub** button. No GitHub token is stored in HQ, in this repo or in the browser. GitHub itself does the merge, under Nat's own login.

## Why it is "one click plus a confirm"
Only a logged-in GitHub session can merge without a stored token, and GitHub has no link that merges a PR in one step. GitHub's PR page needs two clicks: **Squash and merge**, then **Confirm**. HQ gets Nat to that page in one tap from the phone. So it's one tap on HQ, then two clicks on GitHub.

## What enforces "Sinny reviewed, checks green, not a draft"
GitHub's merge button does the enforcing. It stays disabled until branch protection is satisfied:

1. **`sinny-gate`** (`.github/workflows/sinny-gate.yml`) is a status check. It passes only while the PR has the `sinny:reviewed` label. Any new commit removes the label and fails the check, so a changed PR needs a fresh review.
2. **Branch protection** on the default branch must require `sinny-gate` and the repo's CI checks. Draft PRs can't be merged on GitHub at all.
3. Only `zuzivian` has write access, so only Nat can press the button.

There's also a fallback for when the merge box is awkward on a phone. Commenting `/merge` on the PR runs **`nat-merge`** (`.github/workflows/nat-merge.yml`). It squash-merges only if all of these hold:
- the commenter is `zuzivian` and is the repo owner;
- the PR is open and not a draft;
- the PR has `sinny:reviewed`;
- every check is green;
- the head commit hasn't changed since the checks ran.

It uses the run's built-in `GITHUB_TOKEN`. A merge made that way doesn't start other Actions workflows on the default branch. That's fine for Vercel's Git-based deploys, but not for a deploy that runs in Actions.

## Setup per repo (natwong-dev, skyviu, ad-constellation): Nat, about 3 min each
1. Apply the patch from the repo root: `git am < merge-workflows.patch`, or copy the two files into `.github/workflows/`. Then push to the default branch.
2. Create the label: `gh label create "sinny:reviewed" --color 2da44e --description "Reviewed by Sinny; ready for Nat"`.
3. Go to Settings → Branches → the default branch's rule, turn on **Require status checks to pass**, and add `sinny-gate` plus the existing CI checks. Also turn on **Require branches to be up to date**.
4. Go to Settings → General → Pull Requests and allow squash merging.

## HQ data (Fleet Ops)
`data.merge_queue[]`: `{repo, number, title, url, reviewed: bool, checks: "green"|"pending"|"failing", draft: bool, since}`.
- HQ shows a row as **ready** when `reviewed && checks=="green" && !draft`.
- Every other row is listed under "Waiting", with the reason.
- `reviewed` means the PR has the `sinny:reviewed` label.
