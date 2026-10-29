#!/usr/bin/env python3
"""Belgrade's relief: a hillshade from the Copernicus DEM GLO-30 (30 m, ESA /
Airbus, free licence), as one PNG the map lays under the vectors (an image
source, like swisstopo's relief tiles in Zürich: flat ground mid grey, slopes
lighter / darker, drawn at 25 %).

    python3 cities/belgrade/pipeline/build_relief.py

Reads the DEM tile from cities/belgrade/data/src/dem/ (downloaded here from
copernicus-dem-30m.s3.amazonaws.com if missing), writes
cities/belgrade/data/layers/relief.png and relief.json (the image's corners).
Rows are resampled to Web Mercator so the image lines up with the map.
"""
import json
import math
import urllib.request
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image

HERE = Path(__file__).resolve().parent
CITY = HERE.parent
DEM = CITY / "data" / "src" / "dem"
OUT = CITY / "data" / "layers"
TILE = "Copernicus_DSM_COG_10_N44_00_E020_00_DEM"   # 44-45 N, 20-21 E: all of Belgrade
X0, X1, Y0, Y1 = 20.0, 20.95, 44.5, 45.0            # the area + a wide margin (no edge in view at the start zoom)


def main():
    DEM.mkdir(parents=True, exist_ok=True)
    tif = DEM / f"{TILE}.tif"
    if not tif.exists():
        urllib.request.urlretrieve(f"https://copernicus-dem-30m.s3.amazonaws.com/{TILE}/{TILE}.tif", tif)
    z = tifffile.imread(tif).astype("float64")       # 3600 x 3600, top-left at 20 E / 45 N, 1 arcsec
    step = 1 / 3600
    c0, c1 = int((X0 - 20) / step), int((X1 - 20) / step)
    r0, r1 = int((45 - Y1) / step), int((45 - Y0) / step)
    z = z[r0:r1, c0:c1]
    lat = math.radians((Y0 + Y1) / 2)
    dx, dy = step * 111320 * math.cos(lat), step * 110540   # metres per pixel
    gy, gx = np.gradient(z, dy, dx)
    slope = np.arctan(1.3 * np.hypot(gx, gy))                # a little exaggerated: the city is flat
    aspect = np.arctan2(-gx, gy)
    az, alt = math.radians(315), math.radians(45)            # light from the north-west
    shade = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    flat = math.sin(alt)
    img = np.clip(128 + (shade - flat) * 255, 0, 255)
    # rows to Web Mercator
    merc = lambda y: math.log(math.tan(math.pi / 4 + math.radians(y) / 2))
    m0, m1 = merc(Y0), merc(Y1)
    h = img.shape[0]
    rows = []
    for i in range(h):
        m = m1 - (m1 - m0) * (i + 0.5) / h
        y = math.degrees(2 * math.atan(math.exp(m)) - math.pi / 2)
        rows.append(min(h - 1, max(0, int((Y1 - y) / step))))
    img = img[rows, :]
    OUT.mkdir(parents=True, exist_ok=True)
    Image.fromarray(img.astype("uint8"), "L").save(OUT / "relief.png", optimize=True)
    (OUT / "relief.json").write_text(json.dumps({"coordinates": [[X0, Y1], [X1, Y1], [X1, Y0], [X0, Y0]],
                                                  "source": "Copernicus DEM GLO-30 (ESA / Airbus)"}))
    print(f"relief.png {img.shape[1]} x {img.shape[0]}, {(OUT / 'relief.png').stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
