#!/usr/bin/env python3
"""Belgrade's map layers from the Overture extract (fetch_overture.py), in the
shapes the map's style and cards read (the same layer and property names as
Zürich's: one building schema for every city, see the city-data skill).

The area is the settlement of Belgrade (Overture division "Београд", 389 km2),
its inner borders the parts of the 10 urban municipalities in it (they cover it
exactly), like the City of Zürich and its 12 Kreise.

    python3 cities/belgrade/pipeline/build_layers.py

Writes cities/belgrade/data/layers/*.geojson (gitignored), area_labels.json,
and the source tables data/card_sources.json, data/places_sources.json,
data/places_index.json.

Only what a source states (C-05): no year built (no open register; OSM's
start_date isn't in Overture), floors / height / use only where OSM has them.
A building's `housing` is 1 for OSM's residential building types, 0 for the
other known types, absent where OSM says only "building" (unknown use).
"""
import hashlib
import json
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq
from pyproj import Geod
from shapely import wkb
from shapely.geometry import mapping, Point
from shapely.ops import unary_union
from shapely.prepared import prep
from shapely.strtree import STRtree

HERE = Path(__file__).resolve().parent
CITY = HERE.parent
SRC = CITY / "data" / "src"
OUT = CITY / "data" / "layers"
DATA = CITY / "data"
GEOD = Geod(ellps="WGS84")
AREA = "Београд"
PARTS = ["Стари град", "Савски венац", "Врачар", "Палилула", "Звездара", "Вождовац", "Чукарица", "Раковица", "Нови Београд", "Земун"]
# OSM building types that hold homes (Overture `class`); every other known type is "no housing"
HOUSING = {"house", "apartments", "residential", "detached", "semidetached_house", "terrace", "bungalow",
           "dormitory", "farm", "houseboat", "static_caravan", "cabin", "hut", "stilt_house", "trullo"}
# Overture road class -> swissTLM3D-like `objektart` (web/layers.js ROAD_CLASS)
ROAD = {"motorway": 1, "trunk": 2, "primary": 4, "secondary": 8, "tertiary": 9, "unclassified": 10, "residential": 10,
        "living_street": 10, "unknown": 10, "service": 11, "pedestrian": 12, "footway": 15, "path": 16, "steps": 15,
        "cycleway": 16, "bridleway": 16, "track": 17}
# Overture place taxonomy -> (place layer, kind); the kinds are the map's icons (web/layers.js PLACE_LAYERS)
PLACES = {
    "preschool": ("schools", "kindergarten"), "day_care_preschool": ("schools", "kindergarten"),
    "child_care_and_day_care": ("schools", "kindergarten"),
    "elementary_school": ("schools", "school"), "middle_school": ("schools", "school"), "school": ("schools", "school"),
    "public_school": ("schools", "school"), "private_school": ("schools", "school"),
    "high_school": ("schools", "upper"), "vocational_and_technical_school": ("schools", "upper"),
    "hospital": ("hospitals", "hospital"),
    "doctors_office": ("health", "doctor"), "health_care": ("health", "doctor"), "pediatric_clinic": ("health", "doctor"),
    "internal_medicine": ("health", "doctor"), "pharmacy": ("health", "pharmacy"),
    "grocery_store": ("shops", "supermarket"), "organic_grocery_store": ("shops", "supermarket"),
    "international_grocery_store": ("shops", "supermarket"), "post_office": ("shops", "post"),
    "swimming_pool": ("baths", "pool"), "beach": ("baths", "lakebath"), "playground": ("playgrounds", "playground"),
}
MIN_CONFIDENCE = 0.6   # Overture's own score that the place exists as described


def read(name, cols=None):
    return pq.read_table(SRC / f"{name}.parquet", columns=cols).to_pylist()


def latin(names):
    """the sr-Latn name if Overture has one, else the primary (often Cyrillic)"""
    if not names:
        return None
    common = dict(names.get("common") or [])
    return common.get("sr-Latn") or names.get("primary")


def area_m2(g):
    return abs(GEOD.geometry_area_perimeter(g)[0])


def dump(name, feats):
    (OUT / name).write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, separators=(",", ":")))
    print(f"  {name}: {len(feats)}")


def feature(geom, props):
    return {"type": "Feature", "properties": {k: v for k, v in props.items() if v is not None}, "geometry": mapping(geom)}


def street_title(s):
    # RGZ writes streets in capitals ("BULEVAR KRALJA ALEKSANDRA")
    return " ".join(w.capitalize() if w.isupper() else w for w in str(s).split()) if s else s


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    release = (SRC / "RELEASE").read_text().strip()
    today = date.today().isoformat()

    # --- the area and its parts ---
    div = read("division_area")
    loc = {(r["names"] or {}).get("primary"): r for r in div if r["subtype"] == "locality"}
    area = wkb.loads(loc[AREA]["geometry"])
    inside = prep(area)
    parts = []
    for n in PARTS:
        g = wkb.loads(loc[n]["geometry"]).intersection(area)
        parts.append((latin(loc[n]["names"]), g))
    part_tree = STRtree([g for _, g in parts])
    part_of = lambda pt: next((parts[i][0] for i in part_tree.query(pt) if parts[i][1].contains(pt)), None)
    dump("municipalities.geojson", [feature(area, {"name": "Beograd", "level": "municipality"})]
         + [feature(g, {"name": n, "level": "kreis"}) for n, g in parts])
    outer = area.boundary
    inner = unary_union([g.boundary for _, g in parts]).difference(outer.buffer(0.0003))
    dump("borders.geojson", [feature(outer, {"name": "Beograd", "level": "municipality"}), feature(inner, {"level": "kreis"})])
    x0, y0, x1, y1 = area.bounds
    labels = [{"name": "Beograd", "level": "municipality", "lon": round(area.representative_point().x, 5), "lat": round(area.representative_point().y, 5)}]
    for n, g in parts:
        p = g.representative_point()
        labels.append({"name": n, "level": "kreis", "lon": round(p.x, 5), "lat": round(p.y, 5)})
    (OUT / "area_labels.json").write_text(json.dumps({"bbox": [round(x0, 5), round(y0, 5), round(x1, 5), round(y1, 5)], "labels": labels}, ensure_ascii=False))

    # --- buildings, with the RGZ address points inside them ---
    rows = sorted(read("building"), key=lambda r: r["id"])
    blds = []
    for r in rows:
        g = wkb.loads(r["geometry"])
        if g.geom_type not in ("Polygon", "MultiPolygon") or not inside.contains(g.representative_point()):
            continue
        blds.append((r, g))
    tree = STRtree([g for _, g in blds])
    addrs = {}
    for a in read("address", ["geometry", "number", "street"]):
        pt = wkb.loads(a["geometry"])
        for i in tree.query(pt):
            if blds[i][1].contains(pt):
                addrs.setdefault(i, []).append(f"{street_title(a['street'])} {a['number']}".strip())
                break
    feats = []
    for i, (r, g) in enumerate(blds):
        src = {s["dataset"] for s in (r["sources"] or [])}
        cls = r["class"]
        a = sorted(set(addrs.get(i, [])))
        feats.append(feature(g, {
            "egid": i + 1,                      # this map's own id (the selection ring, the search); no register id
            "gers": r["id"],                    # Overture's id, stable across its releases
            "address": a[0] if a else None,
            "addresses_more": len(a) - 1 if len(a) > 1 else None,
            "municipality": part_of(g.representative_point()),
            "building_class": cls,
            "housing": (1 if cls in HOUSING else 0) if cls else None,
            "floors": r["num_floors"],
            "height_m": round(r["height"], 1) if r["height"] else None,
            "underground": True if r.get("is_underground") else None,
            "area_m2": round(area_m2(g)),
            "geometry_type": "osm_footprint" if "OpenStreetMap" in src else "ml_footprint",
        }))
    dump("buildings.geojson", feats)

    # --- roads, rail ---
    rr = []
    for r in read("segment"):
        g = wkb.loads(r["geometry"])
        if not inside.intersects(g):
            continue
        flags = set(sum([f["values"] for f in (r["road_flags"] or r["rail_flags"] or [])], []))
        structure = "tunnel" if "is_tunnel" in flags else "bridge" if "is_bridge" in flags else None
        if r["subtype"] == "road":
            rr.append(feature(g, {"kind": "road", "objektart": ROAD.get(r["class"], 10), "structure": structure, "name": latin(r["names"])}))
        elif r["subtype"] == "rail" and not flags & {"is_disused", "is_abandoned"}:
            rr.append(feature(g, {"kind": "rail", "verkehrsmittel": 200 if r["class"] == "tram" else 100, "structure": structure}))
    dump("roads_rail.geojson", rr)

    # --- water, green ---
    water = []
    for r in read("water"):
        g = wkb.loads(r["geometry"])
        if r["subtype"] == "human_made" or not inside.intersects(g):
            continue
        poly = g.geom_type in ("Polygon", "MultiPolygon")
        water.append(feature(g, {"kind": "water", "type": ("river_area" if r["subtype"] in ("river", "canal", "stream") else "lake") if poly else "river",
                                 "name": latin(r["names"])}))
    dump("water.geojson", water)
    green = []
    for r in read("land"):
        if r["subtype"] == "forest":
            g = wkb.loads(r["geometry"])
            if g.geom_type in ("Polygon", "MultiPolygon") and inside.intersects(g):
                green.append(feature(g, {"kind": "greenery", "type": "forest"}))
    for r in read("land_use"):
        if r["subtype"] == "park":
            g = wkb.loads(r["geometry"])
            if g.geom_type in ("Polygon", "MultiPolygon") and inside.intersects(g):
                green.append(feature(g, {"kind": "greenery", "type": "park", "name": latin(r["names"])}))
    dump("greenery.geojson", green)

    # --- places (Overture places, + OSM's playground outlines) ---
    by_layer, index = {}, []
    def add(layer, kind, pt, props):
        pid = hashlib.sha1(f"{layer}|{kind}|{props.get('name')}|{pt.x:.5f}|{pt.y:.5f}".encode()).hexdigest()[:7]
        props = {"kind": kind, "pid": layer[0] + pid, "muni": part_of(pt), **props}
        by_layer.setdefault(layer, []).append(feature(pt, props))
    for r in read("place"):
        tx = (r["taxonomy"] or {}).get("primary")
        if tx not in PLACES or (r["confidence"] or 0) < MIN_CONFIDENCE:
            continue
        pt = wkb.loads(r["geometry"])
        if not inside.contains(pt):
            continue
        layer, kind = PLACES[tx]
        ad = (r.get("addresses") or [{}])[0] or {}
        add(layer, kind, pt, {"name": latin(r["names"]), "srcs": "overture",
                              "addr": ad.get("freeform"), "web": (r.get("websites") or [None])[0], "phone": (r.get("phones") or [None])[0]})
    for r in read("land_use"):
        if r["class"] == "playground":
            g = wkb.loads(r["geometry"])
            pt = g.representative_point() if g.geom_type != "Point" else g
            if inside.contains(pt):
                add("playgrounds", "playground", pt, {"name": latin(r["names"]), "srcs": "osm",
                                                       "area_m2": round(area_m2(g)) if g.geom_type != "Point" else None})
    for layer, fs in sorted(by_layer.items()):
        dump(f"places_{layer}.geojson", fs)
        for f in fs:
            p = f["properties"]
            x, y = f["geometry"]["coordinates"]
            index.append([p["pid"], layer, p["kind"], p.get("name") or "", round(x, 6), round(y, 6)])
    index.sort(key=lambda e: e[0])
    (DATA / "places_index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")))

    # --- sources, dated by this build (the extract's release in the name) ---
    ov = lambda de, en: {"de": f"{de} (Overture {release})", "en": f"{en} (Overture {release})", "url": "https://docs.overturemaps.org/attribution/", "date": today}
    card = {"building": {
        "osm": ov("OpenStreetMap, Gebäude", "OpenStreetMap, buildings"),
        "msft": ov("Microsoft ML Buildings", "Microsoft ML Buildings"),
        "rgz": {**ov("RGZ, Adressregister (via OpenAddresses)", "RGZ address register (via OpenAddresses)"), "url": "https://data.gov.rs/sr/datasets/adresni-registar/"},
        "osm_area": ov("OpenStreetMap, Siedlung und Gemeinden", "OpenStreetMap, settlement and municipalities"),
    }}
    (DATA / "card_sources.json").write_text(json.dumps(card, ensure_ascii=False, indent=1))
    ps = {"overture": ov("Overture Places (Meta, Foursquare, Microsoft, AllThePlaces)", "Overture places (Meta, Foursquare, Microsoft, AllThePlaces)"),
          "osm": ov("OpenStreetMap, Spielplätze", "OpenStreetMap, playgrounds")}
    (DATA / "places_sources.json").write_text(json.dumps({layer: ps for layer in by_layer}, ensure_ascii=False, indent=1))
    print(f"  area {area_m2(area) / 1e6:.0f} km2, {len(parts)} parts, {sum(1 for f in feats if 'address' in f['properties'])} buildings with an address")


if __name__ == "__main__":
    main()
