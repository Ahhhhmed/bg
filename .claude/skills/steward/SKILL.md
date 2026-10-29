---
name: steward
description: How pull requests move through this repo -- branches, what CI and Vercel do, how to tell a preview is current, who merges and how, and what to verify after a merge. Use when opening, babysitting, merging or following up on any PR, when a CI or Vercel event arrives, or when asked "is it live yet?".
---

# Steward: PRs from branch to production

The owner reviews and merges; Claude prepares PRs that can be merged in one sitting and
proves they work. Item work follows the `backlog` skill.

## Branches and PRs
- One backlog item per branch and PR: `claude/backlog-NNN-slug` from `origin/main`.
- Never push to `main`; never merge unless the owner says so for that change.
- Merge method: a merge commit. Stacked branches build on each other's commits.

## What runs on a PR
| Check | When | Notes |
|---|---|---|
| `check` (GitHub workflow) | every push | compile, backlog check, `scripts/build.sh` (privacy guard), `scripts/check.cjs` on the built site |
| Vercel build + preview | every push | `vercel.json` -> `scripts/build.sh` -> `dist/` |

## Is the preview current?
`bash scripts/preview_url.sh` prints the branch's URLs; hand the owner the city they asked
about. Don't wait for a Vercel bot comment. The preview serves the new commit when a string
you changed shows up in a served file (`curl -s <preview>/<city>/web/<file>.js | grep ...`)
or a changed data file answers with its new content. Then run `verify-site` against it.

## After a merge
1. Production redeploys from `main`; wait until it serves the merge's change.
2. `node scripts/check.cjs <production url>`; report the result to the owner.
3. Next time you touch the backlog: move merged items to `backlog/done/`.

## Decisions
A decision the owner makes that future sessions must not undo goes into
[`docs/decisions.md`](../../../docs/decisions.md) in the same PR.
