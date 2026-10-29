---
id: "005"
title: Belgrade: more places from OpenStreetMap
status: blocked
city: belgrade
priority: P2
size: M
area: data
depends_on: []
hosts: ["download.geofabrik.de", "overpass-api.de"]
blocked_on: "No OSM extract or Overpass server was reachable from the sandbox (2026-10-29); Overture places alone are thin (~170 pharmacies)."
pr: ""
updated: 2026-10-29
---

## Why
Walking distances say 'nearest known'; with OSM's points of interest they'd be much closer to the truth.

## Scope
- In: OSM amenities (pharmacy, doctors, kindergarten, school, supermarket, post office, playground, pool) merged with Overture's by C-05's rules.
- Out: name-pattern matching.

## Acceptance criteria
- [ ] Counts per kind before / after in the PR; walking medians before / after.

## Notes
- `PLACES` and `MIN_CONFIDENCE` in `cities/belgrade/pipeline/build_layers.py`.

## Log
- 2026-10-29: item written while preparing the public repo.
