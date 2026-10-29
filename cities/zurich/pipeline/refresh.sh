#!/usr/bin/env bash
# Refreshes the City of Zürich's data from the Swiss sources, in order
# (pipeline/swiss/: the Swiss fetch scripts, area = cities/zurich/config/area.yaml),
# into cities/zurich/data/work/ (gitignored, caches kept), then assembles the
# city's layers, builds the tiles and the tables.
#   bash cities/zurich/pipeline/refresh.sh [--from STEP]
# Steps can be resumed with --from <step name> (see STEPS below).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
P=cities/zurich/pipeline/swiss
W=cities/zurich/data/work
mkdir -p "$W"
STEPS=(municipalities kreise elevation gwr outlines props av solar roads water green clip rivers parcels ground transit places timetable walk sources assemble tiles tables)
from=${2:-${STEPS[0]}}; [ "${1:-}" = "--from" ] || from=${STEPS[0]}
run=0
for s in "${STEPS[@]}"; do
  [ "$s" = "$from" ] && run=1
  [ $run = 1 ] || continue
  echo "== $s ($(date +%H:%M:%S)) =="
  case $s in
    municipalities) python3 $P/build_municipalities.py ;;
    kreise)         python3 $P/build_kreise.py ;;
    elevation)      python3 $P/build_elevation.py ;;           # swissALTI3D -> each building's height above sea level
    # the buildings: GWR -> solar-roof / raster outlines -> properties -> cadastral survey outlines -> solar values
    gwr)            python3 $P/build_full_buildings.py
                    cp $W/building_polygons_baujahr.geojson $W/building_polygons_baujahr.square_approx.geojson.bak ;;
    outlines)       python3 $P/build_roof_footprints.py ;;
    props)          python3 $P/enrich_building_properties.py ;;
    av)             python3 $P/build_av_footprints.py ;;
    solar)          python3 $P/enrich_building_properties.py --solar-only ;;
    roads)          python3 $P/build_roads_rail.py && python3 $P/build_rail_structures.py ;;
    water)          python3 $P/build_water_greenery.py ;;
    clip)           python3 $P/clip_to_area.py ;;
    rivers)         python3 $P/build_river_areas.py ;;
    green)          python3 $P/build_green_areas.py ;;
    parcels)        python3 $P/build_parcels.py ;;
    ground)         python3 $P/build_ground_themes.py ;;
    transit)        python3 $P/build_transit.py ;;
    places)         python3 $P/build_places.py ;;
    timetable)      python3 $P/build_timetable.py ;;
    walk)           python3 $P/build_walk.py ;;
    sources)        python3 cities/zurich/pipeline/card_sources.py ;;
    assemble)       python3 cities/zurich/pipeline/assemble.py ;;
    tiles)          bash shared/build_tiles.sh zurich ;;
    tables)         python3 shared/pipeline/profile_table.py zurich && python3 shared/pipeline/address_index.py zurich ;;
  esac
done
