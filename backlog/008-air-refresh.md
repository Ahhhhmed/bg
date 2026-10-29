---
id: "008"
title: Keep the air values fresh
status: draft
city: belgrade
priority: P3
size: S
area: infra
depends_on: []
hosts: ["opendata.kosava.cloud"]
blocked_on: "How often to refresh (monthly?) and whether a scheduled CI job may commit data."
pr: ""
updated: 2026-10-29
---

## Why
The air card's 30-day window is a snapshot of the build day and ages.

## Scope
- In: a scheduled refresh (`build_air.py --refresh` + tiles) or a clear age on the card.
- Out: live values in the browser (the map shouldn't depend on SEPA's server being up).

## Acceptance criteria
- [ ] TBD.

## Notes
- The card already shows the window's dates; the attribution pin shows the data age (C-16).

## Log
- 2026-10-29: item written while preparing the public repo.
