"""
Fetch the real borders of the municipalities in config/area.yaml.

Source: swisstopo swissBOUNDARIES3D via geo.admin.ch's `find` API, layer
`ch.swisstopo.swissboundaries3d-gemeinde-flaeche.fill`. A name search
returns one feature per year since 1850; we keep the one flagged
`is_current_jahr` and check its BFS number (`gde_nr`) against the config, so
a renamed or merged municipality fails loudly instead of silently mapping
the wrong shape.

Writes data/work/municipalities.geojson with one feature per
municipality: name, bfs, canton, area_km2, year. Re-runnable (~15 s).
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from pyproj import Geod
from shapely.geometry import mapping, shape

sys.path.insert(0, str(Path(__file__).parent))
from area import MUNICIPALITIES, MUNICIPALITIES_PATH

FIND_URL = "https://api3.geo.admin.ch/rest/services/api/MapServer/find"
LAYER = "ch.swisstopo.swissboundaries3d-gemeinde-flaeche.fill"
GEOD = Geod(ellps="WGS84")


def find_current(name, bfs):
    params = {
        "layer": LAYER,
        "searchText": name,
        "searchField": "gemname",
        "contains": "false",
        "returnGeometry": "true",
        "geometryFormat": "geojson",
        "sr": "4326",
    }
    url = FIND_URL + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                results = json.loads(resp.read())["results"]
            break
        except Exception as e:
            if attempt == 3:
                raise RuntimeError(f"find {name!r} failed: {e}") from e
            time.sleep(2 * (attempt + 1))
    current = [r for r in results if r["properties"].get("is_current_jahr")]
    matching = [r for r in current if r["properties"].get("gde_nr") == bfs]
    if len(matching) != 1:
        found = [(r["properties"]["gemname"], r["properties"]["gde_nr"]) for r in current]
        raise RuntimeError(f"{name!r} (BFS {bfs}): expected 1 current feature, got {found}")
    return matching[0]


def main():
    features = []
    print(f"Resolving {len(MUNICIPALITIES)} municipalities from config/area.yaml ...")
    for m in MUNICIPALITIES:
        r = find_current(m["name"], m["bfs"])
        p = r["properties"]
        geom = shape(r["geometry"]).buffer(0)
        area_km2 = abs(GEOD.geometry_area_perimeter(geom)[0]) / 1e6
        features.append({
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": {
                "name": p["gemname"],
                "bfs": p["gde_nr"],
                "canton": p["kanton"],
                "area_km2": round(area_km2, 2),
                "year": p["jahr"],
                "level": "municipality",
            },
        })
        print(f"  {p['gemname']:<16} BFS {p['gde_nr']:>4}  {p['kanton']}  {area_km2:6.2f} km2  ({p['jahr']})")
        time.sleep(0.2)
    MUNICIPALITIES_PATH.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    print(f"Wrote {len(features)} municipalities -> {MUNICIPALITIES_PATH}")


if __name__ == "__main__":
    main()
