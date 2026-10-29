#!/usr/bin/env bash
# Builds cities/<city>/data/layers/cadastre.pmtiles from the city's GeoJSON
# layers, in separate passes joined by tile-join (C-11: buildings complete from z13):
#   buildings.geojson                buildings, z13 (no underground / < 40 m2) + z14, never thinned
#   roads_rail, water, greenery,     base, z0-z14, thinned at low zooms;
#   municipalities, borders .geojson roads / rail and water get z14 with tile ids
#   parcels.geojson                  optional, z14
#   places_<layer>.geojson,          places, z10-z14, never thinned
#   stops.geojson                    (optional; the source-layer "stops")
#   ground_<layer>.geojson           optional area themes, z10-z14
# Usage: bash shared/build_tiles.sh <city>      (needs tippecanoe + tile-join >= 2.17)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
CITY=${1:?usage: build_tiles.sh <city>}
L=cities/$CITY/data/layers
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
X=(-x solar_match -x zone_name -x zone_zh)

tippecanoe -o "$TMP/b13.pmtiles" -Z13 -z13 --no-feature-limit --no-tile-size-limit --force -q \
  -j '{"buildings": ["all", ["!=", "underground", true], [">=", "area_m2", 40]]}' "${X[@]}" -L buildings:$L/buildings.geojson
tippecanoe -o "$TMP/b14.pmtiles" -Z14 -z14 --no-feature-limit --no-tile-size-limit --force -q "${X[@]}" -L buildings:$L/buildings.geojson
tippecanoe -o "$TMP/base.pmtiles" -Z0 -z14 --drop-densest-as-needed --extend-zooms-if-still-dropping --force -q \
  -j '{"roads_rail": ["<=", "$zoom", 13], "water": ["<=", "$zoom", 13]}' \
  -L roads_rail:$L/roads_rail.geojson -L water:$L/water.geojson -L greenery:$L/greenery.geojson \
  -L municipalities:$L/municipalities.geojson -L borders:$L/borders.geojson
tippecanoe -o "$TMP/lines14.pmtiles" -Z14 -z14 --no-feature-limit --no-tile-size-limit --force -q --generate-ids \
  -L roads_rail:$L/roads_rail.geojson -L water:$L/water.geojson
PARTS=("$TMP/b13.pmtiles" "$TMP/b14.pmtiles" "$TMP/base.pmtiles" "$TMP/lines14.pmtiles")
if [ -f $L/parcels.geojson ]; then
  tippecanoe -o "$TMP/parcels.pmtiles" -Z14 -z14 --no-feature-limit --no-tile-size-limit --force -q -x egrid -x bfs -x source -L parcels:$L/parcels.geojson
  PARTS+=("$TMP/parcels.pmtiles")
fi
PL=()
[ -f $L/stops.geojson ] && PL+=(-L stops:$L/stops.geojson)
for f in $L/places_*.geojson; do [ -f "$f" ] || continue; n=$(basename "$f" .geojson); PL+=(-L "${n#places_}:$f"); done
if [ ${#PL[@]} -gt 0 ]; then
  tippecanoe -o "$TMP/places.pmtiles" -Z10 -z14 -r1 --no-feature-limit --no-tile-size-limit --force -q -x bfs "${PL[@]}"
  PARTS+=("$TMP/places.pmtiles")
fi
GR=()
for f in $L/ground_*.geojson; do [ -f "$f" ] || continue; n=$(basename "$f" .geojson); GR+=(-L "${n#ground_}:$f"); done
if [ ${#GR[@]} -gt 0 ]; then
  tippecanoe -o "$TMP/ground.pmtiles" -Z10 -z14 --no-feature-limit --no-tile-size-limit --no-tiny-polygon-reduction --force -q \
    -x name -x zh -x nr -x process -x upgraded -x limit -x site -x register -x approx \
    -j '{"runoff": ["!=", "depth", "d0"]}' "${GR[@]}"
  PARTS+=("$TMP/ground.pmtiles")
fi
tile-join -o $L/cadastre.pmtiles --force --no-tile-size-limit -q "${PARTS[@]}"
ls -l $L/cadastre.pmtiles
