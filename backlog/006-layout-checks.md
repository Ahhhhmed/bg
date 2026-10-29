---
id: "006"
title: City-aware layout checks
status: ready
city: all
priority: P2
size: S
area: infra
depends_on: []
hosts: []
blocked_on: ""
pr: ""
updated: 2026-10-29
---

## Why
The layout checks (overlaps, off-screen controls, 44 px touch targets on six screen sizes) were never ported; only `scripts/check.cjs` runs today.

## Scope
- In: `scripts/ui_overlap.cjs` and `scripts/ui_audit.cjs` taking a city, run on both cities; fix what they find.
- Out: new features.

## Acceptance criteria
- [ ] Both scripts pass on both cities on the preview; output in the PR.

## Notes
- The checks to port test the brand card, lens popover, profile panel, legend bar, attribution pin and the bottom sheets.

## Log
- 2026-10-29: item written while preparing the public repo.
