"""
Clip every map layer to the area (the municipalities in config/area.yaml).

Run after the fetch scripts and build_municipalities.py, before tippecanoe.
Rewrites, in place:
  building_polygons_baujahr.geojson  keep buildings registered (GWR) in one of
                                     the municipalities; by position if unset
  zurich_roads_rail.geojson          lines cut at the area border
  zurich_greenery.geojson            polygons cut at the area border
  zurich_water.geojson               rivers / small waters cut at the area
                                     border; Lake Zurich itself is kept whole
                                     (down to the Obersee): municipal borders
                                     run through the lake, and cutting it to
                                     the area's bbox left a straight edge at
                                     Stäfa on the map and the sheets
and writes
  area_borders.geojson  municipality and Zürich Kreis border lines (lake cut
                        out), the `borders` tile layer
  area_labels.json      the area's bbox (the map opens fitted to it) and
                        label points; the map loads it directly, so it's
                        deployed
Kreise come from kreise.geojson (build_kreise.py) when it exists.

Prints counts before/after per layer and buildings per municipality.
Idempotent: clipping already-clipped data changes nothing.
"""
import collections
import json
import sys
from pathlib import Path

from shapely.geometry import MultiLineString, mapping, shape
from shapely.ops import unary_union
from shapely.prepared import prep

sys.path.insert(0, str(Path(__file__).parent))
from area import area_polygon, municipality_features

LAYERS = Path(__file__).resolve().parents[2] / "data" / "work"
BUILDINGS = LAYERS / "building_polygons_baujahr.geojson"
ROADS = LAYERS / "zurich_roads_rail.geojson"
GREENERY = LAYERS / "zurich_greenery.geojson"
WATER = LAYERS / "zurich_water.geojson"
LABELS = LAYERS / "area_labels.json"
KREISE = LAYERS / "kreise.geojson"
BORDERS = LAYERS / "area_borders.geojson"
LAKE_BORDER_BUFFER_DEG = 0.0001  # ~10 m: keeps borders from running along the shoreline

LAKE_GWL_NR = "CH0090500000"  # Zürichsee in swissTLM3D


def load(path):
    return json.loads(path.read_text())


def save(path, fc):
    path.write_text(json.dumps(fc))


def clip_features(features, region, region_prepared, keep_whole=lambda f: False, whole_region=None):
    out = []
    for f in features:
        if not f.get("geometry"):
            continue
        g = shape(f["geometry"])
        if keep_whole(f):
            if whole_region is None:         # kept as fetched
                out.append(f)
                continue
            target, target_p = whole_region, prep(whole_region.buffer(1e-7))
        else:
            target, target_p = region, region_prepared
        if target_p is not None and target_p.contains(g):
            out.append(f)
            continue
        if not g.intersects(target):
            continue
        cut = g.intersection(target)
        if cut.is_empty:
            continue
        # keep only the geometry family of the input (drop stray points / lines)
        family = g.geom_type.replace("Multi", "")
        parts = [q for p in getattr(cut, "geoms", [cut]) for q in getattr(p, "geoms", [p]) if q.geom_type == family]
        if not parts:
            continue
        if family == "Polygon":
            merged = unary_union(parts)
        elif len(parts) == 1:
            merged = parts[0]
        else:
            merged = MultiLineString(parts)
        out.append({**f, "geometry": mapping(merged)})
    return out


def main():
    area = area_polygon()
    # contains-test against a hair-wider area, so features already cut to the
    # border count as inside and a re-run doesn't re-cut (and shift) them
    area_p = prep(area.buffer(1e-7))

    # buildings: whole buildings, chosen by representative point
    fc = load(BUILDINGS)
    before = collections.Counter(f["properties"].get("municipality") for f in fc["features"])
    # The building register's municipality is authoritative (it keeps the few
    # garages that straddle a border by a metre or two); the position decides
    # only when a building has no municipality.
    names = {f["properties"]["name"] for f in municipality_features()}
    kept = [
        f for f in fc["features"]
        if f["properties"].get("municipality") in names
        or (not f["properties"].get("municipality") and area_p.contains(shape(f["geometry"]).representative_point()))
    ]
    after = collections.Counter(f["properties"].get("municipality") for f in kept)
    print(f"buildings: {len(fc['features'])} -> {len(kept)}")
    for name in sorted(set(before) | set(after), key=lambda n: -before.get(n, 0)):
        print(f"  {name or '(none)':<26} {before.get(name, 0):6d} -> {after.get(name, 0):6d}")
    fc["features"] = kept
    save(BUILDINGS, fc)

    for path, label, kw in [
        (ROADS, "roads/rail", {}),
        (GREENERY, "greenery", {}),
        (WATER, "water", {"keep_whole": lambda f: f["properties"].get("gwl_nr") == LAKE_GWL_NR}),
    ]:
        fc = load(path)
        n0 = len(fc["features"])
        fc["features"] = clip_features(fc["features"], area, area_p, **kw)
        print(f"{label}: {n0} -> {len(fc['features'])}")
        save(path, fc)

    water = load(WATER)["features"]
    lake = unary_union([shape(f["geometry"]) for f in water if f["properties"].get("gwl_nr") == LAKE_GWL_NR])
    write_borders_and_labels(area, lake)


def _land_parts(geom, lake):
    land = geom.difference(lake)
    return sorted(getattr(land, "geoms", [land]), key=lambda g: -g.area)


def write_borders_and_labels(area, lake):
    """Border lines for the map, with the lake cut out.

    Some municipal polygons include their share of the lake and some stop at
    the shore, so their raw outlines both cross the lake and trace the
    shoreline -- neither is a border anyone looks for. Lines are the polygon
    outlines minus a slightly buffered lake; labels sit on each unit's
    largest land part.
    """
    lake_buf = lake.buffer(LAKE_BORDER_BUFFER_DEG)
    units = [(f, "municipality") for f in municipality_features()]
    if KREISE.exists():
        units += [(f, "kreis") for f in load(KREISE)["features"]]
    else:
        print(f"  ({KREISE.name} not found -- Kreis borders and labels skipped; run build_kreise.py)")
    # Kreis lines: only the internal ones -- the city's outer edge is already
    # drawn as a municipality border
    city_edge = unary_union([shape(f["geometry"]).boundary for f, lvl in units if lvl == "municipality"])
    city_edge_buf = city_edge.buffer(LAKE_BORDER_BUFFER_DEG / 2)
    borders, labels = [], []
    for f, level in units:
        g = shape(f["geometry"])
        name = f["properties"]["name"].replace(" (ZH)", "")
        line = g.boundary.difference(lake_buf)
        if level == "kreis":
            line = line.difference(city_edge_buf)
        if not line.is_empty:
            borders.append({"type": "Feature", "geometry": mapping(line),
                            "properties": {"name": name, "level": level}})
        pt = _land_parts(g, lake)[0].representative_point()
        labels.append({"name": name, "level": level, "lon": round(pt.x, 5), "lat": round(pt.y, 5)})
    save(BORDERS, {"type": "FeatureCollection", "features": borders})
    print(f"wrote {len(borders)} border lines -> {BORDERS}")
    out = {"bbox": [round(v, 5) for v in area.bounds], "labels": labels}
    LABELS.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"wrote {len(labels)} labels + area bbox -> {LABELS}")


if __name__ == "__main__":
    main()
