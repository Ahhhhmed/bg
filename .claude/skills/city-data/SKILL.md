---
name: city-data
description: Refreshing or extending a city's data -- Zürich's Swiss pipeline (refresh.sh), Belgrade's Overture / GTFS / SEPA pipeline, the shared tiles, walking distances, profile table and address index -- and adding a new city. Use for any change under cities/ or shared/, a data refresh, a new source, or "add city X".
---

# City data

Every city writes the **same layers and building properties** into
`cities/<id>/data/layers/` (GeoJSON, gitignored) and `cities/<id>/data/` (committed tables),
so the shared steps and the one web app work for all of them:

| File | What |
|---|---|
| `buildings.geojson` | one feature per building: `egid` (a numeric id), `address`, `municipality`, the facts the lenses read |
| `roads_rail`, `water`, `greenery`, `municipalities`, `borders` | the base map; roads carry swissTLM3D's `objektart` codes (Belgrade maps OSM classes onto them) |
| `places_<layer>.geojson` | points: `pid`, `kind` (the icon), `name`, `srcs`, ... |
| `stops.geojson` + `data/stops/<nr>.json` | stops and their profile cards to the city's target |
| `ground_<theme>.geojson` | optional area themes |
| `data/card_sources.json`, `places_sources.json`, `places_index.json`, `profile_table.json`, `address_index.json` | the cards' sources, the place index, the profile counts, the address search |

Then, per city: `bash shared/build_tiles.sh <id>` -> `data/layers/cadastre.pmtiles`,
`python3 shared/pipeline/profile_table.py <id>`, `python3 shared/pipeline/address_index.py <id>`.

## Zürich (`cities/zurich/`)
- `bash cities/zurich/pipeline/refresh.sh [--from STEP]`: the Swiss fetch scripts in
  `pipeline/swiss/`, area = `config/area.yaml` (BFS 261), into `data/work/` (gitignored, with
  the download caches), then `assemble.py` (the shared names), the tiles and the tables. Hours
  on a fresh run (the building register and the cadastral survey come tile by tile).
- `pipeline/swiss/` keeps the original script names; `area.py` reads the config, everything
  writes to `data/work/`. `config/hospital_sites.yaml` places the canton's hospital lists at
  their buildings (a list entry without a site stops the build).
- Building outlines are a four-tier fallback (`geometry_type`): cadastral survey (by EGID),
  solar-roof outline, raster trace, placeholder square. Matching is by EGID or strict
  point-in-polygon, never nearest neighbour.

## Belgrade (`cities/belgrade/`)
`fetch_overture.py`, `build_layers.py`, `build_relief.py`, `build_transit.py`, `build_air.py`,
then `shared/pipeline/walk.py belgrade`, the tiles and the tables. Details in `CLAUDE.md`.

## Rules
- **Only what a source states (C-05).** Joins by shared identifiers or containment only.
- **Every source in the card tables and `NOTICE.md`**, with its licence and date.
- **Never commit `data/src/` or `data/work/`** (downloads); commit the tiles and tables.
- A step that rewrites the buildings is followed by the walk step, the tiles and the tables.

## A new city
1. `cities/<id>/city.js` (copy one, fill every field; `coverage` lists what it lacks).
2. A pipeline that writes the files above.
3. Add `<id>` to `CITIES` in `scripts/build.sh` and `scripts/check.cjs` (a test address),
   and to the other cities' `others` (and its own `others`, `home`).
