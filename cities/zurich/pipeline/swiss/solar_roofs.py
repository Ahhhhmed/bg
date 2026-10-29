"""
Roof facets of BFE's solar-roof suitability (ch.bfe.solarenergie-eignung-daecher,
"Sonnendach") for the map area, from the national GeoPackage on
data.geo.admin.ch instead of the geo.admin `identify` API.

Why: the facet layer is so dense that tiling the area through `identify`
(201 results per request) didn't finish in 2 h (~370k facets, 2026-10-13),
which left the lake towns without solar values. The national GeoPackage
(SOLKAT_DACH.gpkg, 1.5 GB zipped / 4.6 GB, Deflate64) downloads in ~1-2 min,
extracts in ~1.5 min, and an R-tree query gives the area's facets in seconds.
Same data as the API: DF_UID = the API's featureId, identical stromertrag,
flaeche_kollektoren, ausrichtung, klasse, gwr_egid (checked 2026-10-19).

`load_facets()` returns records shaped like geoadmin_tiles.fetch_layer's
geojson results (`featureId`, `properties` with the API's lower-case names,
`geometry` as WGS84 GeoJSON), so build_roof_footprints.py and
enrich_building_properties.py use them unchanged. Two API fields aren't in
the file and are derived exactly as the API does:
  - finanzertrag = stromertrag * 0.10 (CHF; the API's ratio for every facet)
  - klasse_text  = the API's "Gering##Faible##..." string for klasse 1-5

Needs `unzip` (Info-ZIP 6, with Deflate64; Python's zipfile can't read it).
The zip and the .gpkg live in data/work/_solar_cache/ (gitignored).
"""
import hashlib
import json
import sqlite3
import struct
import subprocess
import sys
import urllib.request
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer
from shapely import wkb
from shapely.geometry import box, mapping
from shapely.prepared import prep

sys.path.insert(0, str(Path(__file__).parent))

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "data" / "work" / "_solar_cache"
FACETS_CACHE = ROOT / "data" / "work" / "_roof_facets_cache.json"

COLLECTION = "ch.bfe.solarenergie-eignung-daecher"
STAC_ITEM = f"https://data.geo.admin.ch/api/stac/v1/collections/{COLLECTION}/items/solarenergie-eignung-daecher"
ASSET = "solarenergie-eignung-daecher_2056.gpkg.zip"
GPKG_NAME = "SOLKAT_DACH.gpkg"
TABLE = "SOLKAT_CH_DACH"

# the API's klasse_text per klasse (de##fr##it##en##rm); the code keeps only the German part
KLASSE_TEXT = {
    1: "Gering##Faible##Bassa##Low##Gering",
    2: "Mittel##Moyenne##Media##Mean##Mittel",
    3: "Gut##Bonne##Buona##Good##Gut",
    4: "Sehr gut##Trés bonne##Molto buona##Very good##Sehr gut",
    5: "Top##Top##Top##Top##Top",
}
TARIFF_CHF_PER_KWH = 0.10  # API finanzertrag / stromertrag, identical for every facet

_TO_LV95 = Transformer.from_crs("EPSG:4326", "EPSG:2056", always_xy=True)
_TO_WGS84 = Transformer.from_crs("EPSG:2056", "EPSG:4326", always_xy=True)


def _reproject(geom, transformer):
    return shapely.transform(geom, lambda c: np.column_stack(transformer.transform(c[:, 0], c[:, 1])))


def _asset():
    """(href, sha256 hex) of the GeoPackage zip from the STAC item."""
    with urllib.request.urlopen(STAC_ITEM, timeout=60) as r:
        item = json.loads(r.read())
    a = item["assets"][ASSET]
    mh = a.get("file:checksum") or a.get("checksum:multihash")
    if not mh or not mh.startswith("1220"):
        raise RuntimeError(f"unexpected checksum format in STAC item: {mh!r}")
    return a["href"], mh[4:]


def _download(url, dest, sha256):
    """Resumable download (HTTP Range), then SHA-256 check against STAC."""
    head = urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60)
    total = int(head.headers["Content-Length"])
    for attempt in range(6):
        have = dest.stat().st_size if dest.exists() else 0
        if have >= total:
            break
        print(f"[solar] downloading {url} ({have / 1e6:.0f} / {total / 1e6:.0f} MB)...")
        try:
            req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"})
            with urllib.request.urlopen(req, timeout=120) as r, open(dest, "ab") as fh:
                while chunk := r.read(1 << 22):
                    fh.write(chunk)
        except Exception as e:  # resume from where it stopped
            print(f"[solar]   interrupted ({e}), retrying")
    if dest.stat().st_size != total:
        raise RuntimeError(f"{dest} is {dest.stat().st_size} bytes, expected {total}; re-run to resume")
    h = hashlib.sha256()
    with open(dest, "rb") as fh:
        while chunk := fh.read(1 << 24):
            h.update(chunk)
    if h.hexdigest() != sha256:
        dest.unlink()
        raise RuntimeError(f"checksum mismatch for {dest} (deleted); re-run to download again")
    print(f"[solar]   {dest.name}: {total / 1e6:.0f} MB, sha256 ok")


def ensure_gpkg():
    """Path of the extracted national GeoPackage, downloading / extracting if needed."""
    gpkg = CACHE_DIR / GPKG_NAME
    if gpkg.exists():
        return gpkg
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    url, sha = _asset()
    z = CACHE_DIR / ASSET
    _download(url, z, sha)
    print(f"[solar] extracting {GPKG_NAME} (Deflate64, ~4.6 GB, ~1.5 min)...")
    tmp = CACHE_DIR / "_extract"
    tmp.mkdir(exist_ok=True)
    subprocess.run(["unzip", "-o", "-q", str(z), GPKG_NAME, "-d", str(tmp)], check=True)
    (tmp / GPKG_NAME).rename(gpkg)
    tmp.rmdir()
    z.unlink()  # 1.5 GB; the .gpkg is all we read
    return gpkg


def _gpkg_geom(blob):
    """GeoPackage geometry blob -> shapely (header + envelope, then WKB)."""
    flags = blob[3]
    env = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[(flags >> 1) & 7]
    return wkb.loads(bytes(blob[8 + env:]))


def load_facets(region_wgs84):
    """All roof facets whose outline touches `region_wgs84` (shapely, WGS84)."""
    gpkg = ensure_gpkg()
    region = _reproject(region_wgs84, _TO_LV95)
    region_p = prep(region)
    xmin, ymin, xmax, ymax = region.bounds
    con = sqlite3.connect(f"file:{gpkg}?mode=ro", uri=True)
    rows = con.execute(
        f"""SELECT t.DF_UID, t.geom, t.GWR_EGID, t.STROMERTRAG, t.FLAECHE_KOLLEKTOREN, t.KLASSE,
                   t.AUSRICHTUNG, t.NEIGUNG, t.FLAECHE, t.DF_NUMMER
            FROM {TABLE} t JOIN rtree_{TABLE}_geom r ON t.objectid = r.id
            WHERE r.maxx >= ? AND r.minx <= ? AND r.maxy >= ? AND r.miny <= ?""",
        (xmin, xmax, ymin, ymax))
    out, scanned = [], 0
    for uid, blob, egid, strom, kollekt, klasse, ausr, neig, flaeche, nr in rows:
        scanned += 1
        if blob is None:
            continue
        g = _gpkg_geom(blob)
        if not region_p.intersects(box(*g.bounds)) or not region_p.intersects(g):
            continue
        g = _reproject(g, _TO_WGS84)
        out.append({
            "featureId": uid,
            "id": uid,
            "properties": {
                "gwr_egid": egid,
                "stromertrag": strom,
                "flaeche_kollektoren": kollekt,
                "finanzertrag": round((strom or 0) * TARIFF_CHF_PER_KWH, 1),
                "klasse": klasse,
                "klasse_text": KLASSE_TEXT.get(klasse),
                "ausrichtung": ausr,
                "neigung": neig,
                "flaeche": flaeche,
                "df_nummer": nr,
            },
            "geometry": mapping(g),
        })
        if scanned % 100000 == 0:
            print(f"[solar]   ...{scanned} facets scanned in the bbox, {len(out)} in the area")
    con.close()
    print(f"[solar] {len(out)} roof facets in the area ({scanned} in its bbox)")
    if not out:
        raise RuntimeError("no roof facets found for the area -- wrong region or broken GeoPackage")
    return out


def facets_cached(region_wgs84):
    """The area's facets from _roof_facets_cache.json, building it from the GeoPackage if missing."""
    if FACETS_CACHE.exists():
        print(f"Loading cached roof facets from {FACETS_CACHE} (delete it to rebuild)...")
        return json.loads(FACETS_CACHE.read_text())
    facets = load_facets(region_wgs84)
    FACETS_CACHE.write_text(json.dumps(facets))
    print(f"  cached {len(facets)} facets -> {FACETS_CACHE}")
    return facets


if __name__ == "__main__":
    from area import area_polygon
    FACETS_CACHE.unlink(missing_ok=True)
    facets_cached(area_polygon().buffer(0.002))
