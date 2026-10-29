"""
Shared helper for pulling real vector data out of the geo.admin.ch
`identify` REST endpoint (api3.geo.admin.ch) for a bounding box.

The identify endpoint caps each response at 201 features. There is no
bbox-filtered bulk download for most swisstopo/BFS layers (the official
bulk product is a single ~3GB national shapefile), so instead we tile the
bounding box and recursively split any tile that comes back saturated
(== 201 results) into quadrants until every tile is under the cap.

This is real, authoritative government data (swisstopo / BFS), fetched
live, not synthetic placeholders.

A tile the API keeps failing on (4 tries) would leave a hole in the dataset,
so fetch_layer counts such tiles and raises FetchIncomplete at the end, which
stops the calling script with a non-zero exit before it writes anything. To keep a partial result on purpose, set
BAU_ALLOW_PARTIAL_FETCH=1 (or pass allow_partial=True); the given-up tiles
are still listed. Tiles still at the 201-result cap at max depth are counted
and reported, but don't fail the run (they are rare and only lose the
features beyond the cap).
"""
import json
import os
import time
import urllib.request
import urllib.parse

API_URL = "https://api3.geo.admin.ch/rest/services/api/MapServer/identify"
CAP = 201  # observed hard cap on identify responses
MAX_DEPTH = 9  # 0.2deg bbox / 2^9 =~ 40m tiles at the deepest, city-center only
REQUEST_DELAY = 0.15  # be polite to a free public government API


class FetchIncomplete(RuntimeError):
    """Some tiles failed after every retry; the fetched data would have holes."""


def _fetch_tile(layer, bbox, geometry_format=None):
    xmin, ymin, xmax, ymax = bbox
    params = {
        "geometryType": "esriGeometryEnvelope",
        "geometry": f"{xmin},{ymin},{xmax},{ymax}",
        "imageDisplay": "1000,1000,96",
        "mapExtent": f"{xmin},{ymin},{xmax},{ymax}",
        "tolerance": "0",
        "layers": f"all:{layer}",
        "returnGeometry": "true",
        "sr": "4326",
    }
    if geometry_format:
        params["geometryFormat"] = geometry_format
    url = API_URL + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = json.loads(resp.read())
            return data.get("results", [])
        except Exception as e:
            if attempt == 3:
                print(f"  ! giving up on tile {bbox} for {layer}: {e}")
                return None
            time.sleep(1.5 * (attempt + 1))


def fetch_layer(layer, bbox, geometry_format="geojson", log_prefix="", region=None, allow_partial=None):
    """Recursively tile `bbox` and fetch all features of `layer`, deduped by featureId.

    `region` (optional shapely geometry, WGS84): skip tiles that don't touch it,
    e.g. the map area from area.py -- its bbox is much bigger than the area.
    Raises FetchIncomplete if any tile was given up on, unless `allow_partial`
    (default: the BAU_ALLOW_PARTIAL_FETCH environment variable is "1").
    """
    if allow_partial is None:
        allow_partial = os.environ.get("BAU_ALLOW_PARTIAL_FETCH") == "1"
    from shapely.geometry import box
    from shapely.prepared import prep

    region_p = prep(region) if region is not None else None
    seen = {}
    stack = [(bbox, 0)]
    tiles_done = 0
    saturated_at_max_depth = 0
    given_up = []
    while stack:
        (xmin, ymin, xmax, ymax), depth = stack.pop()
        if region_p is not None and not region_p.intersects(box(xmin, ymin, xmax, ymax)):
            continue
        results = _fetch_tile(layer, (xmin, ymin, xmax, ymax), geometry_format)
        time.sleep(REQUEST_DELAY)
        tiles_done += 1
        if results is None:
            given_up.append((xmin, ymin, xmax, ymax))
            continue
        if tiles_done % 25 == 0:
            print(f"{log_prefix}  ...{tiles_done} tiles queried, {len(seen)} unique features so far")

        if len(results) >= CAP and depth >= MAX_DEPTH:
            # can't split further: features beyond the cap are lost here
            saturated_at_max_depth += 1
        if len(results) >= CAP and depth < MAX_DEPTH:
            mx, my = (xmin + xmax) / 2, (ymin + ymax) / 2
            stack.extend([
                ((xmin, ymin, mx, my), depth + 1),
                ((mx, ymin, xmax, my), depth + 1),
                ((xmin, my, mx, ymax), depth + 1),
                ((mx, my, xmax, ymax), depth + 1),
            ])
            continue

        for r in results:
            fid = r.get("featureId") or r.get("id")
            if fid not in seen:
                seen[fid] = r

    print(f"{log_prefix}done: {tiles_done} tiles, {len(seen)} unique features, "
          f"{len(given_up)} tiles given up, {saturated_at_max_depth} saturated at max depth")
    if saturated_at_max_depth:
        print(f"{log_prefix}  ! {saturated_at_max_depth} tile(s) still hit the {CAP}-result cap at max depth "
              f"{MAX_DEPTH}: some features there may be missing")
    if given_up:
        listing = "\n".join(f"    {b}" for b in given_up)
        msg = (f"{log_prefix}{len(given_up)} tile(s) of {layer} failed after every retry, "
               f"so the result has holes there:\n{listing}")
        if not allow_partial:
            raise FetchIncomplete(msg + "\nRe-run (the API is usually back), or set BAU_ALLOW_PARTIAL_FETCH=1 "
                                  "to keep the partial result on purpose.")
        print(msg + "\n  (kept anyway: BAU_ALLOW_PARTIAL_FETCH=1)")
    return list(seen.values())
