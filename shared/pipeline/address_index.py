#!/usr/bin/env python3
"""The address search's file: every building with a GWR address,
so the map can find "Scheffelstrasse 29" without an outside geocoder.

Reads cities/<city>/data/layers/buildings.geojson (the city\'s pipeline
writes it), writes cities/<city>/data/address_index.json,
served at /data/address_index.json and loaded when the search field is first used:

    {"cols": ["address", "plz", "egid", "lon", "lat"], "rows": [[...], ...]}

Public register fields only (owner, C-18): the GWR address and postcode, the
EGID and a position (the footprint's centroid, 5 decimals, ~1 m). Every
building with an address, housing or not, planned ones included (owner,
2026-10-25). scripts/build.sh refuses a file with other columns. Run it
after anything that rewrites the buildings, like the tiles.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
import argparse
_ap = argparse.ArgumentParser(); _ap.add_argument("city"); CITY = _ap.parse_args().city
SRC = ROOT / "cities" / CITY / "data/layers/buildings.geojson"
OUT = ROOT / "cities" / CITY / "data/address_index.json"
COLS = ["address", "plz", "egid", "lon", "lat"]


def centroid(geom):
    """Area-weighted centroid of the largest outer ring (no shapely needed)."""
    rings = [geom["coordinates"][0]] if geom["type"] == "Polygon" else [p[0] for p in geom["coordinates"]]
    best, best_a = None, -1.0
    for ring in rings:
        a = cx = cy = 0.0
        for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
            c = x0 * y1 - x1 * y0
            a += c
            cx += (x0 + x1) * c
            cy += (y0 + y1) * c
        if abs(a) > best_a:
            best_a = abs(a)
            best = (cx / (3 * a), cy / (3 * a)) if a else ring[0]
    return best


def main():
    if not SRC.exists():
        sys.exit(f"{SRC} missing: run the city's pipeline first (README)")
    rows = []
    for f in json.loads(SRC.read_text())["features"]:
        p = f["properties"]
        addr = (p.get("address") or "").strip()
        if not addr or not p.get("egid") or not f.get("geometry"):
            continue
        lon, lat = centroid(f["geometry"])
        plz = str(p.get("plz") or "").split("/")[0]
        rows.append([addr, plz, int(p["egid"]), round(lon, 5), round(lat, 5)])
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    OUT.write_text(json.dumps({"cols": COLS, "rows": rows}, ensure_ascii=False, separators=(",", ":")))
    print(f"wrote {OUT.relative_to(ROOT)}: {len(rows)} addresses, {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
