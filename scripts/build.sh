#!/usr/bin/env bash
# Builds the public site into $OUT (default dist/):
#   index.html                 Belgrade's map (the start page)
#   <city>/index.html          the city's map (web/index.html with <base href="web/">)
#   <city>/web/                the map app + the city's city.js
#   <city>/data/               the city's tiles, tables and stop profiles
# Only files on the lists below go out (privacy guard: the repo and the site are
# public; nothing private-looking may be in the tree, nothing may point outside it).
# Usage: bash scripts/build.sh [out dir]
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
OUT=${1:-dist}
CITIES=(zurich belgrade)

# --- privacy guard: this folder never holds personal data, and never reads outside itself ---
bad=$(find . -path ./dist -prune -o \( -iname 'leads*' -o -iname 'requirements.yaml' -o -iname '*.FCStd' -o -iname '*.env' \) -print)
[ -z "$bad" ] || { echo "ERROR: private-looking files in the repo: $bad" >&2; exit 1; }
if grep -rnE '\.\./\.\./(data/leads|config/)' web cities shared scripts --include=*.js --include=*.py --include=*.sh --exclude=build.sh >/dev/null; then
  echo "ERROR: code points at files outside the repo (a parent's data/leads or config/)" >&2; exit 1
fi

rm -rf "$OUT"; mkdir -p "$OUT"
WEB=(index.html map.js i18n.js i18n_sr.js years.js area.js relief.js layers.js profile.js controls.js freshness.js stops.js places.js nearby.js search.js style.css theme.css controls.css mark.svg)
DATA=(card_sources.json places_sources.json places_index.json profile_table.json address_index.json)
LAYERS=(area_labels.json relief.png)
for c in "${CITIES[@]}"; do
  C=cities/$c; D=$OUT/$c
  mkdir -p "$D/web" "$D/data/layers"
  for f in "${WEB[@]}"; do cp "web/$f" "$D/web/"; done
  cp "$C/city.js" "$D/web/city.js"
  for f in "${DATA[@]}"; do [ -f "$C/data/$f" ] && cp "$C/data/$f" "$D/data/"; done
  # the address search's file holds public register fields only (C-18): address, postcode, id, position
  python3 -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d['cols']==['address','plz','egid','lon','lat'] and all(len(r)==5 for r in d['rows']) else 'ERROR: '+sys.argv[1]+' has other columns than address, plz, egid, lon, lat')" "$D/data/address_index.json"
  for f in "${LAYERS[@]}"; do [ -f "$C/data/layers/$f" ] && cp "$C/data/layers/$f" "$D/data/layers/"; done
  [ -d "$C/data/stops" ] && cp -r "$C/data/stops" "$D/data/stops"
  # the tiles under a name that changes with their content (PMTiles reads byte
  # ranges: a browser holding ranges of an older archive must not mix them; CLAUDE.md)
  V=$(sha256sum "$C/data/layers/cadastre.pmtiles" | cut -c1-12)
  cp "$C/data/layers/cadastre.pmtiles" "$D/data/layers/cadastre.pmtiles"
  sed -i "s#cadastre.pmtiles\"#cadastre.pmtiles?v=$V\"#" "$D/web/map.js"
  grep -q "cadastre.pmtiles?v=$V" "$D/web/map.js" || { echo "ERROR: could not version the tiles URL ($c)" >&2; exit 1; }
  # <base> is relative, so the page must be served as <city>/ (with the slash)
  sed 's#<head>#<head>\n  <script>if (!location.pathname.endsWith("/")) location.replace(location.pathname + "/" + location.search + location.hash);</script>\n  <base href="web/">#' "$D/web/index.html" > "$D/index.html"
  echo "  $c: $(du -sh "$D" | cut -f1)"
done
# the start page is Belgrade's map (C-23): / serves it with <base> into belgrade/web/;
# /belgrade/ keeps working, Zürich (the reference) is at /zurich/
sed 's#<head>#<head>\n  <base href="belgrade/web/">#' "$OUT/belgrade/web/index.html" > "$OUT/index.html"
grep -q '<base href="belgrade/web/">' "$OUT/index.html" || { echo "ERROR: could not make the start page" >&2; exit 1; }
echo "built $OUT ($(du -sh "$OUT" | cut -f1))"
