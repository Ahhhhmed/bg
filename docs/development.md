# Development

How the repo is laid out, how to build the site and how to refresh a city's
data. How people work here (with Claude) is in [CONTRIBUTING.md](../CONTRIBUTING.md);
the rules and gotchas Claude follows are in [CLAUDE.md](../CLAUDE.md).

## Setup

```
bash setup.sh                 # tippecanoe, GDAL, Python packages (.venv)
bash scripts/build.sh         # the site -> dist/ (from the committed tiles and tables)
python3 scripts/serve.py 8750 dist
node scripts/check.cjs http://localhost:8750
```

The committed tiles and tables are enough to build and deploy the site; the
pipelines below are only needed to refresh a city's data. Deployed on Vercel
(`vercel.json`: `bash scripts/build.sh`, output `dist/`); every branch gets a
preview (`bash scripts/preview_url.sh`). Production: https://bg-gules-iota.vercel.app/

## Layout

```
cities/<id>/city.js          the city: name, languages, centre, relief, credits,
                             coverage (what's missing and why), labels
cities/<id>/pipeline/        the city's data scripts (sources differ per city)
cities/<id>/data/            built outputs: tiles, tables, stop profiles (committed)
cities/<id>/data/layers/     GeoJSON layers (gitignored) + cadastre.pmtiles, relief
cities/<id>/data/src/        downloads (gitignored)
cities/zurich/config/        the area (BFS 261) and the hospital sites
cities/zurich/data/work/     the Swiss scripts' outputs and caches (gitignored)
shared/build_tiles.sh <id>   GeoJSON layers -> cadastre.pmtiles (tippecanoe)
shared/pipeline/             profile_table.py, address_index.py (take the city id)
web/                         the map app, one copy for every city
scripts/build.sh [out]       the public site -> dist/ (only listed files go out)
scripts/check.cjs <url>      headless check of the start page and both cities
scripts/check_*_colours.py   the colour rules (years, lenses, ground tints)
backlog/                     open work, one file per item (scripts/backlog.py)
docs/decisions.md            what was decided and must not be undone silently
.claude/                     skills and commands for Claude sessions
```

## Rebuild a city

Zürich (the Swiss sources; hours on a fresh run, caches kept in `data/work/`):

```
bash cities/zurich/pipeline/refresh.sh            # all steps, or --from <step>
```

Belgrade:

```
python3 cities/belgrade/pipeline/fetch_overture.py    # Overture release, ~5 min
python3 cities/belgrade/pipeline/build_layers.py
python3 cities/belgrade/pipeline/build_relief.py      # Copernicus DEM
python3 cities/belgrade/pipeline/build_transit.py     # GTFS -> stops, stop cards (~3 min)
python3 cities/belgrade/pipeline/build_air.py --refresh   # SEPA stations, last 30 days + verified 2024
python3 shared/pipeline/walk.py belgrade              # walks + commute per building
bash shared/build_tiles.sh belgrade
python3 shared/pipeline/profile_table.py belgrade && python3 shared/pipeline/address_index.py belgrade
```

Then `bash scripts/build.sh`, serve `dist/` with a server that honours HTTP
Range (PMTiles needs it; `python3 scripts/serve.py 8750 dist`), and
`node scripts/check.cjs http://localhost:8750`.


Data sources and licences: [NOTICE.md](../NOTICE.md).
