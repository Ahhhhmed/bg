"""
Land plots (Liegenschaften) for the map area, from the official cadastral
survey (Amtliche Vermessung), and the join to our buildings.

Source: geodienste.ch's open AV WFS (https://geodienste.ch/db/av_0/deu),
layer `ms:RESF` (Liegenschaften): one polygon per plot with its number
(`Nummer`), the national plot id `EGRIS_EGRID`, its area in m2 (`Flaeche`)
and the municipality (`BFSNr`). Openly available for Canton Zürich. Owner
names are not part of it (they need a request to the land registry).

Plots are kept whole (a plot is a legal unit; cutting it at the area edge
would make its area wrong): a plot belongs to the map when a point inside it
lies in the area.

The join is exact: every GWR building carries the EGRID of the plot it
stands on (`egrid`, from enrich_building_properties.py). Per plot this adds
`buildings` (above-ground buildings on it) and `built_pct` (their footprint
area / plot area; only when every one of them has its cadastral-survey
outline, else unknown: C-05); per building `parcel_area_m2` and `parcel_built_pct`, for
the hover card.

  python3 cities/zurich/pipeline/swiss/build_parcels.py

Writes data/work/zurich_parcels.geojson (gitignored; snapshot in
data/snapshots/, see cities/zurich/pipeline/refresh.sh) and updates
building_polygons_baujahr.geojson in place. Run after build_av_footprints.py
(the footprint areas come from it); then shared/build_tiles.sh zurich. Fetch
cached in `_av_parcels_cache.json`.
"""
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from shapely.geometry import box, mapping, shape
from shapely.prepared import prep

sys.path.insert(0, str(Path(__file__).parent))
from area import area_bbox, area_polygon  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LAYERS = ROOT / "data" / "work"
BUILDINGS = LAYERS / "building_polygons_baujahr.geojson"
PARCELS = LAYERS / "zurich_parcels.geojson"
CACHE = LAYERS / "_av_parcels_cache.json"

WFS_URL = "https://geodienste.ch/db/av_0/deu"
TYPENAME = "ms:RESF"
TILE_DEG = 0.02     # like build_av_footprints.py; a dense city tile has ~5k plots
PAGE_CAP = 10000    # a tile that hits it gets split
REQUEST_DELAY = 0.2
M_PER_DEG_LAT = 111320.0
SOURCE = "geodienste.ch AV WFS ms:RESF Liegenschaften (live)"


def _filter(bbox):
    xmin, ymin, xmax, ymax = bbox
    return (
        '<Filter xmlns="http://www.opengis.net/fes/2.0" xmlns:gml="http://www.opengis.net/gml/3.2">'
        '<BBOX><ValueReference>geom</ValueReference><gml:Envelope srsName="urn:ogc:def:crs:EPSG::4326">'
        f"<gml:lowerCorner>{ymin} {xmin}</gml:lowerCorner><gml:upperCorner>{ymax} {xmax}</gml:upperCorner>"
        "</gml:Envelope></BBOX></Filter>"
    )


def _fetch_tile(bbox):
    params = {
        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": TYPENAME,
        "FILTER": _filter(bbox), "COUNT": str(PAGE_CAP), "SRSNAME": "EPSG:4326",
        "OUTPUTFORMAT": "application/json; subtype=geojson",
    }
    url = WFS_URL + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=180) as resp:
                return json.loads(resp.read())["features"]
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if attempt == 3:
                # a hole in the plots would be silent on the map: stop
                raise RuntimeError(f"AV WFS plot tile {bbox} failed: {e}") from e
            time.sleep(2 * (attempt + 1))


def _owns(bbox, feature):
    """A plot straddling a tile edge comes back from both tiles; keep it in
    the tile that contains its first vertex (half-open bounds)."""
    xmin, ymin, xmax, ymax = bbox
    g = feature["geometry"]
    ring = g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0]
    x, y = ring[0][0], ring[0][1]
    return xmin <= x < xmax and ymin <= y < ymax


def fetch_parcels(region):
    if CACHE.exists():
        print(f"Loading cached plots from {CACHE.name} (delete it to force a re-fetch)...")
        return json.loads(CACHE.read_text())
    print(f"Fetching {TYPENAME} from {WFS_URL} ...")
    xmin, ymin, xmax, ymax = area_bbox()
    region_p = prep(region)
    stack = []
    x = xmin
    while x < xmax:
        y = ymin
        while y < ymax:
            t = (x, y, min(x + TILE_DEG, xmax), min(y + TILE_DEG, ymax))
            if region_p.intersects(box(*t)):
                stack.append(t)
            y += TILE_DEG
        x += TILE_DEG
    out, tiles = [], 0
    while stack:
        bbox = stack.pop()
        feats = _fetch_tile(bbox)
        time.sleep(REQUEST_DELAY)
        tiles += 1
        if len(feats) >= PAGE_CAP:
            bx0, by0, bx1, by1 = bbox
            mx, my = (bx0 + bx1) / 2, (by0 + by1) / 2
            stack += [(bx0, by0, mx, my), (mx, by0, bx1, my), (bx0, my, mx, by1), (mx, my, bx1, by1)]
            continue
        for f in feats:
            if f.get("geometry") and _owns(bbox, f):
                out.append(f)
        if tiles % 20 == 0:
            print(f"  ...{tiles} tiles, {len(out)} plots so far")
    CACHE.write_text(json.dumps(out))
    print(f"  {tiles} tiles, cached {len(out)} plots -> {CACHE.name}")
    return out


def _area_m2(g, lat0):
    kx = M_PER_DEG_LAT * math.cos(math.radians(lat0))
    from shapely import affinity
    return affinity.scale(g, kx, M_PER_DEG_LAT, origin=(0, 0)).area


def main():
    region = area_polygon()
    region_p = prep(region)
    raw = fetch_parcels(region)

    plots = {}
    skipped = 0
    for f in raw:
        g = shape(f["geometry"])
        if not g.is_valid:
            g = g.buffer(0)
        if g.is_empty or not region_p.contains(g.representative_point()):
            skipped += 1
            continue
        p = f["properties"]
        egrid = p.get("EGRIS_EGRID") or None
        plots[egrid or f"_{len(plots)}"] = {
            "geom": g,
            "props": {"nr": p.get("Nummer"), "egrid": egrid, "area_m2": p.get("Flaeche"), "bfs": p.get("BFSNr")},
        }
    print(f"{len(plots)} plots in the area ({skipped} outside it)")

    fc = json.loads(BUILDINGS.read_text())
    lat0 = (area_bbox()[1] + area_bbox()[3]) / 2
    built = {}
    n_buildings = {}
    traced = set()
    matched = 0
    for f in fc["features"]:
        b = f["properties"]
        e = b.get("egrid")
        for k in ("parcel_area_m2", "parcel_built_pct"):
            b.pop(k, None)
        if not e or e not in plots:
            continue
        matched += 1
        if b.get("underground"):
            continue
        built[e] = built.get(e, 0) + _area_m2(shape(f["geometry"]), lat0)
        n_buildings[e] = n_buildings.get(e, 0) + 1
        if b.get("geometry_type") != "cadastral_footprint_av":
            traced.add(e)   # a placeholder / traced outline: the plot's share would be a guess
    for e, pl in plots.items():
        pr = pl["props"]
        pr["buildings"] = n_buildings.get(e, 0)
        if pr["area_m2"] and e not in traced:   # only from surveyed outlines (C-05)
            pr["built_pct"] = min(100, round(100 * built.get(e, 0) / pr["area_m2"]))
    for f in fc["features"]:
        b = f["properties"]
        pl = plots.get(b.get("egrid"))
        if pl and pl["props"]["area_m2"]:
            b["parcel_area_m2"] = pl["props"]["area_m2"]
            b["parcel_built_pct"] = pl["props"].get("built_pct")
    print(f"buildings joined to a plot by EGRID: {matched} of {len(fc['features'])}")

    PARCELS.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": mapping(pl["geom"]), "properties": {**pl["props"], "source": SOURCE}}
        for pl in plots.values()]}))
    BUILDINGS.write_text(json.dumps(fc))
    with_buildings = sum(1 for pl in plots.values() if pl["props"]["buildings"])
    print(f"Wrote {len(plots)} plots ({with_buildings} with buildings) -> {PARCELS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
