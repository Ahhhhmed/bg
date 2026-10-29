"""
Walking distance from every building to the nearest place of each kind: kindergarten, Kita, school, stop, supermarket, post office,
doctor, pharmacy, playground, bath, hospital with an emergency station.

  python3 cities/zurich/pipeline/swiss/build_walk.py      # then shared/build_tiles.sh zurich

Deterministic and re-runnable whenever the places, the stops, the roads or
the buildings change (owner, 2026-10-23: our own calculation, as long as it
can be redone). Run it after build_places.py / build_transit.py and after
anything that rewrites the buildings.

How:
  - The walking network is swissTLM3D's roads and paths
    (zurich_roads_rail.geojson, `kind: road`) without motorways and
    expressways (objektart 0-3, 21); segments join where they share a vertex
    (bridges and tunnels only at their ends). Only the largest connected
    piece is used, so nothing snaps onto an island of paths.
  - A building starts at its footprint's representative point, a place at
    its point; each joins the network at its nearest vertex in a straight
    line (the "connector"). Places beyond the clipped network (hospitals up
    to 3 km outside the area) join at the nearest edge vertex the same way.
  - One multi-source Dijkstra per kind (all of that kind's places at once,
    each starting at its connector length) up to MAX_M; a building's
    distance = its connector + the network distance at its vertex.
  - Written onto every building: `w_<kind>` (metres, rounded to 10) and
    `n_<kind>` (the nearest place: its position in places_index.json).
    The 22 values add ~4.7 MB (+14 %) to the archive (2026-10-23).
    Walking minutes are shown as metres / 80 (an estimate, "≈" on the card).

Commute to Zürich HB (`commute_hb_min`, `commute_hb_stop`; owner, 2026-10-23:
the map's "Zürich HB" layer uses the timetable profiles of):
  the best over every stop within COMMUTE_WALK_M on foot of
      walk (network metres / 80) + the stop's mean trip to HB on a weekday
      morning 06:30-09:00, waiting included (`hb_mean`, build_timetable.py)
  Zürich HB itself counts 0 (a building near HB walks there). Whole minutes;
  `commute_hb_stop` = the stop's name, `n_hb` = its position in
  places_index.json and `w_hb` = the walk to it (metres): the building card's
  stop is this one, the stop that makes most sense for HB, not the nearest
  (owner, 2026-10-23). Replaces build_commute.py's estimate
  (straight line x 1.3 + half the headway + the median of six connections
  from transport.opendata.ch), which this repo doesn't carry.

Also writes data/work/places_index.json (served at
/data/places_index.json): a list of [id, layer, kind, name, lon, lat], id =
`pid` from build_places.py or the stop's `nr`, sorted by id. The card names
the nearest places and opens their cards from it. The positions change when
the places do; this script rewrites the index and the buildings together, so
run the tile build after it.
"""
import heapq
import json
import sys
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import shape
from shapely.strtree import STRtree
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[2]
LAYERS = ROOT / "data" / "work"
BUILDINGS = LAYERS / "building_polygons_baujahr.geojson"
ROADS = LAYERS / "zurich_roads_rail.geojson"
INDEX = LAYERS / "places_index.json"
WALK_M_PER_MIN = 80.0  # as the card and the colour mode (web/layers.js)
MAX_M = 6000           # no value beyond this
COMMUTE_WALK_M = 1500  # stops this far on foot count for the commute to HB
HB_NR = 8503000        # Zürich HB: the destination itself, 0 minutes
NO_WALK = {0, 1, 2, 3, 21}   # swissTLM3D objektart: motorway, slip roads, rest areas, expressway

# kind -> (place layer, kinds in it); "stop" = transit_stops.geojson
KINDS = {
    "kg": ("schools", {"kindergarten"}),
    "kita": ("schools", {"kita"}),
    "sch": ("schools", {"school"}),
    "stop": ("stops", None),
    "sup": ("shops", {"supermarket"}),
    "post": ("shops", {"post"}),
    "doc": ("health", {"doctor"}),
    "pha": ("health", {"pharmacy"}),
    "play": ("playgrounds", {"playground"}),
    "bath": ("baths", {"lakebath", "pool"}),
    "er": ("hospitals", {"er"}),
}

_LV95 = Transformer.from_crs("EPSG:4326", "EPSG:2056", always_xy=True)


def lv95(lon, lat):
    return _LV95.transform(lon, lat)


def build_graph():
    """{node: [(neighbour, metres)]} and node coordinates, the largest piece."""
    key = lambda x, y: (round(x, 1), round(y, 1))
    adj = {}
    for f in json.loads(ROADS.read_text())["features"]:
        p = f["properties"]
        if p.get("kind") != "road" or p.get("objektart") in NO_WALK:
            continue
        g = f["geometry"]
        lines = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
        for line in lines:
            pts = [lv95(*c[:2]) for c in line]
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                a, b = key(x1, y1), key(x2, y2)
                if a == b:
                    continue
                d = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
                adj.setdefault(a, []).append((b, d))
                adj.setdefault(b, []).append((a, d))
    # the largest connected piece
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
    """The nearest network vertex to a point (straight line)."""
    def __init__(self, nodes):
        self.nodes = sorted(nodes)          # sorted: ties resolve the same way every run
        self.tree = STRtree([Point(n) for n in self.nodes])

    def __call__(self, x, y):
        i = self.tree.nearest(Point(x, y))
        n = self.nodes[i]
        return n, ((n[0] - x) ** 2 + (n[1] - y) ** 2) ** 0.5


def dijkstra(adj, sources):
    """sources: [(node, start metres, place id)] -> {node: (metres, place id)}."""
    best = {}
    heap = [(d, i, n, pid) for i, (n, d, pid) in enumerate(sorted(sources, key=lambda s: (s[1], str(s[2]))))]
    heapq.heapify(heap)
    while heap:
        d, i, n, pid = heapq.heappop(heap)
        if n in best or d > MAX_M:
            continue
        best[n] = (d, pid)
        for nb, w in adj[n]:
            if nb not in best:
                heapq.heappush(heap, (d + w, i, nb, pid))
    return best


def bounded(adj, start, d0, limit):
    """{node: metres} from one start node (d0 = its connector) up to `limit`."""
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


def commute(adj, snap, fc, starts, pos):
    """commute_hb_min / commute_hb_stop on every building (see the docstring)."""
    stops = json.loads((LAYERS / "transit_stops.geojson").read_text())["features"]
    best = {}   # node -> (minutes from this node, stop nr, stop name, metres walked)
    used = 0
    for f in sorted(stops, key=lambda f: f["properties"]["nr"]):
        p = f["properties"]
        mean = 0.0 if p["nr"] == HB_NR else p.get("hb_mean")
        if mean is None:
            continue
        used += 1
        n0, d0 = snap(*lv95(*f["geometry"]["coordinates"][:2]))
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
    q = lambda x: got[int(len(got) * x)]
    print(f"  commute to HB: {used} stops with a morning profile; {len(got)} buildings; "
          f"10/50/90th pct {q(.1)} / {q(.5)} / {q(.9)} min")


def places():
    """{kind: [(lon, lat, id)]} and the index {id: [layer, kind, name, lon, lat]}."""
    out, index = {k: [] for k in KINDS}, {}
    for f in json.loads((LAYERS / "transit_stops.geojson").read_text())["features"]:
        lon, lat = f["geometry"]["coordinates"][:2]
        p = f["properties"]
        out["stop"].append((lon, lat, p["nr"]))
        index[str(p["nr"])] = ["stops", p.get("kind") or "", p.get("name") or "", round(lon, 6), round(lat, 6)]
    layers = {}
    for kind, (layer, kinds) in KINDS.items():
        if layer == "stops":
            continue
        if layer not in layers:
            layers[layer] = json.loads((LAYERS / f"places_{layer}.geojson").read_text())["features"]
        for f in layers[layer]:
            p = f["properties"]
            lon, lat = f["geometry"]["coordinates"][:2]
            index[p["pid"]] = [layer, p["kind"], p.get("name") or "", round(lon, 6), round(lat, 6)]
            if p["kind"] in kinds:
                out[kind].append((lon, lat, p["pid"]))
    return out, index


def main():
    print("network ...")
    adj = build_graph()
    snap = Snap(adj)
    print(f"  {len(adj)} vertices, {sum(len(v) for v in adj.values()) // 2} edges (largest piece)")
    targets, index = places()
    order = sorted(index)
    pos = {i: n for n, i in enumerate(order)}
    fc = json.loads(BUILDINGS.read_text())
    starts = []
    for f in fc["features"]:
        pt = shape(f["geometry"]).representative_point()
        starts.append(snap(*lv95(pt.x, pt.y)))
    conn = sorted(d for _, d in starts)
    print(f"  buildings: connector median {conn[len(conn) // 2]:.0f} m, 99th pct {conn[int(len(conn) * .99)]:.0f} m")
    for kind, pts in targets.items():
        sources = []
        for lon, lat, pid in pts:
            n, d = snap(*lv95(lon, lat))
            sources.append((n, d, pid))
        best = dijkstra(adj, sources)
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
    commute(adj, snap, fc, starts, pos)
    BUILDINGS.write_text(json.dumps(fc))
    INDEX.write_text(json.dumps([[i, *index[i]] for i in order], ensure_ascii=False, separators=(",", ":")))
    print(f"wrote {BUILDINGS.relative_to(ROOT)} and {INDEX.relative_to(ROOT)} ({len(index)} places)")


if __name__ == "__main__":
    sys.exit(main())
