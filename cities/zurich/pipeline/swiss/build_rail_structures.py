"""
Tunnels and bridges for the rail and road networks: adds
`structure` ("tunnel" / "bridge") to the rail and road segments in
zurich_roads_rail.geojson, so the map can draw tunnels
faintly and bridges with a casing. Surface segments get no `structure`.

The identify API that build_roads_rail.py fetches from doesn't return
swissTLM3D's structure attribute (KUNSTBAUTE), so this reads it from the
national swissTLM3D shapefile download instead -- only the members it needs,
via HTTP Range requests (see remote_zip.py) -- and joins it onto our segments
spatially. Both come from the same swissTLM3D, so the segments line up.

- Rail: member TLM_EISENBAHN (~10 MB of the 3.6 GB ZIP). A segment counts as
  tunnel / bridge when >= 50 % of its length lies within 3 m of such a TLM line
  (union of all tunnel / bridge lines).
- Roads: member TLM_STRASSE (~500 MB compressed, ~3 GB unpacked). Roads are
  dense and often run parallel within a few metres (ramps beside a viaduct,
  streets under the Hardbrücke, a street above a cut-and-cover tunnel), so a
  union buffer would tag the wrong line. Each road segment is matched to the
  ONE TLM line it lies on best (largest share of its length within 3 m, ties
  broken by mean vertex distance) and takes that line's KUNSTBAUTE if the share
  is >= 50 %. The TLM road lines near the area are cached in
  _tlm_cache/TLM_STRASSE_area.json (~few MB) and the 3 GB download is deleted.

  python3 cities/zurich/pipeline/swiss/build_rail_structures.py            # rail and roads
  python3 cities/zurich/pipeline/swiss/build_rail_structures.py rail       # only one kind
  python3 cities/zurich/pipeline/swiss/build_rail_structures.py road

Run after build_roads_rail.py (or the snapshot restore); re-running is safe.
Needs pyshp (`uv pip install pyshp`). Roads: ~2 min download + a few minutes
to scan the national shapefile on the first run, ~1 min with the cache.
"""
import collections
import json
import sys
from pathlib import Path

import numpy as np
import shapefile
import shapely
from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString, shape

sys.path.insert(0, str(Path(__file__).parent))
from area import area_polygon  # noqa: E402
from remote_zip import RemoteZip  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LAYERS = ROOT / "data" / "work"
ROADS_RAIL = LAYERS / "zurich_roads_rail.geojson"
CACHE = LAYERS / "_tlm_cache"
TLM_URL = ("https://data.geo.admin.ch/ch.swisstopo.swisstlm3d/swisstlm3d_2026-02/"
           "swisstlm3d_2026-02_2056_5728.shp.zip")
MEMBER = "TLM_OEV\\swissTLM3D_TLM_EISENBAHN"
ROAD_MEMBER = "TLM_STRASSEN\\swissTLM3D_TLM_STRASSE"
ROAD_AREA_CACHE = CACHE / "TLM_STRASSE_area.json"

# KUNSTBAUTE -> our structure class. Covered sections (underpasses, galleries,
# tracks inside buildings such as the underground stations) read as tunnels.
# Roads add stairs variants and footbridges (Steg); Treppe, Furt, Staudamm and
# k_W (no value) stay surface.
STRUCTURE = {"Tunnel": "tunnel", "Unterfuehrung": "tunnel", "Galerie": "tunnel",
             "in/auf Gebaeude": "tunnel", "Unterfuehrung mit Treppe": "tunnel",
             "Bruecke": "bridge", "Gedeckte Bruecke": "bridge", "Bruecke mit Galerie": "bridge",
             "Bruecke mit Treppe": "bridge", "Steg": "bridge"}
BUFFER_M = 3.0
MIN_SHARE = 0.5

TO_LV95 = Transformer.from_crs(4326, 2056, always_xy=True)


def to_lv95(g):
    return shapely.transform(g, lambda c: np.column_stack(TO_LV95.transform(c[:, 0], c[:, 1])))


def area_bounds():
    return to_lv95(area_polygon()).buffer(500).bounds


def download(member, base):
    if base.with_suffix(".shp").exists():
        return
    print(f"downloading {member}.* from the swissTLM3D ZIP (range requests) ...", flush=True)
    z = RemoteZip(TLM_URL)
    for ext in ("shp", "shx", "dbf", "prj", "cpg"):
        z.extract(f"{member}.{ext}", base.with_suffix(f".{ext}"))


def iter_lines(base, bounds, keep=None):
    """(KUNSTBAUTE, [part coordinate lists]) of every TLM line touching bounds."""
    x0, y0, x1, y1 = bounds
    r = shapefile.Reader(str(base))
    for sr in r.iterShapeRecords(fields=["KUNSTBAUTE"]):
        k = sr.record["KUNSTBAUTE"]
        if keep and k not in keep:
            continue
        bx = sr.shape.bbox
        if bx[2] < x0 or bx[0] > x1 or bx[3] < y0 or bx[1] > y1:
            continue
        pts = [(p[0], p[1]) for p in sr.shape.points]
        parts = list(sr.shape.parts) + [len(pts)]
        yield k, [pts[a:b] for a, b in zip(parts, parts[1:]) if b - a > 1]
    r.close()


def rail_zones():
    CACHE.mkdir(exist_ok=True)
    base = CACHE / "TLM_EISENBAHN"
    download(MEMBER, base)
    out = collections.defaultdict(list)
    for k, parts in iter_lines(base, area_bounds(), keep=STRUCTURE):
        out[STRUCTURE[k]].extend(LineString(p) for p in parts)
    return {cls: shapely.union_all(shapely.buffer(np.array(gs), BUFFER_M)) for cls, gs in out.items()}


def road_lines():
    """All TLM road lines near the area (any KUNSTBAUTE), from the small area cache."""
    if not ROAD_AREA_CACHE.exists():
        CACHE.mkdir(exist_ok=True)
        base = CACHE / "TLM_STRASSE"
        download(ROAD_MEMBER, base)
        print("scanning TLM_STRASSE for lines near the area ...", flush=True)
        rows = [{"k": k, "c": [[[round(x, 2), round(y, 2)] for x, y in p] for p in parts]}
                for k, parts in iter_lines(base, area_bounds())]
        ROAD_AREA_CACHE.write_text(json.dumps(rows))
        for ext in ("shp", "shx", "dbf", "prj", "cpg"):         # ~3 GB, not needed again
            base.with_suffix(f".{ext}").unlink(missing_ok=True)
    rows = json.loads(ROAD_AREA_CACHE.read_text())
    return [r["k"] for r in rows], [MultiLineString(r["c"]) for r in rows]


def tag_rail(features):
    zones = rail_zones()
    for z in zones.values():
        shapely.prepare(z)
    counts = collections.Counter()
    for f in features:
        p = f["properties"]
        p.pop("structure", None)
        g = to_lv95(shape(f["geometry"]))
        if g.length == 0:
            continue
        for cls in ("tunnel", "bridge"):
            z = zones.get(cls)
            if z is not None and g.intersection(z).length >= MIN_SHARE * g.length:
                p["structure"] = cls
                break
        counts[p.get("structure", "surface")] += 1
    return counts


def tag_roads(features):
    kb, lines = road_lines()
    lines = np.array(lines)
    bufs = shapely.buffer(lines, BUFFER_M)
    tree = shapely.STRtree(lines)
    counts, kunst = collections.Counter(), collections.Counter()
    for f in features:
        p = f["properties"]
        p.pop("structure", None)
        g = to_lv95(shape(f["geometry"]))
        if g.length == 0:
            continue
        cand = tree.query(g, predicate="dwithin", distance=BUFFER_M)
        if len(cand):
            share = shapely.length(shapely.intersection(g, bufs[cand])) / g.length
            verts = shapely.points(shapely.get_coordinates(g))
            mean_d = np.array([shapely.distance(verts, lines[c]).mean() for c in cand])
            best = cand[np.lexsort((mean_d, -np.round(share, 2)))[0]]
            if share[list(cand).index(best)] >= MIN_SHARE:
                kunst[kb[best]] += 1
                cls = STRUCTURE.get(kb[best])
                if cls:
                    p["structure"] = cls
        counts[p.get("structure", "surface")] += 1
    print(f"  best-matching TLM KUNSTBAUTE: {dict(kunst)}")
    return counts


def main():
    kinds = sys.argv[1:] or ["rail", "road"]
    fc = json.loads(ROADS_RAIL.read_text())
    for kind in kinds:
        feats = [f for f in fc["features"] if f["properties"].get("kind") == kind]
        counts = (tag_rail if kind == "rail" else tag_roads)(feats)
        print(f"{kind} segments: {dict(counts)}", flush=True)
    ROADS_RAIL.write_text(json.dumps(fc))
    print(f"-> {ROADS_RAIL.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
