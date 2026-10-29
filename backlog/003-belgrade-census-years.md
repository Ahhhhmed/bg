---
id: "003"
title: Belgrade: dwellings by period built (census)
status: blocked
city: belgrade
priority: P2
size: S
area: data
depends_on: []
hosts: ["data.stat.gov.rs"]
blocked_on: "data.stat.gov.rs / www.stat.gov.rs answer 403 to the sandbox; needs another route to the RZS census tables (2022 census: dwellings by period of construction per municipality)."
pr: ""
updated: 2026-10-29
---

## Why
Belgrade has no year built per building. The census gives, per municipality, how many dwellings were built in each period: an honest area-level picture.

## Scope
- In: an area lens per municipality (share of dwellings built before 1971, ...), never a year on a building (C-05).
- Out: estimating years for buildings.

## Acceptance criteria
- [ ] The lens shows each of the 10 municipalities with its census shares and the table's source and date.

## Notes
- RZS (Republički zavod za statistiku), census 2022. The data.gov.rs search found only 2011-era dwelling tables (`stanovi-prema-povrshini`, ...).

## Log
- 2026-10-29: item written while preparing the public repo.
