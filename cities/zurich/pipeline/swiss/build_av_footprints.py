"""
Upgrade building geometry to the official cadastral-survey footprint
(Amtliche Vermessung, AV) wherever one exists.

Source: geodienste.ch's open AV WFS (https://geodienste.ch/db/av_0/deu),
layer `ms:LCSF` (Bodenbedeckung / land cover), filtered to `Art =
Gebaeude`, plus `ms:LCSFPROJ` (projected land cover: planned and recently
built buildings not yet transferred into LCSF) and `ms:SOSF` (Einzelobjekte)
for `unterirdisches_Gebaeude` (underground garages etc.) and `Unterstand`
(carports, shelters) -- GWR registers those as buildings too, but they
aren't land cover. Each polygon is the surveyed ground footprint of a
building and carries `GWR_EGID` -- the same EGID key our GWR data uses -- so
the join is exact, like build_roof_footprints.py's. It is also the geometry
swisstopo's own basemap draws its buildings from, which is why it lines up
with swisstopo's raster map.

It covers what the earlier tiers couldn't: garages, sheds and other small
structures (no solar-roof data, too small to raster-trace reliably), plus
buildings whose solar facets only cover part of the roof.

Priority per building after this pass:
  1. AV footprint, joined by exact EGID (all AV polygons sharing that EGID
     are unioned; current land cover wins over projected land cover, which
     wins over an individual-object footprint, so a building with a surface
     outline is never marked underground).
  2. AV footprint containing the building's GWR point (from the GWR cache
     `_gwr_raw_cache.json`; without it, a square's centre), for every
     building not on tier 1 -- squares, raster traces and solar-roof shapes -- and only if that AV polygon carries no EGID or an EGID
     not present in our GWR set (so we never steal a polygon that belongs to
     another registered building). Current land cover is preferred over
     projected over individual objects; a residential building never takes
     an individual-object outline (its point inside an underground garage
     means a house above a garage, not a garage). Containment, not
     nearest-neighbour -- the fuzzy matching tried in the early raster pass
     is what produced mis-assigned shapes.
  3. Whatever geometry the building already had (solar roof, raster trace,
     or square) -- except that a building in development (GWR status
     1001-1003) on a raster trace becomes a square at its GWR point: the
     raster basemap shows the old building it replaces.

`geometry_type` becomes `cadastral_footprint_av` for tiers 1-2,
`footprint_match` records `egid` or `point_in_polygon`, and `underground`
is set to true for `unterirdisches_Gebaeude` footprints -- swisstopo's
basemap doesn't draw those, so web/map.js renders them faintly instead of as
solid buildings.

Finally, buildings still on the square get a size cap and are shrunk and/or
nudged a few metres until they don't overlap another building, a road or
water (`fit_leftover_squares`): an unknown footprint should read as a small
placeholder, not as a large block drawn across a street.

Reads and rewrites data/work/building_polygons_baujahr.geojson in place
(run after build_roof_footprints.py / enrich_building_properties.py; it only
touches geometry and the properties above). Also reads
zurich_roads_rail.geojson and zurich_water.geojson as obstacles for the
square fitting.
"""
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from shapely import affinity
from shapely.geometry import Point, box, shape, mapping
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[2]
BUILDINGS_PATH = ROOT / "data" / "work" / "building_polygons_baujahr.geojson"
AV_CACHE = ROOT / "data" / "work" / "_av_buildings_cache.json"
AV_OBJECTS_CACHE = ROOT / "data" / "work" / "_av_objects_cache.json"
AV_PROJECTED_CACHE = ROOT / "data" / "work" / "_av_projected_cache.json"
GWR_CACHE = ROOT / "data" / "work" / "_gwr_raw_cache.json"
ROADS_PATH = ROOT / "data" / "work" / "zurich_roads_rail.geojson"
WATER_PATH = ROOT / "data" / "work" / "zurich_water.geojson"

sys.path.insert(0, str(Path(__file__).parent))
from area import area_bbox, area_polygon

# The map area (config/area.yaml, see area.py); only tiles near it.
BBOX = area_bbox()
REGION = area_polygon().buffer(0.002)  # ~200 m margin
WFS_URL = "https://geodienste.ch/db/av_0/deu"
TILE_DEG = 0.02  # ~1.5 x 2.2 km; the densest city tiles return ~3k polygons
PAGE_CAP = 10000  # request cap per tile; a tile that hits it gets split
REQUEST_DELAY = 0.2

GEOMETRY_TYPE = "cadastral_footprint_av"
SOURCE = "geodienste.ch AV WFS ms:LCSF Art=Gebaeude (live), joined by GWR_EGID"
SQUARE = "approximate_square_from_gwr_point"
RASTER = "extracted_from_raster_tiles"
SOLAR = "real_roof_footprint_solar_vector"
GWR_SOURCE = "geo.admin.ch ch.bfs.gebaeude_wohnungs_register (live)"  # the squares' source
UNFINISHED = (1001, 1002, 1003)
RESIDENTIAL = (1010, 1020, 1030, 1040)
# point-in-polygon preference: current land cover, projected, individual objects
LAYER_RANK = {"ms:LCSF": 0, "ms:LCSFPROJ": 1, "ms:SOSF": 2}

# Leftover-square fitting (metres)
SQUARE_MAX_AREA_M2 = 300  # GWR area can be a 2,700 m2 underground garage; cap the placeholder
SQUARE_MIN_SIDE_M = 4
SQUARE_SHRINK = 0.85
SQUARE_NUDGES_M = (0, 3, 6, 9, 12, 15)
ROAD_HALF_WIDTH_M = 3  # roads are centrelines; keep squares off the carriageway
M_PER_DEG_LAT = 111320.0


UNDERGROUND_ART = "unterirdisches_Gebaeude"
# (WFS layer, `Art` values to keep, cache file)
AV_LAYERS = [
    ("ms:LCSF", ["Gebaeude"], AV_CACHE),
    ("ms:LCSFPROJ", ["Gebaeude"], AV_PROJECTED_CACHE),
    ("ms:SOSF", [UNDERGROUND_ART, "Unterstand"], AV_OBJECTS_CACHE),
]


def _filter(bbox, arts):
    xmin, ymin, xmax, ymax = bbox
    art = "".join(
        f"<PropertyIsEqualTo><ValueReference>Art</ValueReference><Literal>{a}</Literal></PropertyIsEqualTo>"
        for a in arts
    )
    if len(arts) > 1:
        art = f"<Or>{art}</Or>"
    return (
        '<Filter xmlns="http://www.opengis.net/fes/2.0" xmlns:gml="http://www.opengis.net/gml/3.2"><And>'
        f"{art}"
        '<BBOX><ValueReference>geom</ValueReference><gml:Envelope srsName="urn:ogc:def:crs:EPSG::4326">'
        f"<gml:lowerCorner>{ymin} {xmin}</gml:lowerCorner><gml:upperCorner>{ymax} {xmax}</gml:upperCorner>"
        "</gml:Envelope></BBOX></And></Filter>"
    )


def _fetch_tile(typename, arts, bbox):
    params = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": typename,
        "FILTER": _filter(bbox, arts),
        "COUNT": str(PAGE_CAP),
        "SRSNAME": "EPSG:4326",
        "OUTPUTFORMAT": "application/json; subtype=geojson",
    }
    url = WFS_URL + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=180) as resp:
                return json.loads(resp.read())["features"]
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if attempt == 3:
                raise RuntimeError(f"AV WFS tile {bbox} failed: {e}") from e
            time.sleep(2 * (attempt + 1))


def _owns(bbox, feature):
    """A polygon straddling a tile edge comes back from both tiles; keep it
    only in the tile containing its first vertex (half-open bounds)."""
    xmin, ymin, xmax, ymax = bbox
    geom = feature["geometry"]
    ring = geom["coordinates"][0] if geom["type"] == "Polygon" else geom["coordinates"][0][0]
    x, y = ring[0][0], ring[0][1]
    return xmin <= x < xmax and ymin <= y < ymax


def fetch_av_layer(typename, arts, cache):
    if cache.exists():
        print(f"Loading cached {typename} {arts} from {cache} (delete it to force a re-fetch)...")
        return json.loads(cache.read_text())

    print(f"Fetching {typename} {arts} from {WFS_URL} ...")
    xmin, ymin, xmax, ymax = BBOX
    stack = []
    x = xmin
    while x < xmax:
        y = ymin
        while y < ymax:
            stack.append((x, y, min(x + TILE_DEG, xmax), min(y + TILE_DEG, ymax)))
            y += TILE_DEG
        x += TILE_DEG

    from shapely.prepared import prep
    region_p = prep(REGION)
    stack = [t for t in stack if region_p.intersects(box(*t))]

    out, tiles_done = [], 0
    while stack:
        bbox = stack.pop()
        feats = _fetch_tile(typename, arts, bbox)
        time.sleep(REQUEST_DELAY)
        tiles_done += 1
        if len(feats) >= PAGE_CAP:
            bx0, by0, bx1, by1 = bbox
            mx, my = (bx0 + bx1) / 2, (by0 + by1) / 2
            stack += [(bx0, by0, mx, my), (mx, by0, bx1, my), (bx0, my, mx, by1), (mx, my, bx1, by1)]
            continue
        for f in feats:
            if f.get("geometry") and _owns(bbox, f):
                pr = f["properties"]
                out.append({
                    "egid": pr.get("GWR_EGID") or None,
                    "art": pr.get("Art"),
                    "layer": typename,
                    "geometry": f["geometry"],
                })
        if tiles_done % 20 == 0:
            print(f"  ...{tiles_done} tiles, {len(out)} footprints so far")

    cache.write_text(json.dumps(out))
    print(f"  cached {len(out)} footprints -> {cache}")
    return out


def load_gwr_points():
    """{egid: (lon, lat)} of the GWR register points, from enrich_building_properties.py's cache."""
    if not GWR_CACHE.exists():
        print(f"  ! {GWR_CACHE.name} missing: point-in-polygon falls back to the squares' centres, "
              "raster / solar buildings are skipped (run enrich_building_properties.py first)")
        return {}
    pts = {}
    for r in json.loads(GWR_CACHE.read_text()):
        g = r.get("geometry") or {}
        if "x" in g and "y" in g:
            pts[str(r["attributes"]["egid"])] = (g["x"], g["y"])
    print(f"  {len(pts)} GWR points from {GWR_CACHE.name}")
    return pts


def main():
    gwr_points = load_gwr_points()
    av = []
    for typename, arts, cache in AV_LAYERS:
        for a in fetch_av_layer(typename, arts, cache):
            a.setdefault("layer", typename)  # caches written before "layer" was stored
            av.append(a)
    fc = json.loads(BUILDINGS_PATH.read_text())
    features = fc["features"]
    our_egids = {str(f["properties"]["egid"]) for f in features if f["properties"].get("egid") is not None}

    by_egid = {}  # egid -> {"surface": [...], "projected": [...], "underground": [...]}
    unowned = []  # (geom, is_underground, layer) no building in our set can claim by EGID
    for a in av:
        g = shape(a["geometry"]).buffer(0)
        if g.is_empty:
            continue
        underground = a.get("art") == UNDERGROUND_ART
        if a["egid"] and a["egid"] in our_egids:
            slot = by_egid.setdefault(a["egid"], {"surface": [], "projected": [], "underground": []})
            kind = "underground" if underground else "projected" if a["layer"] == "ms:LCSFPROJ" else "surface"
            slot[kind].append(g)
        else:
            unowned.append((g, underground, a["layer"]))
    print(f"{len(av)} AV footprints: {len(by_egid)} EGIDs matched, {len(unowned)} unowned")

    tree = STRtree([g for g, _, _ in unowned])
    claimed = set()
    counts = {}
    for f in features:
        p = f["properties"]
        before = p.get("geometry_type")
        egid = str(p.get("egid"))
        geom, how, underground = None, None, False
        if egid in by_egid:
            slot = by_egid[egid]
            underground = not (slot["surface"] or slot["projected"])
            geom, how = unary_union(slot["surface"] or slot["projected"] or slot["underground"]), "egid"
        elif before != GEOMETRY_TYPE or p.get("footprint_match") == "point_in_polygon":
            # (an earlier run's point-in-polygon matches compete again, so a
            # polygon is never handed to two buildings)
            pt = _gwr_point(f, gwr_points)
            residential = p.get("building_category") in RESIDENTIAL
            # a solar roof or a shape traced off the basemap is above ground
            seen_above = before in (SOLAR, RASTER)
            hits = [] if pt is None else sorted(
                (i for i in tree.query(pt, predicate="within")
                 if i not in claimed
                 and not (residential and unowned[i][2] == "ms:SOSF")
                 and not (seen_above and unowned[i][1])),
                key=lambda i: LAYER_RANK.get(unowned[i][2], 9))
            if hits:
                claimed.add(hits[0])
                geom, underground, _ = unowned[hits[0]]
                how = "point_in_polygon"
        if geom is None or geom.geom_type not in ("Polygon", "MultiPolygon"):
            redo = before == GEOMETRY_TYPE  # an earlier point-in-polygon match that no longer qualifies
            if (redo or (before == RASTER and p.get("building_status") in UNFINISHED)) and _gwr_point(f, gwr_points):
                # raster: traced off the basemap, which still shows the building this one replaces
                f["geometry"] = mapping(_gwr_point(f, gwr_points).buffer(0.0001, cap_style="square"))
                p["geometry_type"] = SQUARE
                p.pop("footprint_match", None)
                p.pop("underground", None)
                key = f"{before} ({'old point-in-polygon match' if redo else 'in development'}) -> square"
                counts[key] = counts.get(key, 0) + 1
                p["source"] = GWR_SOURCE
                continue
            counts[f"kept:{before}"] = counts.get(f"kept:{before}", 0) + 1
            continue
        f["geometry"] = mapping(geom)
        p["geometry_type"] = GEOMETRY_TYPE
        p["footprint_match"] = how
        if underground:
            p["underground"] = True
        else:
            p.pop("underground", None)
        p["source"] = SOURCE
        key = f"{before} -> av ({how}{', underground' if underground else ''})"
        counts[key] = counts.get(key, 0) + 1

    print("Geometry changes:")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")

    fit_leftover_squares(features, gwr_points)
    tiers = {}
    for f in features:
        tiers[f["properties"]["geometry_type"]] = tiers.get(f["properties"]["geometry_type"], 0) + 1
    print("Buildings per geometry_type: " + ", ".join(f"{k} {v}" for k, v in sorted(tiers.items())))
    BUILDINGS_PATH.write_text(json.dumps(fc))
    print(f"Wrote {len(features)} buildings -> {BUILDINGS_PATH}")


def _gwr_point(f, gwr_points):
    """The building's GWR register point; a square's centre if the cache is missing."""
    xy = gwr_points.get(str(f["properties"].get("egid")))
    if xy:
        return Point(xy)
    if f["properties"].get("geometry_type") == SQUARE:
        return shape(f["geometry"]).centroid
    return None


def _to_m(lat0):
    """Local equirectangular projection around lat0 -- plenty for 10m-scale fitting."""
    kx = M_PER_DEG_LAT * math.cos(math.radians(lat0))
    to_m = lambda g: affinity.scale(g, kx, M_PER_DEG_LAT, origin=(0, 0))
    to_deg = lambda g: affinity.scale(g, 1 / kx, 1 / M_PER_DEG_LAT, origin=(0, 0))
    return to_m, to_deg


def fit_leftover_squares(features, gwr_points=None):
    squares = [f for f in features if f["properties"].get("geometry_type") == SQUARE]
    if not squares:
        return
    lat0 = (BBOX[1] + BBOX[3]) / 2
    to_m, to_deg = _to_m(lat0)

    obstacles = [
        to_m(shape(f["geometry"]))
        for f in features
        if f["properties"].get("geometry_type") != SQUARE and not f["properties"].get("underground")
    ]
    for path, buf in ((ROADS_PATH, ROAD_HALF_WIDTH_M), (WATER_PATH, 0)):
        if not path.exists():
            print(f"  ! {path.name} missing -- leftover squares may overlap it")
            continue
        for f in json.loads(path.read_text())["features"]:
            if f.get("geometry"):
                g = to_m(shape(f["geometry"]))
                obstacles.append(g.buffer(buf) if buf or g.geom_type.endswith("LineString") else g)
    tree = STRtree(obstacles)

    def blocked(cand):
        return any(obstacles[i].intersects(cand) for i in tree.query(cand))

    placed = []  # squares fitted so far are obstacles for the next ones
    stats = {"fits_as_is": 0, "shrunk_or_nudged": 0, "minimum_size_overlapping": 0}
    for f in squares:
        p = f["properties"]
        # start from the GWR point (a re-run would otherwise start from last run's nudged square)
        c = to_m(_gwr_point(f, gwr_points or {}))
        side = math.sqrt(min(p.get("area_m2") or 80, SQUARE_MAX_AREA_M2))
        original_side = side
        chosen = None
        while chosen is None and side >= SQUARE_MIN_SIDE_M:
            for d in SQUARE_NUDGES_M:
                offsets = [(0, 0)] if d == 0 else [
                    (d * math.cos(a), d * math.sin(a)) for a in [k * math.pi / 4 for k in range(8)]
                ]
                for dx, dy in offsets:
                    cand = box(c.x + dx - side / 2, c.y + dy - side / 2, c.x + dx + side / 2, c.y + dy + side / 2)
                    if not blocked(cand) and not any(q.intersects(cand) for q in placed if q.distance(cand) < 1):
                        chosen = cand
                        break
                if chosen is not None:
                    break
            if chosen is None:
                side *= SQUARE_SHRINK
        if chosen is None:
            s = SQUARE_MIN_SIDE_M
            chosen = box(c.x - s / 2, c.y - s / 2, c.x + s / 2, c.y + s / 2)
            stats["minimum_size_overlapping"] += 1
        elif side == original_side and chosen.centroid.distance(c) < 1e-6:
            stats["fits_as_is"] += 1
        else:
            stats["shrunk_or_nudged"] += 1
        placed.append(chosen)
        f["geometry"] = mapping(to_deg(chosen))
    print(f"Fitted {len(squares)} leftover squares (cap {SQUARE_MAX_AREA_M2} m2, no overlap with buildings/roads/water):")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
