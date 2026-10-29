#!/usr/bin/env python3
"""Walking distance from every building to the nearest place of each kind,
and the commute to the city's target (C-15, C-04), for any city (Zürich's own
copy is cities/zurich/pipeline/swiss/build_walk.py).

  python3 shared/pipeline/walk.py <city>      # then shared/build_tiles.sh <city>

Reads cities/<city>/data/layers/{buildings,roads_rail,stops,places_*}.geojson,
rewrites buildings.geojson (w_<kind> metres rounded to 10, n_<kind> = the
nearest place's position in places_index.json; commute_hb_min,
commute_hb_stop, n_hb, w_hb) and data/places_index.json
([id, layer, kind, name, lon, lat], sorted by id). Deterministic.

  - Network: the city's roads and paths (`kind: road`) without motorways,
    slip roads and expressways (objektart 0-3, 21: swissTLM3D's codes, which
    the Belgrade build maps OSM classes onto); the largest connected piece.
  - Buildings start at their footprint's representative point, places at
    their point; each joins the nearest network vertex in a straight line.
  - One multi-source Dijkstra per kind, up to MAX_M.
  - Commute: the best over every stop within COMMUTE_WALK_M on foot of
    walk / 80 m/min + the stop's mean morning trip to the target (`hb_mean`
    from the city's transit script); the target stop itself (if the city
    has one, Zürich HB) counts 0.
"""
import heapq
import json
import sys
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parent.parent.parent
WALK_M_PER_MIN = 80.0
MAX_M = 6000
COMMUTE_WALK_M = 1500
NO_WALK = {0, 1, 2, 3, 21}

# per city: metric CRS, the target stop (0 minutes) and the kinds:
# kind -> (place layer, kinds in it); "stop" = stops.geojson
CITIES = {
    "zurich": {"crs": "EPSG:2056", "target_nr": 8503000, "kinds": {
        "kg": ("schools", {"kindergarten"}), "kita": ("schools", {"kita"}), "sch": ("schools", {"school"}),
        "stop": ("stops", None), "sup": ("shops", {"supermarket"}), "post": ("shops", {"post"}),
        "doc": ("health", {"doctor"}), "pha": ("health", {"pharmacy"}), "play": ("playgrounds", {"playground"}),
        "bath": ("baths", {"lakebath", "pool"}), "er": ("hospitals", {"er"})}},
    # Belgrade: no Kita layer (OSM / Overture don't tell day care from
    # kindergarten), no emergency stations (no list of them; a hospital isn't one)
    "belgrade": {"crs": "EPSG:32634", "target_nr": None, "kinds": {
        "kg": ("schools", {"kindergarten"}), "sch": ("schools", {"school"}),
        "stop": ("stops", None), "sup": ("shops", {"supermarket"}), "post": ("shops", {"post"}),
        "doc": ("health", {"doctor"}), "pha": ("health", {"pharmacy"}), "play": ("playgrounds", {"playground"}),
        "bath": ("baths", {"lakebath", "pool"})}},
}


def build_graph(roads, proj):
    key = lambda x, y: (round(x, 1), round(y, 1))
    adj = {}
    for f in json.loads(roads.read_text())["features"]:
        p = f["properties"]
        if p.get("kind") != "road" or p.get("objektart") in NO_WALK:
            continue
        g = f["geometry"]
        lines = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
        for line in lines:
            pts = [proj(*c[:2]) for c in line]
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                a, b = key(x1, y1), key(x2, y2)
                if a == b:
                    continue
                d = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
                adj.setdefault(a, []).append((b, d))
                adj.setdefault(b, []).append((a, d))
    seen, best = set(), set()
    for start in adj:
        if start in seen:
            continue
        comp, stack = {start}, [start]
        while stack:
            for nb, _ in adj[stack.pop()]:
                if nb not in comp:
                    comp.add(nb)
                    stack.append(nb)
        seen |= comp
        if len(comp) > len(best):
            best = comp
    return {n: adj[n] for n in best}


class Snap:
    def __init__(self, nodes):
        self.nodes = sorted(nodes)
        self.tree = STRtree([Point(n) for n in self.nodes])

    def __call__(self, x, y):
        n = self.nodes[self.tree.nearest(Point(x, y))]
        return n, ((n[0] - x) ** 2 + (n[1] - y) ** 2) ** 0.5


def dijkstra(adj, sources, limit=MAX_M):
    best = {}
    heap = [(d, i, n, pid) for i, (n, d, pid) in enumerate(sorted(sources, key=lambda s: (s[1], str(s[2]))))]
    heapq.heapify(heap)
    while heap:
        d, i, n, pid = heapq.heappop(heap)
        if n in best or d > limit:
            continue
        best[n] = (d, pid)
        for nb, w in adj[n]:
            if nb not in best:
                heapq.heappush(heap, (d + w, i, nb, pid))
    return best


def bounded(adj, start, d0, limit):
    best, heap = {}, [(d0, start)]
    while heap:
        d, n = heapq.heappop(heap)
        if n in best or d > limit:
            continue
        best[n] = d
        for nb, w in adj[n]:
            if nb not in best:
                heapq.heappush(heap, (d + w, nb))
    return best


def main(city):
    cfg = CITIES[city]
    layers = ROOT / "cities" / city / "data" / "layers"
    tr = Transformer.from_crs("EPSG:4326", cfg["crs"], always_xy=True)
    proj = tr.transform
    print("network ...")
    adj = build_graph(layers / "roads_rail.geojson", proj)
    snap = Snap(adj)
    print(f"  {len(adj)} vertices (largest piece)")
    stops = json.loads((layers / "stops.geojson").read_text())["features"] if (layers / "stops.geojson").exists() else []
    targets, index, feats = {k: [] for k in cfg["kinds"]}, {}, {}
    for f in stops:
        lon, lat = f["geometry"]["coordinates"][:2]
        p = f["properties"]
        if "stop" in targets:
            targets["stop"].append((lon, lat, p["nr"]))
        index[str(p["nr"])] = ["stops", p.get("kind") or "", p.get("name") or "", round(lon, 6), round(lat, 6)]
    for path in sorted(layers.glob("places_*.geojson")):
        layer = path.stem[len("places_"):]
        for f in json.loads(path.read_text())["features"]:
            p = f["properties"]
            lon, lat = f["geometry"]["coordinates"][:2]
            index[p["pid"]] = [layer, p["kind"], p.get("name") or "", round(lon, 6), round(lat, 6)]
            for kind, (kl, kinds) in cfg["kinds"].items():
                if kl == layer and kinds and p["kind"] in kinds:
                    targets[kind].append((lon, lat, p["pid"]))
    order = sorted(index)
    pos = {i: n for n, i in enumerate(order)}
    bpath = layers / "buildings.geojson"
    fc = json.loads(bpath.read_text())
    starts = []
    for f in fc["features"]:
        pt = shape(f["geometry"]).representative_point()
        starts.append(snap(*proj(pt.x, pt.y)))
    for kind, pts in targets.items():
        best = dijkstra(adj, [(*snap(*proj(lon, lat)), pid) for lon, lat, pid in pts])
        got = []
        for f, (n, d0) in zip(fc["features"], starts):
            p = f["properties"]
            p.pop(f"w_{kind}", None)
            p.pop(f"n_{kind}", None)
            hit = best.get(n)
            if hit and hit[0] + d0 <= MAX_M:
                p[f"w_{kind}"] = int(round(hit[0] + d0, -1))
                p[f"n_{kind}"] = pos[str(hit[1])]
                got.append(p[f"w_{kind}"])
        got.sort()
        q = lambda x: got[int(len(got) * x)] if got else None
        print(f"  {kind:5} {len(pts):5} places; {len(got)} buildings; median {q(.5)} m, 90th pct {q(.9)} m")
    # commute to the target
    best = {}
    for f in sorted(stops, key=lambda f: f["properties"]["nr"]):
        p = f["properties"]
        mean = 0.0 if p["nr"] == cfg["target_nr"] else p.get("hb_mean")
        if mean is None:
            continue
        n0, d0 = snap(*proj(*f["geometry"]["coordinates"][:2]))
        for n, d in bounded(adj, n0, d0, COMMUTE_WALK_M).items():
            v = (d / WALK_M_PER_MIN + mean, p["nr"], p["name"], d)
            if n not in best or v[:2] < best[n][:2]:
                best[n] = v
    got = []
    for f, (n, d0) in zip(fc["features"], starts):
        p = f["properties"]
        for k in ("commute_hb_min", "commute_hb_stop", "n_hb", "w_hb"):
            p.pop(k, None)
        hit = best.get(n)
        if hit:
            p["commute_hb_min"] = int(round(hit[0] + d0 / WALK_M_PER_MIN))
            p["commute_hb_stop"] = hit[2]
            p["n_hb"] = pos[str(hit[1])]
            p["w_hb"] = int(round(hit[3] + d0, -1))
            got.append(p["commute_hb_min"])
    got.sort()
    if got:
        print(f"  commute: {len(got)} buildings; 10/50/90th pct {got[len(got) // 10]} / {got[len(got) // 2]} / {got[len(got) * 9 // 10]} min")
    bpath.write_text(json.dumps(fc, ensure_ascii=False))
    (ROOT / "cities" / city / "data" / "places_index.json").write_text(
        json.dumps([[i, *index[i]] for i in order], ensure_ascii=False, separators=(",", ":")))
    print(f"wrote buildings.geojson and places_index.json ({len(index)} places)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else sys.exit("usage: walk.py <city>"))
