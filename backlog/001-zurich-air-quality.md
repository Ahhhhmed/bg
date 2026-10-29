---
id: "001"
title: Air quality in Zürich: the city's stations and BAFU's modelled annual maps
status: ready
city: zurich
priority: P3
size: M
area: map
depends_on: []
hosts: ["data.stadt-zuerich.ch", "data.geo.admin.ch"]
blocked_on: ""
pr: ""
updated: 2026-10-29
---

## Why
Zürich is the reference (C-23), so this is P3: it shows what a full air layer looks like next to Belgrade's stations.
Zürich's air layer is greyed today, while Belgrade has 24 stations. Zürich has better data: the city's measuring stations and a federal model for every location.

## Scope
- In: (1) the City of Zürich's UGZ stations (Stampfenbachstrasse, Schimmelstrasse, Rosengartenstrasse, Heubeeribüel) as `places_air.geojson` with the same card as Belgrade (last 30 days' means, last full year's annual means, limits for reference; LRV annual limits NO₂ 30, PM10 20, PM2.5 10 µg/m³). (2) BAFU's 2025 modelled NO₂ / PM10 / PM2.5 sampled at every building (`air_no2_ug`, `air_pm10_ug`, `air_pm25_ug`): an "Air" lens with three variants, a card block, a profile criterion. Belgrade: the new lens greyed (`air: NONE`).
- Out: NABEL / OSTLUFT stations (later, if open and reachable; ostluft.ch didn't answer from the sandbox on 2026-10-29); Belgrade's model (none exists).

## Acceptance criteria
- [ ] 4 UGZ stations with 30-day and annual means; source dates on the card.
- [ ] Every Zürich building has the three model values or a stated reason; counts and 10/50/90th percentiles in the PR.
- [ ] Model vs measurement at each station for the same year, printed in the PR.
- [ ] The air lens's colours pass the colour checks; screenshot along Rosengartenstrasse.
- [ ] Profile criterion on NO₂: counts match `critPass()` on the preview.
- [ ] `node scripts/check.cjs <preview>` passes; Belgrade shows the air lens greyed.
- [ ] Definition of done (`.claude/skills/backlog/SKILL.md`).

## Notes
- Stations: data.stadt-zuerich.ch dataset `ugz_luftschadstoffmessung_stundenwerte` (CC0; yearly CSVs `ugz_ogd_air_h1_<year>.csv`, all years as `ugz_ogd_air_h1.parquet`). Station coordinates: from the city's metadata if it states them; else the station's address geocoded through our own address index. Never guessed.
- Model: STAC collections `ch.bafu.luftreinhaltung-stickstoffdioxid`, `-feinstaub_pm10`, `-feinstaub_pm2_5` on data.geo.admin.ch, items `..._<year>`, one COG in LV95 each. Check geo.admin's terms (STAC says "proprietary") before publishing.
- Belgrade's version for reference: `cities/belgrade/pipeline/build_air.py`, `PLACE_CARDS.air` in `web/places.js`.

## Log
- 2026-10-29: item written while preparing the public repo.
