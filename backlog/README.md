# Backlog

One file per work item: `NNN-short-slug.md` (copy [`_TEMPLATE.md`](_TEMPLATE.md)).
Finished items move to [`done/`](done/).

You tell Claude which item to focus on (typically one a day); Claude works
it thoroughly on a `claude/backlog-NNN-*` branch and opens a PR for you to
review. How Claude works an item is in
[`.claude/skills/backlog/SKILL.md`](../.claude/skills/backlog/SKILL.md).

Your part:
- **Curate**: set `priority` (P1 first), move items from `draft` to `ready` once
  Scope and Acceptance criteria are concrete, answer `blocked_on`.
- **Direct**: "work on 001" (optionally with extra guidance) starts a working session on it.
- **Review** the PR: open the preview link, check the acceptance criteria,
  then merge, comment / tell Claude what to change, or close.

```bash
python3 scripts/backlog.py list    # queue in pick order
python3 scripts/backlog.py next    # top suggestion by priority
python3 scripts/backlog.py check   # validate all items
```
