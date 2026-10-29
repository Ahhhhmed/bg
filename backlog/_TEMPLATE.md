---
id: "000"            # 3 digits, same as the filename prefix; never reused
title: Short imperative title
status: draft        # draft | ready | in-progress | review | blocked | done
city: all            # all | zurich | belgrade
priority: P2         # P1 (next up) | P2 | P3 (someday)
size: M              # S (< half a run) | M (one run) | L (too big: split before starting)
area: map            # map | data | infra | docs
depends_on: []       # ids that must be done first, e.g. ["008"]
hosts: []            # network hosts the work needs beyond the default allowlist
blocked_on: ""       # what a human has to provide or decide; empty if nothing
pr: ""               # PR URL once one is open
updated: 2026-01-01
---

## Why
One or two sentences: what this gives the people using the map.

## Scope
- In: what to build.
- Out: what NOT to touch in this item (goes into a new item instead).

## Acceptance criteria
Each line must be checkable from command output, a URL, or a screenshot.
- [ ] ...
- [ ] Project definition of done holds (see `.claude/skills/backlog/SKILL.md`).

## Notes
Pointers: relevant files, data sources, prior attempts, gotchas.

## Log
<!-- Newest last. One dated line per working session: what happened, decisions made, what is left. -->
