---
id: "004"
title: Belgrade: BG Voz city rail in the commute
status: blocked
city: belgrade
priority: P3
size: M
area: data
depends_on: []
hosts: []
blocked_on: "BG Voz has no GTFS; its data.gov.rs CSVs (bg-voz-*) are from 2020 and give only the first stop's departure times, so travel times between stations would be guessed."
pr: ""
updated: 2026-10-29
---

## Why
City rail stations (Vukov spomenik, Karađorđev park, Novi Beograd ...) are missing from the stop cards and the commute.

## Scope
- In: BG Voz trips in the profile scan once a timetable with times per station exists.
- Out: guessed times.

## Acceptance criteria
- [ ] BG Voz stations on the map with stop cards; the commute uses them.

## Notes
- `cities/belgrade/pipeline/build_transit.py` merges GTFS feeds by stop id; a BG Voz GTFS would be a third feed.

## Log
- 2026-10-29: item written while preparing the public repo.
