"""
River water areas: adds the cadastral survey's flowing-water
polygons (AV land cover `ms:LCSF`, `Art = Gewaesser_fliessendes`) to
data/work/zurich_water.geojson, so the Limmat, Sihl and other wide rivers
are drawn as water areas, not only as swissTLM3D centrelines. In central
Zürich the Limmat is 40-60 m wide but swissTLM3D has only its centreline.

Same open WFS as the building footprints (build_av_footprints.py, geodienste.ch),
same tiling and cache convention. Run after build_water_greenery.py and
clip_to_area.py (see data/work/SOURCES.md); re-running replaces the previous
river areas (features with `type: river_area`) instead of adding duplicates.

  python3 cities/zurich/pipeline/swiss/build_river_areas.py
"""
import json
import sys
from pathlib import Path

from shapely import set_precision
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).parent))
from area import area_polygon  # noqa: E402
from build_av_footprints import fetch_av_layer  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LAYERS = ROOT / "data" / "work"
WATER = LAYERS / "zurich_water.geojson"
CACHE = LAYERS / "_av_rivers_cache.json"
ART = "Gewaesser_fliessendes"
SOURCE = f"geodienste.ch AV WFS ms:LCSF Art={ART} (live)"
MIN_AREA_M2 = 20  # drop slivers left by clipping
GRID_DEG = 1e-6   # snap to ~0.1 m: the survey's mm precision only bloats the GeoJSON (tiles keep ~0.4 m)


def main():
    raw = fetch_av_layer("ms:LCSF", [ART], CACHE)
    print(f"{len(raw)} flowing-water polygons from the cadastral survey")
    area = area_polygon()
    merged = unary_union([shape(f["geometry"]).buffer(0) for f in raw]).intersection(area)
    parts = list(getattr(merged, "geoms", [merged]))
    # rough m2 from degrees at Zürich's latitude, only to drop slivers
    m2 = 111320.0 * 75500.0
    parts = [set_precision(p, GRID_DEG) for p in parts if p.geom_type == "Polygon" and p.area * m2 >= MIN_AREA_M2]
    parts = [p for p in parts if not p.is_empty and p.geom_type == "Polygon"]

    water = json.loads(WATER.read_text())
    before = len(water["features"])
    kept = [f for f in water["features"] if f["properties"].get("type") != "river_area"]
    for p in parts:
        kept.append({
            "type": "Feature",
            "geometry": mapping(p),
            "properties": {"kind": "water", "type": "river_area", "source": SOURCE},
        })
    water["features"] = kept
    WATER.write_text(json.dumps(water))
    total_ha = sum(p.area for p in parts) * m2 / 1e4
    print(f"zurich_water.geojson: {before} -> {len(kept)} features "
          f"({len(parts)} river areas, {total_ha:.1f} ha)")


if __name__ == "__main__":
    main()
