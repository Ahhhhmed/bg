"""
Public transport for the map area: every stop, and the federal
public-transport quality grades (ÖV-Güteklassen).

Sources (both open federal data, downloaded whole from data.geo.admin.ch):
  - Stops: BAV's register of stops, `ch.bav.haltestellen-oev`
    (Betriebspunkt.csv, LV95). Kept: rows of type "Haltestelle" /
    "Haltestelle und Bedienpunkt" inside the area. The means of transport is a
    code string (A bus, B train, C tram, D metro, E rack railway, F funicular,
    G cabin / H chair lift, I boat, J lift); a stop served by several gets
    the most important one as `kind` (train > tram > boat > funicular > bus)
    and all of them in `modes`; a "train" street stop ("Zürich, Balgrist", the
    Forchbahn running as a tram in town) counts as tram, a rack railway as a
    funicular. `hub` = a rail station: drawn bigger and from z11 on the map.
  - Quality grades: ARE's `ch.are.gueteklassen_oev` (latest year,
    OeV_Gueteklassen_ARE in the GeoPackage): polygons of grade A (very good)
    to D (low), computed from the departures at nearby stops. Its own stop
    table adds the ARE stop category (`cat`, 1 = best .. 6) to our stops, by
    the stop number.

  python3 cities/zurich/pipeline/swiss/build_transit.py              # fetch, write both layers, join
  python3 cities/zurich/pipeline/swiss/build_transit.py --join-only  # only the per-building join

Writes data/work/transit_stops.geojson (points: name, nr, kind, modes, cat,
hub) and data/work/oev_gueteklassen.geojson (polygons, cut at the area
border: k = "A".."D"), then joins both onto every building in
building_polygons_baujahr.geojson (so the building card shows
what these layers show): `oev_class` ("A".."D", the grade polygon a point
inside the building lies in; none = outside every grade, i.e. below D) and
the nearest stop by straight line from that point, `stop_name`, `stop_kind`,
`stop_m` (metres, rounded to 10), within STOP_MAX_M. Then
shared/build_tiles.sh zurich. Downloads cached in data/work/_transit_cache/
(gitignored).
"""
import collections
import csv
import io
import json
import sqlite3
import sys
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import shapely
import shapely.geometry
from pyproj import Transformer
from shapely.geometry import Point, mapping
from shapely.prepared import prep

sys.path.insert(0, str(Path(__file__).parent))
from area import area_polygon  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LAYERS = ROOT / "data" / "work"
CACHE = LAYERS / "_transit_cache"
STOPS_OUT = LAYERS / "transit_stops.geojson"
BUILDINGS = LAYERS / "building_polygons_baujahr.geojson"
STOP_MAX_M = 2000
GRADES_OUT = LAYERS / "oev_gueteklassen.geojson"

STOPS_URL = ("https://data.geo.admin.ch/ch.bav.haltestellen-oev/haltestellen-oev/"
             "haltestellen-oev_2056_de.csv.zip")
GRADES_STAC = "https://data.geo.admin.ch/api/stac/v0.9/collections/ch.are.gueteklassen_oev/items"

STOP_TYPES = {"Haltestelle", "Haltestelle und Bedienpunkt"}
MODE = {"A": "bus", "B": "train", "C": "tram", "D": "metro", "E": "rack", "F": "funicular",
        "G": "cable", "H": "cable", "I": "boat", "J": "lift"}
# the symbol a stop gets: its most important means of transport
RANK = ["train", "metro", "tram", "boat", "rack", "funicular", "cable", "lift", "bus"]
KIND = {"metro": "train", "rack": "funicular", "cable": "funicular", "lift": "funicular"}
SIMPLIFY_M = 2.0

TO_WGS = Transformer.from_crs(2056, 4326, always_xy=True)


def to_wgs(g):
    return shapely.transform(g, lambda xy: np.column_stack(TO_WGS.transform(xy[:, 0], xy[:, 1])))


def download(url, name):
    CACHE.mkdir(exist_ok=True)
    path = CACHE / name
    if not path.exists():
        print(f"Downloading {url} ...")
        with urllib.request.urlopen(url, timeout=300) as r:
            path.write_bytes(r.read())
    return zipfile.ZipFile(path)


def latest_grades_url():
    with urllib.request.urlopen(GRADES_STAC, timeout=60) as r:
        items = json.loads(r.read())["features"]
    item = max(items, key=lambda it: it["properties"]["datetime"])
    href = next(a["href"] for a in item["assets"].values() if a["href"].endswith(".gpkg.zip"))
    return href, item["id"]


def gpkg_geom(blob):
    """Shapely geometry from a GeoPackage geometry blob (header + WKB)."""
    flags = blob[3]
    env = (flags >> 1) & 7
    header = 8 + {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[env]
    return shapely.from_wkb(blob[header:])


def main():
    region = area_polygon()
    region_p = prep(region)
    to_lv95 = Transformer.from_crs(4326, 2056, always_xy=True)
    region95 = shapely.transform(region, lambda xy: np.column_stack(to_lv95.transform(xy[:, 0], xy[:, 1])))

    # ---- quality grades (and the ARE stop categories) ----
    url, item = latest_grades_url()
    zf = download(url, f"{item}.gpkg.zip")
    gpkg_name = next(n for n in zf.namelist() if n.endswith(".gpkg"))
    gpkg = CACHE / gpkg_name
    if not gpkg.exists():
        zf.extract(gpkg_name, CACHE)
    db = sqlite3.connect(gpkg)
    grades = []
    for blob, k in db.execute("select geom, KLASSE from OeV_Gueteklassen_ARE"):
        g = gpkg_geom(blob)
        if not g.intersects(region95):
            continue
        g = g.intersection(region95).simplify(SIMPLIFY_M, preserve_topology=True)
        if g.is_empty or g.area < 1:
            continue
        grades.append({"type": "Feature", "geometry": mapping(to_wgs(g)), "properties": {"k": k}})
    cat = {int(nr): int(c) for nr, c in db.execute("select Haltestellen_No, Hst_Kat from OeV_Haltestellen_ARE")
           if nr is not None and c is not None}

    # ---- stops ----
    zf = download(STOPS_URL, "haltestellen-oev_2056_de.csv.zip")
    rows = csv.DictReader(io.TextIOWrapper(zf.open("Betriebspunkt.csv"), encoding="utf-8-sig"))
    stops = []
    for r in rows:
        if r["Betriebspunkttyp_Bezeichnung"] not in STOP_TYPES or not r["E"]:
            continue
        p = Point(*TO_WGS.transform(float(r["E"]), float(r["N"])))
        if not region_p.contains(p):
            continue
        modes = sorted({MODE[c] for c in r["Verkehrsmittel_Code"] if c in MODE}, key=RANK.index)
        if not modes:
            continue
        kind = KIND.get(modes[0], modes[0])
        if kind == "train" and "," in r["Name"]:
            # a street stop ("Zürich, Balgrist") the Forchbahn serves as a tram
            # in town; rail stations are named without a comma
            kind = "tram"
        nr = int(r["Nummer"])
        stops.append({"type": "Feature", "geometry": mapping(p), "properties": {
            "name": r["Name"], "nr": nr, "kind": kind, "modes": ",".join(modes),
            "cat": cat.get(nr), "hub": kind == "train"}})

    STOPS_OUT.write_text(json.dumps({"type": "FeatureCollection", "features": stops}, ensure_ascii=False))
    GRADES_OUT.write_text(json.dumps({"type": "FeatureCollection", "features": grades}))
    by_kind = {}
    for s in stops:
        by_kind[s["properties"]["kind"]] = by_kind.get(s["properties"]["kind"], 0) + 1
    print(f"{len(stops)} stops in the area: " + ", ".join(f"{k} {v}" for k, v in sorted(by_kind.items())))
    print(f"  {sum(1 for s in stops if s['properties']['cat'] is not None)} with an ARE stop category")
    by_k = {}
    for g in grades:
        by_k[g["properties"]["k"]] = by_k.get(g["properties"]["k"], 0) + 1
    print(f"{len(grades)} grade polygons ({item}): " + ", ".join(f"{k} {v}" for k, v in sorted(by_k.items())))
    print(f"-> {STOPS_OUT.relative_to(ROOT)} ({STOPS_OUT.stat().st_size / 1e6:.2f} MB), "
          f"{GRADES_OUT.relative_to(ROOT)} ({GRADES_OUT.stat().st_size / 1e6:.2f} MB)")


def join_buildings():
    """oev_class and the nearest stop onto every building (see the docstring)."""
    to_lv95 = Transformer.from_crs(4326, 2056, always_xy=True)
    grades = json.loads(GRADES_OUT.read_text())["features"]
    stops = json.loads(STOPS_OUT.read_text())["features"]
    print(f"Joining {len(grades)} grade polygons and {len(stops)} stops onto {BUILDINGS.name} ...")
    fc = json.loads(BUILDINGS.read_text())
    feats = [f for f in fc["features"] if f.get("geometry")]
    points = shapely.point_on_surface(np.array([shapely.geometry.shape(f["geometry"]) for f in feats], dtype=object))
    gtree = shapely.STRtree([shapely.geometry.shape(f["geometry"]) for f in grades])
    bi, gi = gtree.query(points, predicate="intersects")
    rank = "DCBA"   # a point on a shared edge takes the better grade
    grade = {}
    for b, g in zip(bi, gi):
        k = grades[g]["properties"]["k"]
        if b not in grade or rank.index(k) > rank.index(grade[b]):
            grade[b] = k
    xy = np.column_stack(to_lv95.transform(shapely.get_x(points), shapely.get_y(points)))
    sxy = np.array([to_lv95.transform(*s["geometry"]["coordinates"]) for s in stops])
    stree = shapely.STRtree(shapely.points(sxy))
    near, dist = stree.query_nearest(shapely.points(xy), max_distance=STOP_MAX_M, return_distance=True, all_matches=False)
    nearest = dict(zip(near[0], zip(near[1], dist)))
    for i, f in enumerate(feats):
        p = f["properties"]
        for k in ("oev_class", "stop_name", "stop_kind", "stop_m"):
            p.pop(k, None)
        if i in grade:
            p["oev_class"] = grade[i]
        if i in nearest:
            s, d = nearest[i]
            p["stop_name"] = stops[s]["properties"]["name"]
            p["stop_kind"] = stops[s]["properties"]["kind"]
            p["stop_m"] = int(round(d / 10) * 10)
    BUILDINGS.write_text(json.dumps(fc))
    by = collections.Counter(grade.values())
    print(f"  oev_class on {len(grade)} of {len(feats)} buildings: " + ", ".join(f"{k} {by[k]}" for k in "ABCD"))
    ds = sorted(int(d) for _, d in nearest.values())
    print(f"  nearest stop for {len(nearest)} buildings; median {ds[len(ds) // 2]} m, 90th percentile {ds[int(len(ds) * 0.9)]} m")


if __name__ == "__main__":
    if "--join-only" not in sys.argv:
        main()
    join_buildings()
