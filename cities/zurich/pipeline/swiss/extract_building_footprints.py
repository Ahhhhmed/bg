"""
Upgrade building footprints from synthetic squares to real shapes traced
off swisstopo's public Pixelkarte raster tiles.

Why this works: ch.swisstopo.pixelkarte-farbe is a cartographic rendering
of the same official vector data (swissTLM3D) we couldn't bulk-download
directly -- at zoom 18 it draws building footprints as solid near-black
fill (verified empirically against a known real GWR coordinate -- see
chat/session notes), distinct from white streets and green tree dots. So
we can threshold + contour-trace the raster back into real polygon shapes.

Pipeline:
  1. Figure out which z=18 tiles actually contain a building (from our
     existing GWR point data) -- avoids downloading tiles over the lake/
     forest/empty countryside.
  2. Download those tiles concurrently (plain public JPEG tiles, no key).
  3. Threshold near-black pixels, contour-trace, filter out street-label
     text / thin lines by area+solidity, simplify, project pixel coords
     back to lon/lat.
  4. Match each extracted polygon to the nearest real GWR building (by
     distance) to inherit its real attributes (EGID, baujahr, address...).
     GWR buildings with no nearby extracted polygon keep their old square
     approximation as a fallback. Extracted polygons with no nearby GWR
     point are kept too (likely real, unregistered structures) with null
     attributes.
"""
import json
import math
import os
import sys
import time
import urllib.request
import concurrent.futures
from pathlib import Path

import numpy as np
from PIL import Image
import cv2

ROOT = Path(__file__).resolve().parents[2]
BUILDINGS_PATH = ROOT / "data" / "work" / "building_polygons_baujahr.geojson"
BACKUP_PATH = ROOT / "data" / "work" / "building_polygons_baujahr.square_approx.geojson.bak"
TILE_CACHE = ROOT / "data" / "work" / "_tile_cache"
TILE_URL = "https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-farbe/default/current/3857/{z}/{x}/{y}.jpeg"
ZOOM = 18
TILE_SIZE = 256
MATCH_THRESHOLD_M = 20.0  # max distance to link an extracted polygon to a real GWR point


def deg2num_f(lat, lon, zoom):
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def num2deg(xtile, ytile, zoom):
    n = 2.0 ** zoom
    lon = xtile / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * ytile / n))))
    return lat, lon


def tile_pixel_to_lonlat(xt, yt, px, py, zoom):
    fx = xt + px / TILE_SIZE
    fy = yt + py / TILE_SIZE
    lat, lon = num2deg(fx, fy, zoom)
    return lon, lat


def centroid(ring):
    pts = ring[:-1] if ring[0] == ring[-1] else ring
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def load_existing_buildings():
    d = json.loads(BUILDINGS_PATH.read_text())
    return d["features"]


def tiles_with_buildings(features, zoom):
    tiles = set()
    for f in features:
        lon, lat = centroid(f["geometry"]["coordinates"][0])
        x, y = deg2num_f(lat, lon, zoom)
        tiles.add((int(x), int(y)))
    return tiles


def download_tile(xy):
    x, y = xy
    out = TILE_CACHE / f"{x}_{y}.jpeg"
    if out.exists() and out.stat().st_size > 0:
        return xy, True
    url = TILE_URL.format(z=ZOOM, x=x, y=y)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                out.write_bytes(resp.read())
            return xy, True
        except Exception:
            time.sleep(1)
    return xy, False


def extract_polygons_from_tile(xy):
    x, y = xy
    path = TILE_CACHE / f"{x}_{y}.jpeg"
    if not path.exists():
        return []
    try:
        im = Image.open(path).convert("RGB")
    except Exception:
        return []
    arr = np.array(im)
    mask = ((arr[:, :, 0] < 70) & (arr[:, :, 1] < 70) & (arr[:, :, 2] < 70)).astype(np.uint8) * 255

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    polys = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < 30:  # drop text-character-sized noise
            continue
        bx, by, bw, bh = cv2.boundingRect(c)
        if min(bw, bh) < 4:  # drop thin lines
            continue
        hull = cv2.convexHull(c)
        hull_area = cv2.contourArea(hull)
        if hull_area <= 0 or area / hull_area < 0.45:  # drop stringy text blobs
            continue
        eps = 0.8
        approx = cv2.approxPolyDP(c, eps, True)
        if len(approx) < 3:
            continue
        ring = []
        for pt in approx.reshape(-1, 2):
            lon, lat = tile_pixel_to_lonlat(x, y, float(pt[0]), float(pt[1]), ZOOM)
            ring.append([lon, lat])
        ring.append(ring[0])
        polys.append(ring)
    return polys


class GridIndex:
    """Coarse lon/lat bucket index for nearest-neighbour matching."""

    def __init__(self, features, cell_deg=0.0007):
        self.cell = cell_deg
        self.buckets = {}
        for f in features:
            lon, lat = centroid(f["geometry"]["coordinates"][0])
            key = (round(lon / cell_deg), round(lat / cell_deg))
            self.buckets.setdefault(key, []).append((lon, lat, f))

    def nearest(self, lon, lat, max_dist_m):
        key = (round(lon / self.cell), round(lat / self.cell))
        best, best_d = None, max_dist_m
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for blon, blat, f in self.buckets.get((key[0] + dx, key[1] + dy), []):
                    dlat_m = (blat - lat) * 111320.0
                    dlon_m = (blon - lon) * 111320.0 * math.cos(math.radians(lat))
                    d = math.hypot(dlat_m, dlon_m)
                    if d < best_d:
                        best, best_d = f, d
        return best


def main():
    TILE_CACHE.mkdir(exist_ok=True)
    print("Loading existing (square-approx) buildings...")
    existing = load_existing_buildings()
    print(f"  {len(existing)} known real GWR buildings")

    tiles = sorted(tiles_with_buildings(existing, ZOOM))
    print(f"Need {len(tiles)} z={ZOOM} tiles covering real building locations")

    print("Downloading tiles (public swisstopo Pixelkarte, no API key)...")
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        for xy, ok in ex.map(download_tile, tiles):
            done += 1
            if done % 1000 == 0:
                print(f"  ...{done}/{len(tiles)} tiles downloaded")
    print(f"Download complete: {done}/{len(tiles)}")

    print("Extracting building contours from tiles...")
    all_rings = []
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for rings in ex.map(extract_polygons_from_tile, tiles):
            all_rings.extend(rings)
            done += 1
            if done % 1000 == 0:
                print(f"  ...{done}/{len(tiles)} tiles processed, {len(all_rings)} polygons so far")
    print(f"Extracted {len(all_rings)} raw building polygons from imagery")

    print("Matching extracted polygons to real GWR attributes...")
    index = GridIndex(existing)
    matched_egids = set()
    new_features = []
    unmatched_count = 0
    for ring in all_rings:
        lon, lat = centroid(ring)
        match = index.nearest(lon, lat, MATCH_THRESHOLD_M)
        if match:
            props = dict(match["properties"])
            egid = props.get("egid")
            if egid in matched_egids:
                # already claimed by a closer/earlier polygon -- keep as unmatched extra shape
                props = {"egid": None, "address": None, "baujahr": None, "era": "unknown",
                         "geometry_type": "extracted_unmatched_duplicate",
                         "source": "swisstopo Pixelkarte raster extraction (live)"}
            else:
                matched_egids.add(egid)
                props["geometry_type"] = "extracted_from_raster_tiles"
                props["source"] = "swisstopo Pixelkarte raster extraction (live), matched to GWR"
        else:
            unmatched_count += 1
            props = {"egid": None, "address": None, "baujahr": None, "era": "unknown",
                      "geometry_type": "extracted_unmatched_no_gwr",
                      "source": "swisstopo Pixelkarte raster extraction (live), no nearby GWR point"}
        new_features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": props,
        })

    # GWR buildings whose polygon never got replaced keep their square approximation
    fallback = [f for f in existing if f["properties"].get("egid") not in matched_egids]
    print(f"  {len(matched_egids)} GWR buildings upgraded to real traced shapes")
    print(f"  {len(fallback)} GWR buildings kept as square approximation (no raster match)")
    print(f"  {unmatched_count} extracted shapes kept with no GWR match (possibly unregistered structures)")

    final = new_features + fallback
    print(f"Writing {len(final)} total building features...")

    if not BACKUP_PATH.exists():
        BACKUP_PATH.write_text(BUILDINGS_PATH.read_text())
        print(f"  backed up prior square-approx version -> {BACKUP_PATH}")

    BUILDINGS_PATH.write_text(json.dumps({"type": "FeatureCollection", "features": final}))
    print(f"Done -> {BUILDINGS_PATH}")


if __name__ == "__main__":
    main()
