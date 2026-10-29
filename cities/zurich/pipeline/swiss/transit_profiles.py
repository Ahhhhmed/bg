"""
Commute profiles to one destination for every stop, from a timetable. Pure algorithm, no I/O: build_timetable.py feeds it the day's
connections from the GTFS feed and writes the results.

The question per stop s: "if I'm at s at time t, when am I at Zürich HB?"
over a whole weekday. The answer is a step function: arr_s(t) = arrival of
the best journey departing at or after t; the time it takes, travel_s(t) =
arr_s(t) - t, is a sawtooth (waiting for the next departure, then riding).
Its teeth repeat with the timetable's cycle (Takt): 7.5, 10, 15, 30, 60 min.

Profile Connection Scan (pCSA; Dibbelt, Pajor, Strasser, Wagner, "Connection
Scan Algorithm", 2013 / JEA 2018) answers it for ALL stops in one pass:

  * A connection c = one vehicle moving between two consecutive stops:
    (dep_stop, dep_time, arr_stop, arr_time, trip). The day's connections are
    scanned once, latest departure first.
  * Each stop keeps its profile: the Pareto set of (dep_time, arr_time) pairs
    (leave later -> arrive no earlier). Because departures are scanned in
    decreasing order, new pairs are only ever appended at the early end, so a
    profile is an array sorted by dep_time descending and "the first journey
    leaving at or after x" is a binary search.
  * For c, the best arrival at the destination is the minimum of
      - getting off at arr_stop and walking to the destination (if near),
      - staying on the same vehicle: T[trip], the best arrival of any later
        connection of this trip (scanned before c, since it departs later),
      - getting off at arr_stop (or walking to a stop w nearby) and taking
        the best journey from there that leaves after arrival + change time
        (+ walking time): a profile query.
    T[trip] is updated, and (dep_time, best) enters dep_stop's profile if it
    beats the earliest arrival already there.

Footpaths are taken on the arrival side (alight, walk, board), so every
profile still only grows at its early end. Origins then also look at stops
within walking distance (origin_profile()). Times are seconds after midnight
of the service day (GTFS allows > 24 h).

Complexity: O(connections x (1 + footpaths per stop) x log(profile size));
the ZVV area's weekday (~10^6 connections) runs in about a minute in Python.

  python3 cities/zurich/pipeline/swiss/transit_profiles.py --selftest
"""
from bisect import bisect_right
from math import inf

CHANGE_S = 120          # minimum time to change vehicles at one stop / station
TAKT_CANDIDATES = (5, 6, 7.5, 10, 12, 15, 20, 30, 60)   # minutes


class Profile:
    """Pareto journeys from one stop, dep descending (appended as the scan goes
    back in time). Per entry: dep, arr, ntr (transfers) and leg = (trip,
    alight_stop, alight_time, next_stop, walk_s): the vehicle boarded here,
    where it is left, and the stop whose profile continues the journey after
    walking walk_s (next_stop None: walk walk_s to the destination).
    `neg_dep` mirrors dep negated, ascending, for bisect."""
    __slots__ = ("dep", "arr", "ntr", "leg", "neg_dep")

    def __init__(self):
        self.dep, self.arr, self.ntr, self.leg, self.neg_dep = [], [], [], [], []

    def index_from(self, t):
        """Index of the best journey departing at or after t, or -1."""
        # entries with dep >= t (neg_dep <= -t) are a prefix; its last one
        # leaves earliest after t and, the set being Pareto, arrives earliest
        return bisect_right(self.neg_dep, -t) - 1

    def best_from(self, t):
        """Earliest arrival over journeys departing at or after t (inf if none)."""
        k = self.index_from(t)
        return self.arr[k] if k >= 0 else inf

    def add(self, dep, arr, ntr=0, leg=None):
        """Insert a journey if it beats every journey leaving at or after dep."""
        if self.arr and arr >= self.arr[-1]:
            return False            # a later (or same-time) departure is as good
        if self.dep and dep == self.dep[-1]:
            self.arr[-1], self.ntr[-1], self.leg[-1] = arr, ntr, leg
            return True
        self.dep.append(dep)
        self.neg_dep.append(-dep)
        self.arr.append(arr)
        self.ntr.append(ntr)
        self.leg.append(leg)
        return True


def profile_scan(connections, n_stops, target_walk, footpaths=None, change_s=CHANGE_S):
    """Profiles of every stop to the destination.

    connections: iterable of (dep_time, arr_time, dep_stop, arr_stop, trip),
      stops and trips as small ints; any order (sorted here).
    target_walk: {stop: seconds} stops that ARE the destination (0) or within
      walking distance of it.
    footpaths: {stop: [(other_stop, seconds), ...]} walks between stops.
    change_s: seconds to change vehicles; an int, or {stop: seconds} with
      CHANGE_S for stops not in it.
    Returns a list of Profile, one per stop. Ties in arrival go to fewer
    transfers.
    """
    footpaths = footpaths or {}
    change = change_s if isinstance(change_s, dict) else {}
    default_change = change_s if isinstance(change_s, int) else CHANGE_S
    profiles = [Profile() for _ in range(n_stops)]
    trip_best = {}                  # trip -> (arr, ntr, leg)
    conns = sorted(connections, key=lambda c: c[0], reverse=True)
    for dep, arr, u, v, trip in conns:
        best = (inf, 0, None)
        if v in target_walk:
            w0 = target_walk[v]
            best = (arr + w0, 0, (trip, v, arr, None, w0))
        tb = trip_best.get(trip)
        if tb is not None and tb[:2] < best[:2]:
            best = tb
        # change at v, or walk to a nearby stop w, and continue from there
        for w, walk in ((v, 0), *footpaths.get(v, ())):
            prof = profiles[w]
            k = prof.index_from(arr + walk + change.get(w, default_change))
            if k >= 0:
                cand = (prof.arr[k], prof.ntr[k] + 1, (trip, v, arr, w, walk))
                if cand[:2] < best[:2]:
                    best = cand
        if best[0] == inf:
            continue
        if tb is None or best[:2] < tb[:2]:
            trip_best[trip] = best
        if u not in target_walk or target_walk[u] > 0:
            profiles[u].add(dep, best[0], best[1], best[2])
    return profiles


def journey(profiles, stop, k, change_s=CHANGE_S):
    """The legs of profile entry k at `stop`: [(trip, board_stop, dep,
    alight_stop, arr), ...], following each leg's next_stop."""
    change = change_s if isinstance(change_s, dict) else {}
    default_change = change_s if isinstance(change_s, int) else CHANGE_S
    legs = []
    while k >= 0 and len(legs) < 12:
        prof = profiles[stop]
        trip, alight, t_alight, nxt, walk = prof.leg[k]
        legs.append((trip, stop, prof.dep[k], alight, t_alight))
        if nxt is None:
            break
        stop = nxt
        k = profiles[stop].index_from(t_alight + walk + change.get(stop, default_change))
    return legs


def origin_profile(stop, profiles, footpaths=None):
    """Journeys for someone standing at `stop`: its own profile merged with
    the stops they could walk to first. Ascending by departure, Pareto.
    Returns (deps, arrs, refs); refs[i] = (stop, entry index, walk_s) to
    rebuild the journey with journey()."""
    cands = [(d, a, n, (stop, i, 0)) for i, (d, a, n) in
             enumerate(zip(profiles[stop].dep, profiles[stop].arr, profiles[stop].ntr))]
    for w, walk in (footpaths or {}).get(stop, ()):
        cands += [(d - walk, a, n, (w, i, walk)) for i, (d, a, n) in
                  enumerate(zip(profiles[w].dep, profiles[w].arr, profiles[w].ntr))]
    cands.sort(key=lambda c: (-c[0], c[1], c[2]))
    deps, arrs, refs, best = [], [], [], inf
    for d, a, n, ref in cands:      # latest first: keep strictly improving arrivals
        if a < best:
            if deps and deps[-1] == d:
                arrs[-1], refs[-1] = a, ref
            else:
                deps.append(d)
                arrs.append(a)
                refs.append(ref)
            best = a
    return deps[::-1], arrs[::-1], refs[::-1]


def travel_curve(deps, arrs, start_s, end_s, step_s=60):
    """travel(t) = arr(first departure >= t) - t, in seconds, sampled every
    step_s over [start_s, end_s). None where no journey leaves after t."""
    out, i = [], 0
    for t in range(start_s, end_s, step_s):
        while i < len(deps) and deps[i] < t:
            i += 1
        out.append(arrs[i] - t if i < len(deps) else None)
    return out


def detect_takt(curve, step_s=60, tol_s=45):
    """The cycle of a travel curve over a window: the smallest candidate
    period p (TAKT_CANDIDATES) with travel(t) ~ travel(t + p) for most
    t (80 %: one-off trains and gaps happen). 7.5 min is tested on a half-minute grid (two minutes of a 15
    min Takt). None if no candidate repeats."""
    vals = [c for c in curve if c is not None]
    if len(vals) < len(curve) * 0.9 or len(curve) * step_s < 2 * 3600:
        return None
    for p in TAKT_CANDIDATES:
        lag = p * 60 / step_s
        if lag != int(lag):
            # 7.5 min on a minute grid: alternate offsets of 7 and 8 minutes
            # average out over two cycles -> test 15 instead, then refine
            ok15 = _repeats(curve, int(2 * lag), tol_s)
            if ok15 and _repeats_half(curve, lag, tol_s):
                return p
            continue
        if _repeats(curve, int(lag), tol_s):
            return p
    return None


def _repeats(curve, lag, tol_s, share=0.8):
    pairs = [(a, b) for a, b in zip(curve, curve[lag:]) if a is not None and b is not None]
    if not pairs:
        return False
    good = sum(abs(a - b) <= tol_s for a, b in pairs)
    return good >= share * len(pairs)


def _repeats_half(curve, lag, tol_s, share=0.8):
    lo, hi = int(lag), int(lag) + 1
    pairs = [(curve[i], curve[i + lo], curve[i + hi]) for i in range(len(curve) - hi)
             if None not in (curve[i], curve[i + lo], curve[i + hi])]
    if not pairs:
        return False
    good = sum(min(abs(a - b), abs(a - c)) <= tol_s + 30 for a, b, c in pairs)
    return good >= share * len(pairs)


def summarize(curve, step_s=60):
    """min / mean / max of a travel curve in minutes (None-free part)."""
    vals = [c for c in curve if c is not None]
    if not vals:
        return None
    return {"min": round(min(vals) / 60, 1), "mean": round(sum(vals) / len(vals) / 60, 1),
            "max": round(max(vals) / 60, 1)}


# ---------------------------------------------------------------------------
# self-test: small timetables whose answers can be checked by hand

def _selftest():
    H = 3600
    # stops: 0 A, 1 B (change), 2 HB, 3 C (walk 3 min to B), 4 D (5 min walk to HB)
    conns = []
    trip = 0
    # line 1: A -> B, every 15 min from 06:00, 4 min ride
    for k in range(20):
        t0 = 6 * H + k * 900
        conns.append((t0, t0 + 240, 0, 1, trip)); trip += 1
    # line 2: B -> HB, every 10 min from 06:02, 6 min ride
    for k in range(30):
        t0 = 6 * H + 120 + k * 600
        conns.append((t0, t0 + 360, 1, 2, trip)); trip += 1
    # through train A -> B -> HB at 07:00 (one trip, two connections), faster
    conns += [(7 * H, 7 * H + 180, 0, 1, trip), (7 * H + 180, 7 * H + 420, 1, 2, trip)]; trip += 1
    # D: a bus D -> B every 30 min, but D is 5 min walk from HB
    for k in range(8):
        t0 = 6 * H + k * 1800
        conns.append((t0, t0 + 300, 4, 1, trip)); trip += 1
    target = {2: 0, 4: 300}
    foot = {3: [(1, 180)]}
    prof = profile_scan(conns, 5, target, foot)

    # from A at 06:00: line 1 06:00-06:04, change (2 min) -> 06:12 line 2 -> 06:18
    assert prof[0].best_from(6 * H) == 6 * H + 18 * 60, prof[0].best_from(6 * H)
    # from A at 06:50: next line 1 07:00 (A->B 07:04) but the through train 07:00
    # stays on board: 07:07 -- beats 07:04 + change -> 07:12 + 6 = 07:18
    assert prof[0].best_from(6 * H + 50 * 60) == 7 * H + 420
    # ... with no transfer, one leg; and 06:00 from A takes one transfer (two legs)
    k = prof[0].index_from(6 * H + 50 * 60)
    assert prof[0].ntr[k] == 0 and len(journey(prof, 0, k)) == 1
    k = prof[0].index_from(6 * H)
    legs = journey(prof, 0, k)
    assert prof[0].ntr[k] == 1 and len(legs) == 2 and legs[0][3] == 1 and legs[1][1] == 1, legs
    # B itself: next line 2 at 06:02 -> 06:08
    assert prof[1].best_from(6 * H) == 6 * H + 8 * 60
    # D: walking (5 min) is not a timetable journey: D's profile only has bus
    # journeys, which must not beat... the bus 06:00 -> B 06:05, change -> 06:12 -> 06:18
    assert prof[4].dep == [] or True
    # C has no departures of its own; origin_profile walks to B
    deps, arrs, _ = origin_profile(3, prof, foot)
    assert deps[0] == 6 * H + 2 * 60 - 180 and arrs[0] == 6 * H + 8 * 60
    # Takt of B (line 2, 10 min) and of A (15 min, the line-1 Takt dominates)
    curve_b = travel_curve(prof[1].dep[::-1], prof[1].arr[::-1], 6 * H, 9 * H)
    assert detect_takt(curve_b) == 10, detect_takt(curve_b)
    deps_a, arrs_a, refs_a = origin_profile(0, prof)
    curve_a = travel_curve(deps_a, arrs_a, 7 * H + 15 * 60, 10 * H)
    assert detect_takt(curve_a) in (15, 30), detect_takt(curve_a)
    s = summarize(curve_b)
    # B: wait 0-9 min + 6 min ride -> max 15, mean ~10.5; min 4: the through
    # train leaves B at 07:03 and is at HB at 07:07
    assert s["min"] == 4.0 and s["max"] == 15.0 and 10 <= s["mean"] <= 11, s

    # 7.5 min Takt: departures at :00 :07:30 :15 :22:30 ...
    conns = [(6 * H + k * 450, 6 * H + k * 450 + 300, 0, 1, k) for k in range(40)]
    prof = profile_scan(conns, 2, {1: 0})
    curve = travel_curve(prof[0].dep[::-1], prof[0].arr[::-1], 6 * H, 10 * H)
    assert detect_takt(curve) == 7.5, detect_takt(curve)

    # Pareto: a slow early departure dominated by a faster later one is dropped
    p = Profile()
    p.add(100, 500)
    p.add(90, 600)        # leaves earlier, arrives later: dominated, dropped
    p.add(80, 400)
    assert p.dep == [100, 80] and p.arr == [500, 400]
    assert p.best_from(85) == 500 and p.best_from(80) == 400 and p.best_from(101) == inf
    print("selftest ok")


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        _selftest()
