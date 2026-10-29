# Project brief for Claude sessions

**bg** is a map of Belgrade from open data (C-23). The same app draws the City
of Zürich as the **reference**: a fuller map of the same features where the
sources exist, refreshed rarely. Work goes to Belgrade first; Zürich changes
only when the shared app needs it. Layout and rebuild steps are in
[README.md](README.md), how people work here in [CONTRIBUTING.md](CONTRIBUTING.md);
this is the "why" and the gotchas.

## Start here

| Need | Look at |
|---|---|
| What to work on | `backlog/` (the owner picks); how: skill `backlog` |
| What was decided and must not be undone silently | [`docs/decisions.md`](docs/decisions.md) |
| Changing the map / colours / cards / controls | skill `map-style` |
| A city's data, a refresh, a new city | skill `city-data`, command `/refresh-city` |
| Proving the site works (headless) | skill `verify-site`, `node scripts/check.cjs <url>` |
| PRs, CI, previews, merging | skill `steward`; commands `/preview-link`, `/deploy-check` |
| Sources and licences | [`NOTICE.md`](NOTICE.md) |

Each session starts with no memory: put what you learn into the backlog item,
this file, a skill or `docs/decisions.md`, in the same PR.

## Rules

- **Public.** The repo and the map are public: only open data and code go in.
  No personal data, no secrets. `scripts/build.sh` copies only its listed files
  into `dist/` and refuses private-looking ones (`leads*`, `requirements.yaml`,
  `*.env`, CAD files).
- **One app, one config per city (C-02).** Anything that differs by city goes
  into `cities/<id>/city.js` (`CITY`), never into an `if (city === ...)` in `web/`.
- **Same colouring everywhere, gaps said out loud (C-01).** Year built is the
  default lens in every city. A lens, place layer, card block or walk kind a city
  has no data for stays visible but greyed, with the reason ("nicht verfügbar für
  Belgrad"): `CITY.coverage`, read through `lensCoverage()`, `coverageOf()`,
  `cardUnavailable()` in `web/layers.js`. Never hide it.
- **Only what a source states (C-05).** No guessed years, no name patterns, no
  nearest-neighbour joins. Estimates wear "≈".
- **Every string in each of the city's languages (C-03).** Zürich: de / en.
  Belgrade: sr (Latin) / en. Serbian comes from a label's `sr`, else `SR_TEXT`
  (`web/i18n_sr.js`) keyed by the English text, else the English.
- **Tiles under a versioned URL** (`build.sh` appends `?v=<sha>`): keep the
  source URL in `web/map.js` literally `cadastre.pmtiles"`. A browser holding
  byte ranges of an older archive under the same URL mixes them with the new
  one and draws no vector layers at all.
- **City pages need the trailing slash** (`<base href="web/">` is relative);
  the page redirects `/belgrade` to `/belgrade/` itself.

## Known-fixed bugs, so nobody re-introduces them

- **PMTiles needs HTTP Range.** Python's stock `http.server` doesn't answer
  Range requests: serve locally with `python3 scripts/serve.py`. Cloudflare
  Pages didn't honour Range either (200 with the whole file instead of 206);
  that's why the site is on Vercel.
- **Vercel's deployment protection** puts every `*.vercel.app` URL behind a
  login wall unless it's switched off for the project. If the site redirects
  to `vercel.com/login`, switch it off in the project settings, don't work
  around it in code.
- **A custom URL that stops following `main`.** `vercel alias set` is a
  one-time pointer to one deployment; a project **Domain** follows the latest
  production deployment. Use a Domain.
- **Rivers are mostly lines.** swissTLM3D and OSM give most rivers as
  LineStrings; the water source needs a `line` layer next to the `fill`.
- **Buildings at random zooms.** `--drop-densest-as-needed` kept a random share
  of buildings below z14. Build tiles with `shared/build_tiles.sh` only (C-11).
- **A layer switched on while tiles load stayed hidden**: `apply()` was skipped
  while `isStyleLoaded()` is false; `update()` now applies on the next `idle`.
- **The page scrolled away under a pinned card**: MapLibre focused the popup
  before it was placed. Pinned cards open with `focusAfterOpen: false`.
- **Text traced as buildings (Zürich).** The raster fallback tier once traced
  street labels ("ZÜRICH") as buildings; shape heuristics can't tell a bold
  letter from a small building. That tier only joins by EGID now.

## Zürich specifics

- Area: the City of Zürich (BFS 261), its 12 Kreise as inner borders
  (`cities/zurich/config/area.yaml`, `build_kreise.py`).
- Data from the Swiss sources (C-19): `bash cities/zurich/pipeline/refresh.sh`
  runs the scripts in `pipeline/swiss/` into `data/work/` (gitignored), then
  `assemble.py`, the tiles and the tables. The federal building register (GWR),
  the cadastral survey (outlines by EGID; plots by EGRID), swissTLM3D (roads,
  rail, water), BAFU noise, the solar-roof dataset, the canton's WFS (zoning,
  hazards, runoff, noise sensitivity, contaminated sites, hospital lists), the
  city's registers, OSM via overpass.osm.ch, and the Swiss GTFS timetable
  (profiles to Zürich HB).
- Building outlines are a four-tier fallback (`geometry_type`: cadastral survey,
  solar-roof outline, raster trace, placeholder square); underground ones are
  faint and never extruded.
- The relief is swisstopo's own tiles (WMTS), at 25 %.
- Not available yet: air quality (backlog 001).

## Belgrade specifics

- Area: the settlement Beograd (Overture locality), 10 urban municipalities as
  inner borders. Buildings from Overture (OSM + Microsoft ML outlines),
  addresses from RGZ via Overture, places from Overture / OSM taxonomy
  (`PLACES` in `build_layers.py`, confidence >= 0.6).
- Housing is OSM's `building` tag; unknown use (`yes`) counts as housing.
- Transit: the city + suburban GTFS of the Sekretarijat za javni prevoz
  (data.gov.rs; `build_transit.py`): 2,061 stops with a profile card to
  Trg Republike (stops within 400 m of the square walk there). Property names
  stay Zürich's (`hb_mean`, `commute_hb_min`, `n_hb`): "hb" is the city's
  commute target; its labels come from `CITY.strings` / `CITY.lenses`. BG Voz
  (city rail) is left out: its data.gov.rs CSVs are from 2020 and have only
  the first stop's departure times.
- Walks: `shared/pipeline/walk.py belgrade` (after `build_transit.py`, before
  the tiles) over OSM roads and paths. No Kita and no emergency stations:
  `walk_kita` / `walk_er` are NONE in the coverage (greyed in the lens, the
  profile and the card). The places are Overture's, thinner than OSM's POIs
  (~170 pharmacies), so "nearest" means nearest known.
- Air quality: `build_air.py` (before `walk.py`: the stations go into
  places_index.json) writes `places_air.geojson`, the 24 monitoring stations
  in the area (SEPA's state network and the city's GZZJZ network) from SEPA's
  HVD API at opendata.kosava.cloud: the mean of the last 30 days' hourly
  values (preliminary, unverified) per pollutant, plus the 2024 annual means
  of SEPA's verified daily values (data.gov.rs xlsx, 5 stations; its columns
  join the API's stations by SEPA's own station name). The card shows the EU
  limits and WHO guidelines for reference, never a verdict: a 30-day mean
  isn't an annual one. The 30-day window ages: re-run `build_air.py --refresh`
  with every data refresh. Zürich's map has the layer greyed (no source wired
  in yet; NABEL / OSTLUFT could fill it).
- Run order: `fetch_overture.py`, `build_layers.py`, `build_relief.py`,
  `build_transit.py`, `build_air.py`, `shared/pipeline/walk.py belgrade`,
  `shared/build_tiles.sh belgrade`, `profile_table.py` / `address_index.py`.
- Not available yet: year built, noise, zoning, hazards, plots, solar;
  floors for ~13 % of buildings. Census dwellings by period built are on
  stat.gov.rs (answers 403 here).
