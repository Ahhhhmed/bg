#!/usr/bin/env python3
"""Belgrade's air-quality stations as a place layer (places_air.geojson):
every monitoring station inside the area, with
  - the mean of the last 30 days' hourly values per pollutant (PM10, PM2.5,
    NO2, O3), preliminary (not yet verified by SEPA);
  - for the stations SEPA has verified, the 2024 annual means (PM10, PM2.5,
    NO2) from its verified daily values.

Sources (both SEPA, Agencija za zaštitu životne sredine):
  - opendata.kosava.cloud (SEPA's HVD open data API, linked from data.gov.rs
    "Kvalitet vazduha - satne vrednosti"): the stations (coordinates,
    network) and the bulk parquet of the last 30 days, all networks (SEPA's
    state network and the city's GZZJZ network).
  - data.gov.rs "Kvalitet vazduha" 2024.xlsx: verified daily means, one sheet
    per pollutant, one column per station. A column is joined to a station
    by the station's name as both SEPA datasets write it (the column header
    minus SEPA's sheet suffixes "AOP NO2" / "_8h"); unmatched columns are
    listed and left out.

  python3 cities/belgrade/pipeline/build_air.py      # then walk.py and the tiles

A mean needs MIN_SHARE of its period's values (hours / days); else no value.
"""
import collections
import datetime as dt
import json
import re
import sys
import urllib.request
from pathlib import Path

import openpyxl
import pyarrow.parquet as pq
from shapely.geometry import Point, shape
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
CITY = HERE.parent
SRC = CITY / "data" / "src" / "air"
LAYERS = CITY / "data" / "layers"
API = "https://opendata.kosava.cloud"
VERIFIED = ("2024", "https://data.gov.rs/s/resources/kvalitet-vazdukha/20260316-080003/2024.xlsx")
POLLUTANTS = {"PM10": "pm10", "PM2.5": "pm25", "NO2": "no2", "O3": "o3"}
SHEETS = {"PM10": "2024-PM10", "PM2.5": "2024-PM2.5", "NO2": "2024-NO2"}
MIN_SHARE = 0.75


def fetch(refresh=False):
    SRC.mkdir(parents=True, exist_ok=True)
    files = {"stations.json": f"{API}/api/v1/stations", "networks.json": f"{API}/networks",
             "bulk.json": f"{API}/api/v1/bulk",
             "obs30.parquet": f"{API}/api/v1/bulk/observations_hourly_preliminary_last30days.parquet",
             f"{VERIFIED[0]}.xlsx": VERIFIED[1]}
    for name, url in files.items():
        if refresh or not (SRC / name).exists():
            print(f"downloading {url}")
            urllib.request.urlretrieve(url, SRC / name)


def norm(name):
    return re.sub(r"\s+", " ", re.sub(r"(_8h|AOP NO2)\s*$", "", str(name))).strip()


def verified_means(names):
    """{station name: {pm10: mean, ...}} for the station names given."""
    wb = openpyxl.load_workbook(SRC / f"{VERIFIED[0]}.xlsx", read_only=True)
    out = collections.defaultdict(dict)
    unmatched = set()
    for pol, sheet in SHEETS.items():
        rows = list(wb[sheet].iter_rows(values_only=True))
        hdr, data = rows[0], [r for r in rows[1:] if r and r[0]]
        for j, h in enumerate(hdr[1:], 1):
            n = norm(h)
            if not n.startswith("Beograd"):
                continue
            if n not in names:
                unmatched.add(n)
                continue
            vals = [r[j] for r in data if isinstance(r[j], (int, float))]
            if len(vals) >= MIN_SHARE * len(data):
                out[n][POLLUTANTS[pol]] = round(sum(vals) / len(vals), 1)
    if unmatched:
        print(f"  verified columns without a station of that name (left out): {sorted(unmatched)}")
    return out


def main():
    fetch("--refresh" in sys.argv)
    feats = json.loads((LAYERS / "municipalities.geojson").read_text())["features"]
    area = unary_union([shape(f["geometry"]) for f in feats if f["properties"].get("level") == "municipality"])
    parts = [(f["properties"]["name"], shape(f["geometry"])) for f in feats if f["properties"].get("level") == "kreis"]
    networks = {n["network_code"]: n for n in json.loads((SRC / "networks.json").read_text())}
    stations = [s for s in json.loads((SRC / "stations.json").read_text())
                if area.contains(Point(s["longitude"], s["latitude"]))]
    ids = {s["station_id"] for s in stations}
    t = pq.read_table(SRC / "obs30.parquet", columns=["station_id", "parameter_code", "time_start_utc", "value"]).to_pylist()
    hours = sorted({r["time_start_utc"] for r in t})
    span = (hours[0].date().isoformat(), hours[-1].date().isoformat())
    vals = collections.defaultdict(list)
    for r in t:
        if r["station_id"] in ids and r["parameter_code"] in POLLUTANTS and r["value"] is not None and r["value"] >= 0:
            vals[(r["station_id"], r["parameter_code"])].append(r["value"])
    ver = verified_means({norm(s["station_name"]) for s in stations})
    snapshot = json.loads((SRC / "bulk.json").read_text())["generated_at_utc"][:10]
    out = []
    for s in sorted(stations, key=lambda s: int(s["station_id"])):
        pt = Point(s["longitude"], s["latitude"])
        net = networks.get(s["network_code"], {})
        p = {"pid": f"air{s['station_id']}", "kind": "air", "name": norm(s["station_name"]),
             "muni": next((n for n, g in parts if g.contains(pt)), None),
             "info": net.get("short_name"), "net": net.get("name"), "code": s["station_code"],
             "from": span[0], "to": span[1], "srcs": "sepa_live"}
        for pol, k in POLLUTANTS.items():
            v = vals.get((s["station_id"], pol), [])
            if len(v) >= MIN_SHARE * len(hours):
                p[f"{k}_30d"] = round(sum(v) / len(v), 1)
        v = ver.get(p["name"])
        if v:
            p.update({f"{k}_{VERIFIED[0]}": x for k, x in v.items()})
            p["srcs"] += ",sepa_verified"
        out.append({"type": "Feature", "properties": p,
                    "geometry": {"type": "Point", "coordinates": [round(s["longitude"], 6), round(s["latitude"], 6)]}})
    (LAYERS / "places_air.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": out}, ensure_ascii=False))
    # the card's sources (places_sources.json: one table per layer)
    ps_path = CITY / "data" / "places_sources.json"
    ps = json.loads(ps_path.read_text())
    ps["air"] = {
        "sepa_live": {"de": f"SEPA, Stundenwerte der letzten 30 Tage, vorläufig ({span[0]} – {span[1]})",
                      "en": f"SEPA, hourly values of the last 30 days, preliminary ({span[0]} – {span[1]})",
                      "sr": f"SEPA, satne vrednosti poslednjih 30 dana, neverifikovano ({span[0]} – {span[1]})",
                      "url": "https://data.gov.rs/sr/datasets/kvalitet-vazduha-satne-vrednosti-neverifikovani-podaci-poslednjih-30-dana/",
                      "date": snapshot},
        "sepa_verified": {"de": f"SEPA, verifizierte Tageswerte {VERIFIED[0]}", "en": f"SEPA, verified daily values {VERIFIED[0]}",
                          "sr": f"SEPA, verifikovane dnevne vrednosti {VERIFIED[0]}",
                          "url": "https://data.gov.rs/sr/datasets/kvalitet-vazdukha/", "date": "2026-03-16"},
    }
    ps_path.write_text(json.dumps(ps, ensure_ascii=False, indent=1))
    n30 = sum(1 for f in out if any(k.endswith("_30d") for k in f["properties"]))
    nv = sum(1 for f in out if "sepa_verified" in f["properties"]["srcs"])
    print(f"{len(out)} stations in the area ({n30} with 30-day means {span[0]}..{span[1]}, {nv} with verified {VERIFIED[0]} means)")


if __name__ == "__main__":
    main()
