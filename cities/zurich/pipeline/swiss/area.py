"""
The map area, shared by every pipeline script.

The area is the union of the municipalities listed in config/area.yaml. Their real borders are fetched once by
build_municipalities.py into data/work/municipalities.geojson; this module
reads that file and exposes:

  MUNICIPALITIES  list of {"bfs": int, "name": str} from config/area.yaml
  area_polygon()  shapely (Multi)Polygon of the union, WGS84
  area_bbox()     (xmin, ymin, xmax, ymax) of the union -- use this instead
                  of a hard-coded rectangle when fetching new data
  BFS_NUMBERS     set of the configured BFS numbers

config/area.yaml is parsed with a tiny reader (no PyYAML dependency): it only
supports the flat `- bfs: N / name: X` list it ships with.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "area.yaml"
MUNICIPALITIES_PATH = ROOT / "data" / "work" / "municipalities.geojson"

# The rectangle the project used before item 009; kept for scripts that
# haven't been switched to the area yet (see SOURCES.md).
LEGACY_BBOX = (8.45, 47.28, 8.65, 47.45)


def _read_config():
    items, cur = [], None
    for line in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].rstrip()
        m = re.match(r"^\s*-\s*bfs:\s*(\d+)\s*$", line)
        if m:
            cur = {"bfs": int(m.group(1))}
            items.append(cur)
            continue
        m = re.match(r"^\s+name:\s*(.+?)\s*$", line)
        if m and cur is not None:
            cur["name"] = m.group(1)
    if not items:
        raise ValueError(f"no municipalities found in {CONFIG_PATH}")
    return items


MUNICIPALITIES = _read_config()
BFS_NUMBERS = {m["bfs"] for m in MUNICIPALITIES}


def municipality_features():
    if not MUNICIPALITIES_PATH.exists():
        raise FileNotFoundError(
            f"{MUNICIPALITIES_PATH} missing -- run cities/zurich/pipeline/swiss/build_municipalities.py first"
        )
    return json.loads(MUNICIPALITIES_PATH.read_text())["features"]


def area_polygon():
    from shapely.geometry import shape
    from shapely.ops import unary_union

    return unary_union([shape(f["geometry"]) for f in municipality_features()])


def area_bbox():
    return area_polygon().bounds
