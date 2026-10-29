"""
The public-transport timetable for the map area, and every stop's commute
profile to Zürich HB over a weekday.

Source: the Swiss GTFS feed from geOps (https://gtfs.geops.ch/dl/gtfs_complete.zip,
converted daily from the official HAFAS timetable on opentransportdata.swiss:
all operators, S-Bahn, tram, bus, boat, funicular; ~220 MB zipped, stop_times
2 GB unzipped, streamed). Cached in data/work/_gtfs_cache/ (gitignored).

Steps:
  1. The service day: the next Tuesday (or --date YYYYMMDD) and the services
     running on it (calendar + calendar_dates).
  2. Stations: GTFS platforms ("8503000:7") collapse to their station
     ("8503000" = the BAV stop number `nr` of transit_stops.geojson). Kept:
     stations within REGION_KM of the area, so journeys that leave the area on
     the way to HB still count.
  3. Connections: consecutive stops of every trip running that day, both in
     the region (frequencies.txt trips expanded). Cached per day.
  4. Profiles: transit_profiles.profile_scan() to Zürich HB (station 8503000;
     stops within TARGET_M walk there), with the feed's transfer times
     between stations plus walks of up to FOOT_M straight line x 1.3 at
     80 m/min.
  5. Per stop of transit_stops.geojson: the Pareto departures of the day with
     their arrival, transfers and lines, the travel-time sawtooth's cycle
     (Takt) and min / mean / max per part of the day, and the lines serving
     the stop. -> data/work/stop_profiles.json (one file, read by the
     build into one small JSON per stop for the stop card; see
     assemble.py) and a summary onto transit_stops.geojson.

  python3 cities/zurich/pipeline/swiss/build_timetable.py [--date YYYYMMDD] [--refresh]

Then shared/build_tiles.sh zurich (the stop summaries go into the `stops` layer).
"""
import argparse
import collections
import csv
import datetime as dt
import gzip
import io
import json
import math
import pickle
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import transit_profiles as tp  # noqa: E402
from area import area_polygon  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LAYERS = ROOT / "data" / "work"
CACHE = LAYERS / "_gtfs_cache"
FEED_URL = "https://gtfs.geops.ch/dl/gtfs_complete.zip"
FEED = CACHE / "gtfs_complete.zip"
STOPS = LAYERS / "transit_stops.geojson"
OUT = LAYERS / "stop_profiles.json"

HB = "8503000"
REGION_KM = 15          # stations kept around the area (journeys may leave it)
TARGET_M = 500          # stops this close to HB walk there instead
FOOT_M = 400            # walks between stations (where the feed has no transfer)
WALK_M_PER_MIN = 80.0
DETOUR = 1.3
DAY = (4 * 3600, 26 * 3600)          # departures considered (GTFS times run past 24 h)
CURVE = (5 * 3600, 24 * 3600 + 30 * 60)  # the sawtooth on the card: 05:00-00:30
PARTS = {               # parts of the day for the Takt and the stats
    "early": (5 * 3600, 6 * 3600 + 30 * 60),
    "morning": (6 * 3600 + 30 * 60, 9 * 3600),
    "day": (9 * 3600, 16 * 3600),
    "evening": (16 * 3600, 19 * 3600),
    "night": (19 * 3600, 24 * 3600 + 30 * 60),
}
MODE = {0: "tram", 1: "metro", 2: "train", 3: "bus", 4: "boat", 5: "cable", 6: "cable", 7: "funicular",
        100: "train", 102: "train", 103: "train", 106: "train", 109: "train", 117: "train",
        400: "metro", 700: "bus", 704: "bus", 715: "bus", 900: "tram", 1000: "boat", 1300: "cable",
        1400: "funicular"}


def log(msg):
    print(msg, flush=True)


def secs(hms):
    h, m, s = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def station(stop_id):
    return stop_id.split(":")[0]


def dist_m(lat1, lon1, lat2, lon2):
    k = 111_320.0
    return math.hypot((lat2 - lat1) * k, (lon2 - lon1) * k * math.cos(math.radians((lat1 + lat2) / 2)))


def open_csv(z, name):
    return csv.DictReader(io.TextIOWrapper(z.open(name), "utf-8-sig"))


def next_tuesday(today=None):
    today = today or dt.date.today()
    return today + dt.timedelta(days=(1 - today.weekday()) % 7 or 7)


def download(refresh):
    CACHE.mkdir(exist_ok=True)
    if FEED.exists() and not refresh:
        return
    log(f"Downloading {FEED_URL} ...")
    tmp = FEED.with_suffix(".part")
    with urllib.request.urlopen(FEED_URL, timeout=600) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.rename(FEED)


def services_on(z, day):
    ymd = day.strftime("%Y%m%d")
    wd = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][day.weekday()]
    on = {r["service_id"] for r in open_csv(z, "calendar.txt")
          if r[wd] == "1" and r["start_date"] <= ymd <= r["end_date"]}
    for r in open_csv(z, "calendar_dates.txt"):
        if r["date"] == ymd:
            (on.add if r["exception_type"] == "1" else on.discard)(r["service_id"])
    return on


def region_bbox():
    minx, miny, maxx, maxy = area_polygon().bounds
    dlat = REGION_KM / 111.32
    dlon = REGION_KM / (111.32 * math.cos(math.radians((miny + maxy) / 2)))
    return minx - dlon, miny - dlat, maxx + dlon, maxy + dlat


def extract(day, refresh=False):
    """{stations, routes, trips, connections} for the region on `day`, cached."""
    cache = CACHE / f"connections_{day:%Y%m%d}.pkl.gz"
    if cache.exists() and not refresh:
        with gzip.open(cache) as f:
            return pickle.load(f)
    z = zipfile.ZipFile(FEED)
    t0 = time.time()
    on = services_on(z, day)
    log(f"{day} ({day:%A}): {len(on)} services running")

    minx, miny, maxx, maxy = region_bbox()
    stations = {}
    for r in open_csv(z, "stops.txt"):
        sid = station(r["stop_id"])
        lat, lon = float(r["stop_lat"]), float(r["stop_lon"])
        if minx <= lon <= maxx and miny <= lat <= maxy and (sid not in stations or r["location_type"] == "1"):
            stations[sid] = {"name": r["stop_name"], "lat": lat, "lon": lon}
    log(f"  {len(stations)} stations in the region")

    routes = {}
    for r in open_csv(z, "routes.txt"):
        routes[r["route_id"]] = (r["route_short_name"], int(r["route_type"]), r["route_color"],
                                 r["route_text_color"], r["agency_id"])
    trips = {}
    for r in open_csv(z, "trips.txt"):
        if r["service_id"] in on:
            trips[r["trip_id"]] = (r["route_id"], r["trip_headsign"])
    log(f"  {len(trips)} trips running in Switzerland")
    freq = collections.defaultdict(list)
    for r in open_csv(z, "frequencies.txt"):
        if r["trip_id"] in trips:
            freq[r["trip_id"]].append((secs(r["start_time"]), secs(r["end_time"]), int(r["headway_secs"])))

    # stream stop_times (sorted by trip, then stop_sequence in this feed;
    # sorted again per trip to be safe)
    conns, used_trips = [], {}
    cur, rows, n = None, [], 0

    def flush(trip_id, rows):
        rows.sort()
        base = [(seq, st, a, d) for seq, st, a, d in rows]
        offsets = [0]
        if trip_id in freq:
            first = base[0][3]
            offsets = [t - first for s, e, h in freq[trip_id] for t in range(s, e + 1, h)]
        made = False
        for off in offsets:
            for (s1, st1, a1, d1), (s2, st2, a2, d2) in zip(base, base[1:]):
                if st1 in stations and st2 in stations and st1 != st2 and DAY[0] <= d1 + off <= DAY[1]:
                    conns.append((d1 + off, a2 + off, st1, st2, f"{trip_id}@{off}" if off else trip_id))
                    made = True
        if made:
            used_trips[trip_id] = trips[trip_id]

    with z.open("stop_times.txt") as fh:
        rd = csv.reader(io.TextIOWrapper(fh, "utf-8-sig"))
        hdr = next(rd)
        i_trip, i_arr, i_dep, i_stop, i_seq = (hdr.index(k) for k in
                                               ("trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"))
        for row in rd:
            n += 1
            trip_id = row[i_trip]
            if trip_id != cur:
                if rows:
                    flush(cur, rows)
                cur, rows = trip_id, []
            if trip_id in trips:
                # first / last stops may leave one of the two times empty
                arr_t, dep_t = row[i_arr] or row[i_dep], row[i_dep] or row[i_arr]
                if arr_t:
                    rows.append((int(row[i_seq]), station(row[i_stop]), secs(arr_t), secs(dep_t)))
            if n % 5_000_000 == 0:
                log(f"  {n / 1e6:.0f}M stop times read, {len(conns)} connections ({time.time() - t0:.0f} s)")
        if rows:
            flush(cur, rows)
    route_ids = {r for r, _ in used_trips.values()}
    data = {"day": day.isoformat(), "stations": stations, "routes": {k: routes[k] for k in route_ids},
            "trips": used_trips, "connections": conns}
    with gzip.open(cache, "wb") as f:
        pickle.dump(data, f)
    log(f"  {len(conns)} connections, {len(used_trips)} trips, {len(route_ids)} routes "
        f"({time.time() - t0:.0f} s) -> {cache.name}")
    return data


def transfers(z, stations):
    """{(from, to): seconds} between distinct stations, from the feed."""
    out = {}
    for r in open_csv(z, "transfers.txt"):
        a, b = station(r["from_stop_id"]), station(r["to_stop_id"])
        if a != b and a in stations and b in stations and r["min_transfer_time"]:
            t = int(r["min_transfer_time"])
            out[(a, b)] = min(t, out.get((a, b), t))
    return out


def change_times(z, stations):
    """{station: seconds} the feed's minimum change time within a station."""
    out = {}
    for r in open_csv(z, "transfers.txt"):
        a, b = station(r["from_stop_id"]), station(r["to_stop_id"])
        if a == b and a in stations and r["transfer_type"] == "2" and r["min_transfer_time"]:
            out[a] = max(out.get(a, 0), int(r["min_transfer_time"]))
    return out


def label(route):
    """(name, mode, colour, text colour) of a route, for badges and lines."""
    name, rtype, color, text, _ = route
    mode = MODE.get(rtype, "bus")
    return (name or "?", mode, (color or "").upper(), (text or "").upper())


def profiles(data):
    """Run the scan; returns everything the per-stop output needs."""
    z = zipfile.ZipFile(FEED)
    stations = data["stations"]
    ids = sorted(stations)
    idx = {s: i for i, s in enumerate(ids)}
    trip_ix = {}
    conns = []
    for d, a, u, v, trip in data["connections"]:
        conns.append((d, a, idx[u], idx[v], trip_ix.setdefault(trip, len(trip_ix))))
    trip_names = list(trip_ix)
    # walks between stations: the feed's transfers, plus short straight-line walks
    feed_tr = transfers(z, stations)
    foot = collections.defaultdict(dict)
    for (a, b), t in feed_tr.items():
        foot[idx[a]][idx[b]] = t
    cell = collections.defaultdict(list)          # ~400 m grid for the neighbour search
    for s in ids:
        st = stations[s]
        cell[(int(st["lat"] / 0.0036), int(st["lon"] / 0.0053))].append(s)
    for s in ids:
        st = stations[s]
        ci, cj = int(st["lat"] / 0.0036), int(st["lon"] / 0.0053)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for o in cell[(ci + di, cj + dj)]:
                    if o == s:
                        continue
                    d = dist_m(st["lat"], st["lon"], stations[o]["lat"], stations[o]["lon"])
                    if d <= FOOT_M:
                        foot[idx[s]].setdefault(idx[o], int(d * DETOUR / WALK_M_PER_MIN * 60) + 60)
    footpaths = {k: sorted(v.items(), key=lambda kv: kv[1]) for k, v in foot.items()}
    hb = stations[HB]
    target = {idx[HB]: 0}
    for s in ids:
        d = dist_m(hb["lat"], hb["lon"], stations[s]["lat"], stations[s]["lon"])
        if s != HB and d <= TARGET_M:
            target[idx[s]] = feed_tr.get((s, HB), int(d * DETOUR / WALK_M_PER_MIN * 60) + 60)
    change = {idx[s]: t for s, t in change_times(z, stations).items()}
    log(f"Profile scan: {len(conns)} connections, {len(ids)} stations, "
        f"{sum(len(v) for v in footpaths.values())} footpaths, {len(target)} stops at HB ...")
    t0 = time.time()
    profs = tp.profile_scan(conns, len(ids), target, footpaths, change)
    log(f"  done in {time.time() - t0:.0f} s; "
        f"{sum(len(p.dep) for p in profs)} Pareto journeys over all stations")
    served = collections.Counter(u for _, _, u, _, _ in data["connections"])
    return {"ids": ids, "idx": idx, "profs": profs, "footpaths": footpaths, "change": change,
            "trip_names": trip_names, "target": target, "served": served}


SAME_STOP_M = 150       # a stop missing from the feed: its nearest feed station this close


def feed_station(nr, lat, lon, P, data):
    """The feed's station for a stop of transit_stops.geojson: the same number,
    or (the feed numbers some stops differently: the Forchbahn's Rehalp, HB's
    SZU platforms) the nearest station within SAME_STOP_M that has service."""
    sid = str(nr)
    if sid in P["idx"]:
        return sid          # even without departures today (boats in winter): walks on
    best = None
    for s, st in data["stations"].items():
        if P["served"].get(s):
            d = dist_m(lat, lon, st["lat"], st["lon"])
            if d <= SAME_STOP_M and (best is None or d < best[0]):
                best = (d, s)
    return best[1] if best else None


def stop_output(nr, P, data, sid=None):
    """The card data of one stop (None if it has no journey to HB)."""
    if sid is None:
        return None
    i = P["idx"][sid]
    deps, arrs, refs = tp.origin_profile(i, P["profs"], P["footpaths"])
    if not deps and i not in P["target"]:
        return None
    routes, trips = data["routes"], data["trips"]
    labels, label_ix = [], {}

    def lab(trip_name):
        rid = trips[trip_name.split("@")[0]][0]
        key = label(routes[rid])
        if key not in label_ix:
            label_ix[key] = len(labels)
            labels.append(key)
        return label_ix[key]

    out_dep, out_arr, out_ntr, out_legs, out_walk = [], [], [], [], []
    for d, a, (stop, k, walk) in zip(deps, arrs, refs):
        if not (DAY[0] <= d <= DAY[1]):
            continue
        legs = tp.journey(P["profs"], stop, k, P["change"])
        out_dep.append(round(d / 60, 1))
        out_arr.append(round(a / 60, 1))
        out_ntr.append(P["profs"][stop].ntr[k])
        # per leg: line index and the stop where it is left (names on demand)
        out_legs.append([[lab(P["trip_names"][t]), round(t_off / 60, 1), P["ids"][alight]]
                         for t, _, _, alight, t_off in legs])
        # the journey starts at a nearby stop: walk there first [station, minutes]
        out_walk.append([P["ids"][stop], round(walk / 60)] if walk else None)
    # the travel sawtooth, its cycle and stats per part of the day
    parts = {}
    for name, (a0, a1) in PARTS.items():
        curve = tp.travel_curve(deps, arrs, a0, a1)
        st = tp.summarize(curve)
        parts[name] = {**(st or {}), "takt": tp.detect_takt(curve) if st else None}
    curve = tp.travel_curve(deps, arrs, *CURVE)
    # lines serving the stop (departures of the day per line)
    serving = collections.Counter()
    for d, a, u, v, trip in data["connections"]:
        if u == sid:
            serving[label(routes[trips[trip.split("@")[0]][0]])] += 1
    lines = [[n, m, c, tc, cnt] for (n, m, c, tc), cnt in
             sorted(serving.items(), key=lambda kv: (["train", "metro", "tram", "boat", "funicular", "cable", "bus"]
                                                      .index(kv[0][1]) if kv[0][1] in MODE.values() else 9,
                                                      len(kv[0][0]), kv[0][0]))]
    alight_names = {s: data["stations"][s]["name"] for legs in out_legs for _, _, s in legs}
    alight_names.update({w[0]: data["stations"][w[0]]["name"] for w in out_walk if w})
    return {"nr": nr, "feed_station": sid if sid != str(nr) else None, "day": data["day"], "dep": out_dep, "arr": out_arr, "ntr": out_ntr, "legs": out_legs, "walk": out_walk,
            "labels": labels, "stops": alight_names, "parts": parts, "lines": lines,
            "curve_start": CURVE[0] // 60,
            "curve": [None if c is None else round(c / 60, 1) for c in curve[::2]],   # every 2 min
            "at_hb": i in P["target"] and P["target"][i] == 0}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", help="service day YYYYMMDD (default: next Tuesday)")
    ap.add_argument("--refresh", action="store_true", help="download the feed and re-extract")
    args = ap.parse_args()
    day = dt.datetime.strptime(args.date, "%Y%m%d").date() if args.date else next_tuesday()
    download(args.refresh)
    data = extract(day, args.refresh)
    P = profiles(data)
    stops = json.loads(STOPS.read_text())
    outdir = LAYERS / "stop_profiles"
    outdir.mkdir(exist_ok=True)
    for f in outdir.glob("*.json"):
        f.unlink()
    got, takts = 0, collections.Counter()
    for f in stops["features"]:
        p = f["properties"]
        for k in [k for k in p if k.startswith("hb_")]:
            del p[k]
        lon, lat = f["geometry"]["coordinates"]
        o = stop_output(p["nr"], P, data, feed_station(p["nr"], lat, lon, P, data))
        if not o:
            continue
        got += 1
        (outdir / f"{p['nr']}.json").write_text(json.dumps(o, ensure_ascii=False, separators=(",", ":")))
        m = o["parts"]["morning"]
        if m.get("mean") is not None:
            p["hb_mean"], p["hb_min"], p["hb_takt"] = m["mean"], m["min"], m["takt"]
        takts[m.get("takt")] += 1
    STOPS.write_text(json.dumps(stops, ensure_ascii=False))
    size = sum(f.stat().st_size for f in outdir.glob("*.json"))
    log(f"{got} of {len(stops['features'])} stops with a profile -> {outdir.relative_to(ROOT)}/ "
        f"({size / 1e6:.1f} MB); morning Takt: " +
        ", ".join(f"{k} min {v}" if k else f"none {v}" for k, v in sorted(takts.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))))


if __name__ == "__main__":
    main()
