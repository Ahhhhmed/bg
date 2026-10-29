#!/usr/bin/env python3
"""Belgrade's public transport: the stops on the map and every stop's
commute profile to Trg Republike over a weekday (the stop card), as Zürich's
build_timetable.py does for Zürich HB.

Sources (data.gov.rs, Serbian open data licence, attribution):
  - "Gradski javni prevoz u Beogradu - GTFS" (Sekretarijat za javni prevoz):
    bus, tram and trolleybus lines of the city.
  - "Prigradski javni prevoz u Beogradu - GTFS": the suburban buses.
  The two feeds share their stop ids (20001 = Kalemegdan in both) and their
  service ids (RD = weekdays); trips and routes get a feed prefix. City rail
  (BG Voz) is not in GTFS and not included.

  python3 cities/belgrade/pipeline/build_transit.py [--date YYYYMMDD]

Steps:
  1. The service day: the next Tuesday (or --date) and its services.
  2. Stops of both feeds within REGION_KM of the area (journeys may leave it).
  3. Connections: consecutive stops of every trip running that day.
  4. The profile scan to Trg Republike (shared/pipeline/transit_profiles.py):
     every stop within TARGET_M of the square walks there (straight line x
     1.3 at 80 m/min); walks between stops up to FOOT_M (the feeds have no
     transfers.txt); 2 min to change.
  5. Per stop in the area: the card data -> data/stops/<id>.json, and
     data/layers/stops.geojson (name, nr, kind, modes, cat, hb_mean / hb_min /
     hb_takt of the morning: the same property names as Zürich's, "hb" is the
     city's commute target).
Then shared/pipeline/walk.py belgrade and the tiles.
"""
import argparse
import collections
import csv
import datetime as dt
import io
import json
import math
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
CITY = HERE.parent
ROOT = CITY.parent.parent
sys.path.insert(0, str(ROOT / "shared" / "pipeline"))
import transit_profiles as tp  # noqa: E402

SRC = CITY / "data" / "src" / "gtfs"
LAYERS = CITY / "data" / "layers"
STOPS_OUT = CITY / "data" / "stops"
FEEDS = {
    "c": "https://data.gov.rs/s/resources/gradski-javni-prevoz-u-beogradu-gtfs/20251031-111721/bgprev-belgrade-rs-2-.zip",
    "s": "https://data.gov.rs/s/resources/prigradski-javni-prevoz-u-u-beogradu-gtfs/20250701-155403/gtfs-prigrad.zip",
}
FEED_FILES = {"c": "city.zip", "s": "suburban.zip"}
TARGET = (20.4603, 44.8163)    # Trg Republike (lon, lat): the owner's "Zürich HB" of Belgrade
TARGET_NAME = "Trg Republike"
TARGET_M = 400          # stops this close to the square walk there
REGION_KM = 5
FOOT_M = 400
WALK_M_PER_MIN = 80.0
DETOUR = 1.3
DAY = (4 * 3600, 26 * 3600)
CURVE = (5 * 3600, 24 * 3600 + 30 * 60)
PARTS = {
    "early": (5 * 3600, 6 * 3600 + 30 * 60),
    "morning": (6 * 3600 + 30 * 60, 9 * 3600),
    "day": (9 * 3600, 16 * 3600),
    "evening": (16 * 3600, 19 * 3600),
    "night": (19 * 3600, 24 * 3600 + 30 * 60),
}
MODE = {0: "tram", 1: "metro", 2: "train", 3: "bus", 11: "bus", 700: "bus", 800: "bus", 900: "tram"}
MODE_ORDER = ["train", "metro", "tram", "bus"]


def log(msg):
    print(msg, flush=True)


def secs(hms):
    h, m, s = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def dist_m(lat1, lon1, lat2, lon2):
    k = 111_320.0
    return math.hypot((lat2 - lat1) * k, (lon2 - lon1) * k * math.cos(math.radians((lat1 + lat2) / 2)))


def open_csv(z, name):
    return csv.DictReader(io.TextIOWrapper(z.open(name), "utf-8-sig"))


def next_tuesday(today=None):
    today = today or dt.date.today()
    return today + dt.timedelta(days=(1 - today.weekday()) % 7 or 7)


def download():
    SRC.mkdir(parents=True, exist_ok=True)
    for k, url in FEEDS.items():
        f = SRC / FEED_FILES[k]
        if not f.exists():
            log(f"Downloading {url} ...")
            urllib.request.urlretrieve(url, f)


def services_on(z, day):
    ymd = day.strftime("%Y%m%d")
    wd = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][day.weekday()]
    on = {r["service_id"] for r in open_csv(z, "calendar.txt")
          if r[wd] == "1" and r["start_date"] <= ymd <= r["end_date"]}
    for r in open_csv(z, "calendar_dates.txt"):
        if r["date"] == ymd:
            (on.add if r["exception_type"] == "1" else on.discard)(r["service_id"])
    return on


def area():
    feats = json.loads((LAYERS / "municipalities.geojson").read_text())["features"]
    return unary_union([shape(f["geometry"]) for f in feats if f["properties"].get("level") == "municipality"])


def extract(day, region):
    minx, miny, maxx, maxy = region
    stations, routes, trips, conns = {}, {}, {}, []
    for k, fn in FEED_FILES.items():
        z = zipfile.ZipFile(SRC / fn)
        on = services_on(z, day)
        for r in open_csv(z, "stops.txt"):
            lat, lon = float(r["stop_lat"]), float(r["stop_lon"])
            if minx <= lon <= maxx and miny <= lat <= maxy:
                stations.setdefault(r["stop_id"], {"name": r["stop_name"].strip(), "lat": lat, "lon": lon})
        for r in open_csv(z, "routes.txt"):
            routes[f"{k}:{r['route_id']}"] = (r["route_short_name"], int(r["route_type"]),
                                              (r["route_color"] or "").upper(), (r["route_text_color"] or "").upper())
        ktrips = {}
        for r in open_csv(z, "trips.txt"):
            if r["service_id"] in on:
                ktrips[r["trip_id"]] = (f"{k}:{r['route_id']}", r["trip_headsign"])
        rows_by_trip = collections.defaultdict(list)
        for r in open_csv(z, "stop_times.txt"):
            if r["trip_id"] in ktrips:
                a, d = r["arrival_time"] or r["departure_time"], r["departure_time"] or r["arrival_time"]
                if a:
                    rows_by_trip[r["trip_id"]].append((int(r["stop_sequence"]), r["stop_id"], secs(a), secs(d)))
        n0 = len(conns)
        for tid, rows in rows_by_trip.items():
            rows.sort()
            made = False
            for (_, s1, a1, d1), (_, s2, a2, d2) in zip(rows, rows[1:]):
                if s1 in stations and s2 in stations and s1 != s2 and DAY[0] <= d1 <= DAY[1]:
                    conns.append((d1, a2, s1, s2, f"{k}:{tid}"))
                    made = True
            if made:
                trips[f"{k}:{tid}"] = ktrips[tid]
        log(f"  feed {fn}: {len(on)} services, {len(ktrips)} trips today, {len(conns) - n0} connections")
    used = {r for r, _ in trips.values()}
    return {"day": day.isoformat(), "stations": stations, "routes": {r: routes[r] for r in used},
            "trips": trips, "connections": conns}


def label(route):
    name, rtype, color, text = route
    return (name or "?", MODE.get(rtype, "bus"), color, text)


def profiles(data):
    stations = data["stations"]
    ids = sorted(stations)
    idx = {s: i for i, s in enumerate(ids)}
    trip_ix, conns = {}, []
    for d, a, u, v, trip in data["connections"]:
        conns.append((d, a, idx[u], idx[v], trip_ix.setdefault(trip, len(trip_ix))))
    foot = collections.defaultdict(dict)
    cell = collections.defaultdict(list)
    for s in ids:
        st = stations[s]
        cell[(int(st["lat"] / 0.0036), int(st["lon"] / 0.0051))].append(s)
    for s in ids:
        st = stations[s]
        ci, cj = int(st["lat"] / 0.0036), int(st["lon"] / 0.0051)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for o in cell[(ci + di, cj + dj)]:
                    if o != s:
                        d = dist_m(st["lat"], st["lon"], stations[o]["lat"], stations[o]["lon"])
                        if d <= FOOT_M:
                            foot[idx[s]][idx[o]] = int(d * DETOUR / WALK_M_PER_MIN * 60) + 60
    footpaths = {k: sorted(v.items(), key=lambda kv: kv[1]) for k, v in foot.items()}
    target = {}
    for s in ids:
        d = dist_m(TARGET[1], TARGET[0], stations[s]["lat"], stations[s]["lon"])
        if d <= TARGET_M:
            target[idx[s]] = int(d * DETOUR / WALK_M_PER_MIN * 60)
    log(f"Profile scan: {len(conns)} connections, {len(ids)} stops, {len(target)} stops at {TARGET_NAME} ...")
    t0 = time.time()
    profs = tp.profile_scan(conns, len(ids), target, footpaths)
    log(f"  done in {time.time() - t0:.0f} s")
    return {"ids": ids, "idx": idx, "profs": profs, "footpaths": footpaths, "trip_names": list(trip_ix),
            "target": target}


def stop_output(sid, P, data):
    i = P["idx"][sid]
    deps, arrs, refs = tp.origin_profile(i, P["profs"], P["footpaths"])
    if not deps and i not in P["target"]:
        return None
    routes, trips = data["routes"], data["trips"]
    labels, label_ix = [], {}

    def lab(trip_name):
        key = label(routes[trips[trip_name][0]])
        if key not in label_ix:
            label_ix[key] = len(labels)
            labels.append(key)
        return label_ix[key]

    out_dep, out_arr, out_ntr, out_legs, out_walk = [], [], [], [], []
    for d, a, (stop, k, walk) in zip(deps, arrs, refs):
        if not (DAY[0] <= d <= DAY[1]):
            continue
        legs = tp.journey(P["profs"], stop, k)
        out_dep.append(round(d / 60, 1))
        out_arr.append(round(a / 60, 1))
        out_ntr.append(P["profs"][stop].ntr[k])
        out_legs.append([[lab(P["trip_names"][t]), round(t_off / 60, 1), P["ids"][alight]]
                         for t, _, _, alight, t_off in legs])
        out_walk.append([P["ids"][stop], round(walk / 60)] if walk else None)
    parts = {}
    for name, (a0, a1) in PARTS.items():
        curve = tp.travel_curve(deps, arrs, a0, a1)
        st = tp.summarize(curve)
        parts[name] = {**(st or {}), "takt": tp.detect_takt(curve) if st else None}
    # a stop at the square: the walk there, all day
    if i in P["target"] and not deps:
        w = round(P["target"][i] / 60, 1)
        parts = {n: {"min": w, "mean": w, "max": w, "takt": None} for n in PARTS}
    curve = tp.travel_curve(deps, arrs, *CURVE)
    serving = collections.Counter()
    for d, a, u, v, trip in data["connections"]:
        if u == sid:
            serving[label(routes[trips[trip][0]])] += 1
    lines = [[n, m, c, tc, cnt] for (n, m, c, tc), cnt in
             sorted(serving.items(), key=lambda kv: (MODE_ORDER.index(kv[0][1]) if kv[0][1] in MODE_ORDER else 9,
                                                      len(kv[0][0]), kv[0][0]))]
    names = {s: data["stations"][s]["name"] for legs in out_legs for _, _, s in legs}
    names.update({w[0]: data["stations"][w[0]]["name"] for w in out_walk if w})
    return {"nr": int(sid), "feed_station": None, "day": data["day"], "dep": out_dep, "arr": out_arr, "ntr": out_ntr,
            "legs": out_legs, "walk": out_walk, "labels": labels, "stops": names, "parts": parts, "lines": lines,
            "curve_start": CURVE[0] // 60,
            "curve": [None if c is None else round(c / 60, 1) for c in curve[::2]],
            "at_hb": i in P["target"] and P["target"][i] == 0}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", help="service day YYYYMMDD (default: next Tuesday)")
    args = ap.parse_args()
    day = dt.datetime.strptime(args.date, "%Y%m%d").date() if args.date else next_tuesday()
    download()
    poly = area()
    minx, miny, maxx, maxy = poly.bounds
    dlat, dlon = REGION_KM / 111.32, REGION_KM / (111.32 * math.cos(math.radians((miny + maxy) / 2)))
    log(f"{day} ({day:%A})")
    data = extract(day, (minx - dlon, miny - dlat, maxx + dlon, maxy + dlat))
    P = profiles(data)
    STOPS_OUT.mkdir(parents=True, exist_ok=True)
    for f in STOPS_OUT.glob("*.json"):
        f.unlink()
    deps = collections.Counter(u for _, _, u, _, _ in data["connections"])
    modes = collections.defaultdict(set)
    for d, a, u, v, trip in data["connections"]:
        modes[u].add(label(data["routes"][data["trips"][trip][0]])[1])
    feats, got, takts = [], 0, collections.Counter()
    for sid in sorted(data["stations"], key=int):
        st = data["stations"][sid]
        if not deps.get(sid) or not poly.contains(Point(st["lon"], st["lat"])):
            continue
        ms = sorted(modes[sid], key=lambda m: MODE_ORDER.index(m) if m in MODE_ORDER else 9)
        n = deps[sid]
        p = {"name": st["name"], "nr": int(sid), "kind": ms[0], "modes": ",".join(ms),
             "cat": 1 if n >= 400 else 2 if n >= 150 else 3, "hub": False}
        o = stop_output(sid, P, data)
        if o:
            got += 1
            (STOPS_OUT / f"{sid}.json").write_text(json.dumps(o, ensure_ascii=False, separators=(",", ":")))
            m = o["parts"]["morning"]
            if m.get("mean") is not None:
                p["hb_mean"], p["hb_min"], p["hb_takt"] = m["mean"], m["min"], m["takt"]
            takts[m.get("takt")] += 1
        feats.append({"type": "Feature", "properties": p,
                      "geometry": {"type": "Point", "coordinates": [round(st["lon"], 6), round(st["lat"], 6)]}})
    (LAYERS / "stops.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    # the cards' sources (data/card_sources.json, written by build_layers.py): the stops, the timetable,
    # the commute and walks of shared/pipeline/walk.py (run next)
    cs_path = CITY / "data" / "card_sources.json"
    cs = json.loads(cs_path.read_text())
    gtfs = {"de": "Sekretarijat za javni prevoz, Fahrplan (GTFS, Stadt + Vororte)",
            "en": "Sekretarijat za javni prevoz, timetable (GTFS, city + suburban)",
            "url": "https://data.gov.rs/sr/datasets/gradski-javni-prevoz-u-beogradu-gtfs/", "date": "2025-10-31"}
    cs["stop"] = {"gtfs": gtfs}
    cs["building"]["commute"] = {**gtfs, "de": gtfs["de"] + ", Zeit zum Trg Republike geschätzt",
                                 "en": gtfs["en"] + ", time to Trg Republike estimated"}
    release = (CITY / "data" / "src" / "RELEASE").read_text().strip()
    cs["building"]["walk"] = {"de": f"OpenStreetMap, Strassen und Wege (Overture {release}; Fusswege berechnet)",
                              "en": f"OpenStreetMap, roads and paths (Overture {release}; walks computed)",
                              "url": "https://docs.overturemaps.org/attribution/", "date": dt.date.today().isoformat()}
    cs_path.write_text(json.dumps(cs, ensure_ascii=False, indent=1))
    size = sum(f.stat().st_size for f in STOPS_OUT.glob("*.json"))
    log(f"{len(feats)} stops in the area, {got} with a profile -> data/stops/ ({size / 1e6:.1f} MB); morning Takt: "
        + ", ".join(f"{k}: {v}" for k, v in sorted(takts.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))))


if __name__ == "__main__":
    main()
