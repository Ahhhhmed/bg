"""
Elevation for the City of Zürich's buildings, from swisstopo swissALTI3D.

swissALTI3D is swisstopo's bare-earth elevation model (no buildings or trees),
2 m grid, open data, delivered as 1 km GeoTIFF tiles through the STAC API on
data.geo.admin.ch.

Steps:
  1. download every 2 m tile in the area's bounding box + 1 km (newest year per
     tile) into data/work/_dem_cache/ (kept, gitignored; re-runs only fetch
     what's missing);
  2. mosaic them at 5 m (average) -> data/work/elevation_5m.tif (LV95, uint16
     decimetres, 0 = no data), which enrich_building_properties.py samples at
     each building (`elevation_m`, the card's "m ü. M." tag).

Usage: python3 cities/zurich/pipeline/swiss/build_elevation.py
"""
import json
import resource
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.merge import merge
from rasterio.warp import Resampling
from shapely.geometry import box
from shapely.ops import transform as shp_transform

sys.path.insert(0, str(Path(__file__).parent))
from area import ROOT, area_bbox  # noqa: E402

WORK = ROOT / "data" / "work"
CACHE = WORK / "_dem_cache"
DEM_OUT = WORK / "elevation_5m.tif"
STAC = "https://data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.swissalti3d/items"
CELL = 5.0


def log(msg):
    print(msg, flush=True)


def fetch_tiles():
    CACHE.mkdir(parents=True, exist_ok=True)
    to95 = Transformer.from_crs(4326, 2056, always_xy=True).transform
    w, s, e, n = area_bbox()
    region = box(*shp_transform(to95, box(w, s, e, n)).bounds).buffer(1000, join_style=2)
    url = f"{STAC}?bbox={w - 0.015},{s - 0.01},{e + 0.015},{n + 0.01}&limit=100"
    newest = {}
    while url:
        with urllib.request.urlopen(url, timeout=60) as r:
            d = json.loads(r.read())
        for f in d["features"]:
            _, year, tile = f["id"].split("_")
            ex, ny = (int(v) * 1000 for v in tile.split("-"))
            if not region.intersects(box(ex, ny, ex + 1000, ny + 1000)):
                continue
            if tile not in newest or year > newest[tile][0]:
                href = next(a["href"] for a in f["assets"].values()
                            if a["href"].endswith(".tif") and float(a.get("eo:gsd", 0)) == 2.0)
                newest[tile] = (year, href)
        url = next((l["href"] for l in d.get("links", []) if l["rel"] == "next"), None)

    def get(item):
        tile, (year, href) = item
        dst = CACHE / f"{tile}.tif"
        stamp = CACHE / f"{tile}.year"
        if dst.exists() and stamp.exists() and stamp.read_text() == year:
            return 0
        for attempt in range(4):
            try:
                urllib.request.urlretrieve(href, dst.with_suffix(".part"))
                dst.with_suffix(".part").rename(dst)
                stamp.write_text(year)
                return 1
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 * (attempt + 1))

    with ThreadPoolExecutor(8) as ex:
        fetched = sum(ex.map(get, newest.items()))
    total = sum((CACHE / f"{t}.tif").stat().st_size for t in newest) / 1e6
    log(f"swissALTI3D: {len(newest)} tiles in bbox + 1 km ({fetched} downloaded now), {total:.0f} MB in {CACHE}")
    return [CACHE / f"{t}.tif" for t in sorted(newest)]


def elevation(srcs):
    t0 = time.perf_counter()
    arr, tr = merge(srcs, nodata=-9999, res=CELL, resampling=Resampling.average)
    dem = arr[0].astype("float32")
    dem[dem < -1000] = np.nan
    dm = np.where(np.isfinite(dem), np.round(dem * 10), 0).astype("uint16")
    with rasterio.open(DEM_OUT, "w", driver="GTiff", width=dm.shape[1], height=dm.shape[0], count=1,
                       dtype="uint16", nodata=0, crs=srcs[0].crs, transform=tr, compress="deflate",
                       predictor=2, tiled=True) as dst:
        dst.write(dm, 1)
        dst.update_tags(description="swissALTI3D elevation in decimetres, 5 m average, see build_elevation.py",
                        attribution="© swisstopo (swissALTI3D)")
    log(f"elevation: {dm.shape[1]}x{dm.shape[0]} px at {CELL:.0f} m, {DEM_OUT.stat().st_size / 1e6:.1f} MB "
        f"-> {DEM_OUT} ({time.perf_counter() - t0:.0f} s)")


def main():
    t0 = time.perf_counter()
    paths = fetch_tiles()
    srcs = [rasterio.open(p) for p in paths]
    elevation(srcs)
    for s_ in srcs:
        s_.close()
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    log(f"done in {time.perf_counter() - t0:.0f} s, peak memory {peak:.0f} MB")


if __name__ == "__main__":
    main()
