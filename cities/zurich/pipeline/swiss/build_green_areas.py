"""
Forest and park polygons (owner 2026-10-17) -> zurich_greenery.geojson.

Replaces the raster-traced greenery (build_greenery_raster.py), which was any
light-green area of swisstopo's map, forests, parks and fields alike, all
typed "forest". Now two separate, official layers:

- **forest** (`type: forest`): the cadastral survey's closed forest, AV land
  cover `ms:LCSF` with `Art = geschlossener_Wald`, from the same open WFS on
  geodienste.ch as the building footprints and river areas; all 13
  municipalities.
- **park** (`type: park`, with `name`): the City of Zürich's public parks,
  from Grün Stadt Zürich's green-space inventory (WFS `gruenflaechen`, product
  `610 Parkanlagen`), merged per park (`pflegeareal`). City of Zürich only:
  the other municipalities publish no such inventory. Parks matter later for
  "distance to the nearest park" (not computed here).

Both are clipped to the area and snapped to ~0.1 m; forest edges are
simplified by ~1 m. Run order: after
clip_to_area.py (see data/work/SOURCES.md); writes the whole file.

  python3 cities/zurich/pipeline/swiss/build_green_areas.py
"""
import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

from shapely import set_precision
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).parent))
from area import area_polygon  # noqa: E402
from build_av_footprints import fetch_av_layer  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LAYERS = ROOT / "data" / "work"
OUT = LAYERS / "zurich_greenery.geojson"
FOREST_CACHE = LAYERS / "_av_forest_cache.json"
PARK_CACHE = LAYERS / "_gsz_gruenflaechen_cache.json"
FOREST_ART = "geschlossener_Wald"
PARK_URL = ("https://www.ogd.stadt-zuerich.ch/wfs/geoportal/Gruenflaechen?SERVICE=WFS&VERSION=1.1.0"
            "&REQUEST=GetFeature&TYPENAME=gruenflaechen&outputFormat=GeoJSON&srsName=EPSG:4326")
PARK_PRODUCT = "610"          # "610 Parkanlagen"
GRID_DEG = 1e-6               # ~0.1 m
CLOSE_DEG = 0.00002           # ~2 m: close the gaps between a park's maintenance units
M2 = 111320.0 * 75500.0       # rough m2 per deg2 at Zürich's latitude (area filter / stats only)
MIN_FOREST_M2 = 200
FOREST_SIMPLIFY_DEG = 1e-5   # ~1 m on forest edges: 0.13 mm at 1:7,500, invisible on screen; cuts the file ~3x
MIN_PARK_M2 = 50


def polygons(geom):
    return [g for g in getattr(geom, "geoms", [geom]) if g.geom_type == "Polygon" and not g.is_empty]


def snapped(geom):
    return set_precision(geom, GRID_DEG)


def forests(area):
    raw = fetch_av_layer("ms:LCSF", [FOREST_ART], FOREST_CACHE)
    merged = unary_union([shape(f["geometry"]).buffer(0) for f in raw]).intersection(area)
    parts = [snapped(p.simplify(FOREST_SIMPLIFY_DEG, preserve_topology=True))
             for p in polygons(merged) if p.area * M2 >= MIN_FOREST_M2]
    print(f"forest: {len(raw)} AV polygons -> {len(parts)} areas, {sum(p.area for p in parts) * M2 / 1e4:.0f} ha")
    return [{"geometry": p, "properties": {"kind": "greenery", "type": "forest",
                                           "source": f"geodienste.ch AV WFS ms:LCSF Art={FOREST_ART} (live)"}}
            for p in parts if not p.is_empty]


def parks(area):
    if PARK_CACHE.exists():
        data = json.loads(PARK_CACHE.read_text())
    else:
        print("fetching Grün Stadt Zürich green-space inventory (~100 MB, ~40 s) ...")
        with urllib.request.urlopen(PARK_URL, timeout=600) as r:
            data = json.loads(r.read())
        # keep only the park units in the cache
        data = {"features": [f for f in data["features"]
                             if str(f["properties"].get("produkt", "")).startswith(PARK_PRODUCT)]}
        PARK_CACHE.write_text(json.dumps(data))
    by_park = defaultdict(list)
    for f in data["features"]:
        if f.get("geometry") and str(f["properties"].get("produkt", "")).startswith(PARK_PRODUCT):
            by_park[f["properties"].get("pflegeareal") or "?"].append(shape(f["geometry"]).buffer(0))
    out = []
    for name, geoms in sorted(by_park.items()):
        g = unary_union(geoms).buffer(CLOSE_DEG).buffer(-CLOSE_DEG).intersection(area)
        for p in polygons(g):
            if p.area * M2 >= MIN_PARK_M2:
                out.append({"geometry": snapped(p), "properties": {
                    "kind": "greenery", "type": "park", "name": name,
                    "source": "Stadt Zürich OGD, Grün Stadt Zürich gruenflaechen (610 Parkanlagen)"}})
    out = [f for f in out if not f["geometry"].is_empty]
    print(f"parks: {len(by_park)} named parks -> {len(out)} polygons, "
          f"{sum(f['geometry'].area for f in out) * M2 / 1e4:.0f} ha")
    return out


def main():
    area = area_polygon()
    feats = forests(area) + parks(area)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": mapping(f["geometry"]), "properties": f["properties"]} for f in feats]}))
    print(f"{OUT.name}: {len(feats)} features, {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
