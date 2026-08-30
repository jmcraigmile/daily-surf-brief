#!/usr/bin/env python3
"""
San Diego daily surf brief -- swell, tide, wind -> ranked breaks + board call.

Data sources (all free, no API keys):
  - Open-Meteo Marine API      : swell height / period / direction, wind waves
  - Open-Meteo Forecast API    : wind speed + direction, air temp, sunset
  - NOAA CO-OPS station 9410230: tide predictions (La Jolla / Scripps Pier)
  - NDBC buoy 46258            : live buoy reality-check (Mission Bay, 3nm offshore)

Scoring rules live in breaks.json, extracted from the write-ups in
01-San-Diego-Breaks/. Local transforms (canyon lens, kelp) come from the folder,
not from the model -- the marine model grid is ~5km and cannot resolve the
difference between Black's and Scripps.

Usage: python3 surf_forecast.py [--date YYYY-MM-DD] [--json out.json]
"""

import json
import math
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, date
import argparse
import os
import water

HERE = os.path.dirname(os.path.abspath(__file__))

# Regional swell sample point -- offshore of La Jolla, outside the canyon
REGION_LAT, REGION_LON = 32.83, -117.30
# Wind sample points
WIND_POINTS = {"north": (32.86, -117.255), "south": (32.73, -117.253)}
TIDE_STATION = "9410230"  # La Jolla (Scripps Pier)
BUOY = "46258"            # Mission Bay, CA

MORNING = (7.0, 8.5)      # 7:00 - 8:30am
# Breaks further than this get a "worth the drive?" marker on the card. Scoring
# is deliberately NOT affected -- rank on quality, show the distance, let Jake
# judge (his call, 2026-08-30). Nothing in the current thirteen trips it; the
# mechanism is here for San Onofre and Church (~60 min) if they get added.
DRIVE_FLAG_MINUTES = 45
EVENING_LEAD_HOURS = 1.0  # window = sunset-1h -> sunset


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "sd-surf-brief/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def fetch_json(url, timeout=25):
    return json.loads(fetch(url, timeout))


# ---------------------------------------------------------------- data pulls

def get_marine(day):
    url = (
        "https://marine-api.open-meteo.com/v1/marine?"
        + urllib.parse.urlencode({
            "latitude": REGION_LAT, "longitude": REGION_LON,
            "hourly": ("swell_wave_height,swell_wave_period,swell_wave_direction,"
                       "wind_wave_height,wind_wave_period,wave_height,wave_period,"
                       "wave_direction"),
            "length_unit": "imperial",
            "timezone": "America/Los_Angeles",
            "start_date": day, "end_date": day,
        })
    )
    return fetch_json(url)


def get_weather(day):
    out = {}
    for key, (lat, lon) in WIND_POINTS.items():
        url = (
            "https://api.open-meteo.com/v1/forecast?"
            + urllib.parse.urlencode({
                "latitude": lat, "longitude": lon,
                "hourly": "wind_speed_10m,wind_direction_10m,wind_gusts_10m,temperature_2m",
                "daily": "sunrise,sunset",
                "wind_speed_unit": "mph", "temperature_unit": "fahrenheit",
                "timezone": "America/Los_Angeles",
                "start_date": day, "end_date": day,
            })
        )
        out[key] = fetch_json(url)
    return out


def get_tides(day):
    d = day.replace("-", "")
    nxt = (datetime.strptime(day, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y%m%d")
    base = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?"
    common = {
        "application": "sd-surf-brief", "datum": "MLLW", "station": TIDE_STATION,
        "time_zone": "lst_ldt", "units": "english", "format": "json",
        "product": "predictions", "begin_date": d, "end_date": nxt,
    }
    hilo = fetch_json(base + urllib.parse.urlencode({**common, "interval": "hilo"}))
    curve = fetch_json(base + urllib.parse.urlencode({**common, "interval": "h"}))
    return hilo.get("predictions", []), curve.get("predictions", [])


def get_buoy():
    """Latest spectral reading from NDBC 46258. Returns dict or None."""
    try:
        txt = fetch(f"https://www.ndbc.noaa.gov/data/realtime2/{BUOY}.spec", timeout=20)
    except Exception:
        return None
    lines = [l for l in txt.splitlines() if l and not l.startswith("#")]
    if not lines:
        return None
    f = lines[0].split()
    if len(f) < 15:
        return None

    def num(v):
        try:
            return float(v)
        except ValueError:
            return None

    swh_m, swp, mwd = num(f[6]), num(f[7]), num(f[14])
    wwh_m, wwp = num(f[8]), num(f[9])
    return {
        "time": f"{f[0]}-{f[1]}-{f[2]} {f[3]}:{f[4]} UTC",
        "swell_ft": round(swh_m * 3.28084, 1) if swh_m is not None else None,
        "swell_period": swp,
        "swell_dir_txt": f[10],
        "windwave_ft": round(wwh_m * 3.28084, 1) if wwh_m is not None else None,
        "windwave_period": wwp,
        "mean_dir": mwd,
        "steepness": f[12],
    }


# ---------------------------------------------------------------- helpers

def hour_index(times, target_hour):
    """Index of the hourly slot nearest target_hour (float hours local)."""
    best, best_d = 0, 1e9
    for i, t in enumerate(times):
        h = int(t[11:13])
        d = abs(h - target_hour)
        if d < best_d:
            best, best_d = i, d
    return best


def _window_idxs(times, h0, h1):
    """Hourly slots overlapping [h0,h1]. Slot H covers H:00-H:59, so a window of
    18.33-19.33 must include hour 18, not just 19."""
    import math
    lo, hi = math.floor(h0), math.ceil(h1) - 1
    hi = max(hi, lo)
    return [i for i, t in enumerate(times) if lo <= int(t[11:13]) <= hi]


def window_avg(hourly, keys, h0, h1):
    times = hourly["time"]
    idxs = _window_idxs(times, h0, h1)
    if not idxs:
        idxs = [hour_index(times, (h0 + h1) / 2)]
    out = {}
    for k in keys:
        vals = [hourly[k][i] for i in idxs if hourly[k][i] is not None]
        out[k] = round(sum(vals) / len(vals), 1) if vals else None
    return out


def circ_avg(hourly, key, h0, h1):
    import math
    times = hourly["time"]
    idxs = _window_idxs(times, h0, h1)
    if not idxs:
        idxs = [hour_index(times, (h0 + h1) / 2)]
    xs = ys = 0.0
    n = 0
    for i in idxs:
        v = hourly[key][i]
        if v is None:
            continue
        r = math.radians(v)
        xs += math.cos(r)
        ys += math.sin(r)
        n += 1
    if not n:
        return None
    ang = math.degrees(math.atan2(ys / n, xs / n)) % 360
    return round(ang)


def compass(deg):
    if deg is None:
        return "--"
    pts = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return pts[int((deg + 11.25) % 360 // 22.5)]


def in_arc(deg, lo, hi):
    if deg is None:
        return False
    deg %= 360
    lo %= 360
    hi %= 360
    return lo <= deg <= hi if lo <= hi else (deg >= lo or deg <= hi)


def arc_distance(deg, lo, hi):
    """0 if inside the arc, else degrees to the nearer edge."""
    if in_arc(deg, lo, hi):
        return 0.0
    d1 = min((deg - lo) % 360, (lo - deg) % 360)
    d2 = min((deg - hi) % 360, (hi - deg) % 360)
    return min(d1, d2)


def face_height(hs_ft, period):
    """Total significant wave height -> rough face-foot estimate.

    Calibrated 2026-08-27 against NDBC 46258: the model's TOTAL wave_height
    tracks the buoy's WVHT closely (4.66 ft model vs 4.6 ft measured), while
    the swell/windwave partition does not -- so the total is what drives this.
    Longer period shoals higher. An estimate, not a measurement.
    """
    if hs_ft is None:
        return None
    p = period or 12
    factor = max(0.80, min(1.45, 0.80 + 0.045 * (p - 9)))
    return round(hs_ft * factor, 1)


def tide_at(curve, when_dt):
    """Interpolated tide height (ft MLLW) and rising/falling at a datetime."""
    prev = nxt = None
    for p in curve:
        t = datetime.strptime(p["t"], "%Y-%m-%d %H:%M")
        if t <= when_dt:
            prev = (t, float(p["v"]))
        elif nxt is None:
            nxt = (t, float(p["v"]))
            break
    if prev and nxt:
        span = (nxt[0] - prev[0]).total_seconds()
        frac = (when_dt - prev[0]).total_seconds() / span if span else 0
        h = prev[1] + (nxt[1] - prev[1]) * frac
        return round(h, 1), ("rising" if nxt[1] > prev[1] else "falling")
    if prev:
        return round(prev[1], 1), "unknown"
    return None, "unknown"


def tide_state(h):
    """SD tide range runs roughly -1.5 to +7 ft MLLW; mean sea level ~2.7 ft."""
    if h is None:
        return "unknown"
    if h < 1.5:
        return "low"
    if h < 3.5:
        return "mid"
    return "high"


# ---------------------------------------------------------------- scoring

def sea_state(sw, buoy=None, target_date=None):
    """Split the sea into a long-period component and a short-period one.

    WHY THIS EXISTS (2026-08-30 fix). The canyon lens is refraction, so it acts
    on WAVELENGTH -- the period of the swell actually doing the refracting. The
    old code fed it the model's blended mean period, which averages a long
    groundswell together with local windchop. On 2026-08-30 the buoy held
    3.3ft @ 16.7s SSW for six hours straight while the model reported a 10.7s
    blend, so the lens read "barely in play" on a textbook south groundswell --
    exactly the swell Central-SD.md says the canyon wraps into Black's through
    summer. Two errors in one: the wrong period, applied to the wrong energy.

    The lens must act ONLY on the long-period energy. An 8-second windwave
    "feels bottom at 28 m and skims the whole shelf" (Central-SD.md), so the
    canyon does nothing to it. Amplifying the total over-applies badly: on that
    same morning, amplifying the total gave 8.0ft Hs where decomposing first
    gives 6.5ft.

    TOTAL height and period still come from the model -- both are calibrated and
    trusted (see "Two calibrations that look wrong but aren't" in README.md).
    Only the PARTITION is sourced here, in priority order:

      1. buoy   -- NDBC 46258 measures the split directly. Used only when it is
                   self-consistent with the model total and the target day is
                   within a day of the reading. High confidence.
      2. model  -- Open-Meteo's own partition, but ONLY if it reproduces the
                   model's own mean period. It frequently does not: at
                   2026-08-30T07:00 it reported 3.2ft @ 7.0s from 279deg while
                   its own total said 10.7s, then swung back to 13.2s/202deg
                   twelve hours later. A swell does not vanish and return.
      3. none   -- no split available. Falls back to old behaviour (whole sea
                   treated as one component at the blended period). Low
                   confidence, and the brief says so.

    Returns a dict, or None if there is nothing to work with.
    """
    hs, tm = sw.get("wave_height"), sw.get("wave_period")
    if hs is None or tm is None:
        return None

    def energy_mean_period(h1, t1, h2, t2):
        e1, e2 = (h1 or 0) ** 2, (h2 or 0) ** 2
        if e1 + e2 <= 0:
            return None
        return (e1 * (t1 or 0) + e2 * (t2 or 0)) / (e1 + e2)

    # --- 1. buoy
    if buoy and target_date:
        bh, bp = buoy.get("swell_ft"), buoy.get("swell_period")
        wh, wp = buoy.get("windwave_ft"), buoy.get("windwave_period")
        fresh = False
        try:
            btime = datetime.strptime(buoy["time"][:16], "%Y-%m-%d %H:%M")
            tgt = datetime.strptime(target_date, "%Y-%m-%d")
            # A buoy reading is an observation, not a forecast. Trust it for
            # today and tomorrow only; beyond that it says nothing.
            fresh = -1 <= (tgt - btime).days <= 1
        except Exception:
            fresh = False
        if fresh and None not in (bh, bp, wh, wp) and (bh or wh):
            btotal = math.sqrt(bh ** 2 + wh ** 2)
            # Self-consistency: does the buoy's own total match the model's?
            if btotal > 0 and abs(btotal - hs) / max(hs, 0.1) <= 0.35:
                scale = hs / btotal          # rescale the split onto the model total
                return {
                    "long_hs": round(bh * scale, 2), "long_period": bp,
                    "long_dir": buoy.get("mean_dir"),
                    "short_hs": round(wh * scale, 2), "short_period": wp,
                    "hs_total": hs, "tm_total": tm,
                    "source": "buoy", "confidence": "high",
                    "note": (f"Split from buoy 46258: {bh}ft @ {bp}s swell over "
                             f"{wh}ft @ {wp}s windwave"),
                }

    # --- 2. model partition, only if internally consistent
    ph, pp = sw.get("swell_wave_height"), sw.get("swell_wave_period")
    wwh, wwp = sw.get("wind_wave_height"), sw.get("wind_wave_period")
    if None not in (ph, pp) and (ph or 0) > 0:
        pred = energy_mean_period(ph, pp, wwh or 0, wwp or 0)
        if pred is not None and abs(pred - tm) <= 2.0:
            ptotal = math.sqrt(ph ** 2 + (wwh or 0) ** 2)
            scale = hs / ptotal if ptotal > 0 else 1.0
            return {
                "long_hs": round(ph * scale, 2), "long_period": pp,
                "long_dir": sw.get("swell_wave_direction"),
                "short_hs": round((wwh or 0) * scale, 2), "short_period": wwp or 8.0,
                "hs_total": hs, "tm_total": tm,
                "source": "model", "confidence": "medium",
                "note": None,
            }

    # --- 3. nothing trustworthy
    return {
        "long_hs": hs, "long_period": tm, "long_dir": sw.get("swell_wave_direction"),
        "short_hs": 0.0, "short_period": None,
        "hs_total": hs, "tm_total": tm,
        "source": "none", "confidence": "low",
        "note": "No trustworthy swell/windwave split -- canyon read is approximate",
    }


def _canyon_factor(mode, period, sdir):
    """Multiplier the canyon applies to the LONG-PERIOD component only.

    Softened 2026-08-30 after an external fact-check. There is no hard 11-second
    activation threshold -- refraction over the canyon varies CONTINUOUSLY with
    period, direction and bathymetry, and the literature says gradients get
    larger beyond roughly 12 s rather than switching on at a number. The old code
    returned exactly 1.0 below 11 s and then ramped, which read as an on/off
    switch it has no basis to be.

    Now: a continuous ramp from 8 s (where a short windswell genuinely skims the
    shelf and the lens does almost nothing) to 18 s (full modelled effect), with
    no discontinuity anywhere.

    The magnitudes below remain MODELLED ESTIMATES from the canyon literature,
    not measured field constants. Treat them as directional.
    """
    if period is None:
        return 1.0, None, 0.0
    strength = max(0.0, min(1.0, (period - 8.0) / 10.0))  # 0 at 8s, full at 18s
    if strength <= 0.02:
        return 1.0, None, 0.0
    if mode == "amplify":
        # +80% to ~+100% at the focal band. The focal band migrates north as
        # period stretches: from due west, South Peak reads +72% at 14s but
        # -6% at 20s.
        if sdir is not None and 265 <= sdir <= 275 and period >= 19:
            return 0.98, ("Very long-period straight W -- the focal band has migrated "
                          "north. Torrey Pines may be the beneficiary today, not Black's"), strength
        amp = 1.0 + 0.85 * strength
        return amp, f"Canyon amplification ~+{int((amp - 1) * 100)}% (modelled) on the {period:.0f}s energy", strength
    if mode == "shadow_moderate":
        # Central-SD.md: "Long-period FROM THE SOUTH is the worst case -- canyon
        # shadow up to -64%." A long-period WNW is this spot's best swell.
        southerly = sdir is not None and 170 <= sdir <= 250
        red = 1.0 - (0.64 if southerly else 0.35) * strength
        who = "from the south, the worst case here" if southerly else "Black's is taking a cut"
        return red, f"Canyon shadow ~-{int((1 - red) * 100)}% on the {period:.0f}s energy -- {who}", strength
    if mode == "shadow_deep":
        red = 1.0 - 0.75 * strength
        return red, (f"Deep canyon shadow ~-{int((1 - red) * 100)}% on the {period:.0f}s "
                     f"energy -- long period actively hurts the Shores"), strength
    return 1.0, None, 0.0


def canyon_transform(brk, hs, period, sdir, sea=None):
    """Apply the La Jolla canyon lens from Central-SD.md.

    Black's amplifies on long-period; Scripps and the Shores are drained on the
    same swells. The lens only exists for groundswell -- short-period windswell
    skims the whole shelf and the three break much more alike.

    Returns (local_hs, note) when called without `sea` (legacy signature), or
    (local_hs, note, effective_period) when `sea` is supplied. See sea_state().
    """
    mode = brk.get("canyon", "none")
    if mode == "none" or hs is None or period is None:
        return (hs, None) if sea is None else (hs, None, period)

    # ---- legacy path: no decomposition available, whole sea as one component
    if sea is None:
        if period < 9:
            return hs, ("Short period -- the canyon is barely in play; the three "
                        "canyon spots break alike today")
        f, note, _ = _canyon_factor(mode, period, sdir)
        return round(hs * f, 1), note

    # ---- decomposed path
    lh, lp = sea["long_hs"], sea["long_period"]
    sh, sp = sea["short_hs"], sea["short_period"]
    ldir = sea.get("long_dir")
    if ldir is None:
        ldir = sdir

    if lp is None or lp < 9 or not lh:
        return hs, ("Short period -- the canyon is barely in play; the three "
                    "canyon spots break alike today"), period

    f, note, _ = _canyon_factor(mode, lp, ldir)

    # The lens acts on the long-period energy alone; the windwave passes over
    # the canyon untouched. Recombine in quadrature -- wave energy adds, heights
    # do not.
    lh2 = lh * f
    total = math.sqrt(lh2 ** 2 + (sh or 0) ** 2)

    # Effective period shifts with the new energy mix: amplified groundswell
    # pulls it up, a shadowed spot left with windchop pulls it down.
    e_long, e_short = lh2 ** 2, (sh or 0) ** 2
    if e_long + e_short > 0 and sp:
        eff = (e_long * lp + e_short * sp) / (e_long + e_short)
    else:
        eff = lp

    if sea["source"] == "buoy" and abs(lp - (sea["tm_total"] or lp)) >= 3:
        note = (note or "") + (f" (buoy reads {lp:.0f}s in the water; the model's "
                               f"blended {sea['tm_total']:.0f}s hides it)")
    return round(total, 1), note, round(eff, 1)


def score_break(brk, cond):
    """Return (score 0-100, breakdown dict, notes list)."""
    notes = []
    hs = cond["swell_hs"]
    period = cond["swell_period"]
    sdir = cond["swell_dir"]
    wspd = cond["wind_speed"]
    wdir = cond["wind_dir"]
    tide_h = cond["tide_h"]
    tide_dir = cond["tide_dir"]

    sea = cond.get("sea")
    if sea is None:
        local_hs, canyon_note = canyon_transform(brk, hs, period, sdir)
        eff_period = period
    else:
        local_hs, canyon_note, eff_period = canyon_transform(brk, hs, period, sdir, sea)
    if canyon_note:
        notes.append(canyon_note)
    # Face uses the EFFECTIVE period -- identical to the blended period for every
    # non-canyon spot, but at the three canyon spots the lens has changed the
    # energy mix and therefore how the sea shoals.
    face = face_height(local_hs, eff_period)

    # --- swell direction (0-28)
    windows = brk["swell_windows"]
    dist = min(arc_distance(sdir, lo, hi) for lo, hi in windows) if sdir is not None else 180
    # One continuous scale: distance from the spot's ideal angle, with an extra
    # penalty for falling outside the working window entirely. Scoring must be
    # monotonic -- a swell just outside a window can never beat one just inside.
    ideal = brk.get("ideal_dir")
    if sdir is None:
        dir_score = 14.0
    else:
        off = min((sdir - ideal) % 360, (ideal - sdir) % 360) if ideal is not None else 0
        dir_score = 28 - min(16, off * 0.20)
        if dist > 0:
            dir_score = max(0.0, dir_score - 6 - dist * 0.7)
            if dist > 12:
                notes.append(f"Swell is {compass(sdir)} -- outside this spot's window "
                             f"by ~{int(dist)}deg")
        elif off > 55:
            notes.append(f"Swell is {compass(sdir)} -- inside the window but well off this "
                         f"spot's best angle ({compass(ideal)})")

    # --- size fit (0-30)
    lo, hi = brk["size_ideal"]
    smin, smax = brk["size_min"], brk["size_max"]
    if face is None:
        size_score = 0
    elif lo <= face <= hi:
        size_score = 30
    elif face < lo:
        if face < smin:
            size_score = max(0, 12 * (face / smin) if smin else 0)
            notes.append(f"Under this spot's minimum (~{smin}ft face)")
        else:
            size_score = 12 + 18 * (face - smin) / max(0.1, lo - smin)
    else:
        if face > smax:
            size_score = max(0, 8 - (face - smax) * 3)
            notes.append(f"Over the closeout ceiling (~{smax}ft face)")
        else:
            size_score = 30 - 22 * (face - hi) / max(0.1, smax - hi)

    if brk.get("special") == "needs_size" and face is not None and face < smin:
        size_score *= 0.35
        notes.append("PB Point genuinely doesn't break most of the time -- needs an above-average swell")

    # --- period fit (0-8)
    pl, ph = brk.get("period_ideal", [8, 18])
    if brk.get("canyon") == "shadow_moderate" and sdir is not None and not (170 <= sdir <= 250):
        ph = 20  # Scripps' long-period problem is southerly swell, not period as such
    if period is None:
        per_score = 4
    elif pl <= period <= ph:
        per_score = 8
    else:
        off = pl - period if period < pl else period - ph
        per_score = max(0, 8 - off * 1.5)
    if brk.get("period_closeout_long") and period and period >= 15 and face and face > 5:
        per_score = max(0, per_score - 5)
        notes.append("Long-period straight-in at size is the worst case here -- it walls up and closes out")

    # --- tide (0-18)
    st = tide_state(tide_h)
    weight = brk.get("tide_weight", 1.0)
    if st == "unknown":
        tide_score = 9
    elif st in brk["tide_pref"]:
        tide_score = 18
    else:
        # weight > 1 = more tide-critical than average, so a wrong tide hurts more
        tide_score = 18 - 11 * min(1.6, weight)
        if weight >= 1.2:
            notes.append(f"Wrong tide, and this spot is tide-critical -- {brk['tide_note'].lower()}")
    if brk.get("tide_rising_bonus"):
        if tide_dir == "rising":
            tide_score = min(18, tide_score + 3)
            notes.append("Rising tide -- this spot specifically wants the push")
        elif tide_dir == "falling" and st in brk["tide_pref"]:
            tide_score -= 3
    tide_score = max(0, tide_score)

    # --- wind (0-16)
    wlo, whi = brk["wind_offshore"]
    tol = brk.get("wind_tolerance", 6)
    if wdir is None or wspd is None:
        wind_score = 8
    elif wspd <= 3:
        wind_score = 16
        notes.append("Near-glassy")
    elif in_arc(wdir, wlo, whi):
        # Offshore, but a gale is a gale -- it will still hold you out of waves
        wind_score = 16 if wspd <= 12 else max(0, 16 - (wspd - 12) * 0.8)
        if wspd > 25:
            wind_score = min(wind_score, 3)
            notes.append(f"Offshore but howling at {wspd:.0f}mph -- hard to get in")
    else:
        if wspd <= tol:
            wind_score = 11
        else:
            wind_score = max(0, 11 - (wspd - tol) * 1.6)
        # Sunset Cliffs kelp bed smooths NW onshore bump
        if brk.get("kelp_bonus") and in_arc(wdir, 290, 30):
            wind_score = min(16, wind_score + 7)
            notes.append("The kelp bed smooths this NW bump -- clean here when PB, Mission and OB are blown out")
        # La Jolla Shores: a south wind that ruins the county can go sideshore here.
        # Arc starts at 181 so it doesn't overlap this spot's own offshore arc.
        if brk.get("wind_south_ok") and in_arc(wdir, 181, 215):
            wind_score = min(16, wind_score + 6)
            notes.append("South wind isn't a session-killer here -- it can blow off or go sideshore")

    if brk.get("wind_deadline_hour") and cond["window_end_hour"] > brk["wind_deadline_hour"]:
        wind_score = max(0, wind_score - 3)
        notes.append(f"This stretch catches wind easily -- be in before {brk['wind_deadline_hour']}am")

    # --- crowd: information first, small tiebreaker second
    crowd = brk["crowd"]
    if cond.get("is_weekend") and brk.get("crowd_weekend"):
        crowd = brk["crowd_weekend"]
        notes.append("Weekend -- ultra-crowded and the vibe turns cutthroat here. Surf it midweek")
    crowd_pen = max(0, (crowd - 3)) * 2.0

    total = dir_score + size_score + per_score + tide_score + wind_score - crowd_pen

    # The folder's own surf-forecast star rating is a ceiling. La Jolla Shores is
    # rated 2/5, "lowest of the three", "the overflow spot" -- it should never
    # outrank Black's on a mechanical tie.
    cap = brk.get("quality_cap")
    if cap is not None and total > cap:
        total = cap

    breakdown = {
        "swell_dir": round(dir_score, 1), "size": round(size_score, 1),
        "period": round(per_score, 1), "tide": round(tide_score, 1),
        "wind": round(wind_score, 1), "crowd": -round(crowd_pen, 1),
    }
    return round(min(100, max(0, total))), breakdown, notes, face, local_hs, crowd


def pick_board(brk, face, ctx=None):
    """Ladder pick by face height, then any condition-gated swap.

    The ladder answers "how big is it". Swaps answer "what shape is it in" --
    some boards are gated by surface texture and takeoff shape rather than by
    size. The mini-Simmons is the case that forced this: it is a planing hull,
    not an ankle-to-waist groveller, and it holds well past waist-high on a
    clean organised face while being genuinely bad on a steep late drop. See
    ../02-Gear/Mini-Simmons-Deep-Dive.md.

    Swap gates use local WIND (mph) and PERIOD, deliberately not wind-wave
    height -- the marine model dumps ~all energy into the swell partition and
    ~0 into wind wave, so windwave is not a trustworthy texture proxy here.
    See "Two calibrations that look wrong but aren't" in README.md.
    """
    if face is None:
        return None, None, "No size estimate"
    primary = backup = note = None
    for rung in brk["board_ladder"]:
        if rung[0] <= face < rung[1]:
            primary, backup, note = rung[2], rung[3], rung[4]
            break
    else:
        last = brk["board_ladder"][-1]
        primary, backup, note = last[2], last[3], last[4]

    # A swap never overrides a "don't paddle out" rung (null primary).
    if primary is None or not ctx:
        return primary, backup, note

    for sw in brk.get("board_swaps", []):
        lo, hi = sw["face"]
        if not (lo <= face < hi):
            continue
        wspd = ctx.get("wind_speed")
        if wspd is not None and wspd > sw.get("max_wind", 999):
            continue
        per = ctx.get("swell_period")
        if per is not None and per < sw.get("min_period", 0):
            continue
        return sw["primary"], sw.get("backup"), sw["note"]
    return primary, backup, note


def verdict_label(score):
    if score >= 82:
        return "Go", "go"
    if score >= 67:
        return "Worth it", "good"
    if score >= 50:
        return "Marginal", "marginal"
    return "Skip", "skip"


# ---------------------------------------------------------------- assembly

def active_breaks(cfg):
    """Breaks the brief scores and shows. An entry with "hidden": true keeps
    its research and scoring rules in breaks.json but is skipped entirely --
    the flag is the knob for spots that are written up but not in the daily
    rotation (Oceanside Pier: too far to drive, per its hidden_note)."""
    return [b for b in cfg["breaks"] if not b.get("hidden")]


def build(day=None):
    day = day or date.today().strftime("%Y-%m-%d")
    with open(os.path.join(HERE, "breaks.json")) as f:
        cfg = json.load(f)

    marine = get_marine(day)
    weather = get_weather(day)
    hilo, curve = get_tides(day)
    buoy = get_buoy()
    rain = water.get_rain()
    river = water.get_river()

    mh = marine["hourly"]
    sunset_iso = weather["north"]["daily"]["sunset"][0]
    sunrise_iso = weather["north"]["daily"]["sunrise"][0]
    sunset_dt = datetime.strptime(sunset_iso, "%Y-%m-%dT%H:%M")
    ev_end = sunset_dt.hour + sunset_dt.minute / 60.0
    ev_start = ev_end - EVENING_LEAD_HOURS

    windows = [
        {"key": "morning", "label": "Dawn patrol", "range": MORNING,
         "time_txt": "7:00 - 8:30am"},
        {"key": "evening", "label": "Evening glass", "range": (ev_start, ev_end),
         "time_txt": f"{fmt_hour(ev_start)} - {fmt_hour(ev_end)} (sunset {sunset_dt.strftime('%-I:%M%p').lower()})"},
    ]

    results = []
    for w in windows:
        h0, h1 = w["range"]
        sw = window_avg(mh, ["swell_wave_height", "swell_wave_period",
                             "wind_wave_height", "wave_height", "wave_period"], h0, h1)
        sdir = circ_avg(mh, "swell_wave_direction", h0, h1)
        tdir = circ_avg(mh, "wave_direction", h0, h1)
        sea = sea_state({**sw, "swell_wave_direction": sdir}, buoy, day)

        # Which direction does SCORING use? Not the model's swell partition --
        # that's the same untrustworthy field the canyon fix stopped relying on,
        # and direction is the single largest scoring lever (28 pts).
        #
        # Found 2026-08-30 when Swami's was added: on a measured 16.7s SSW
        # groundswell the model's partition said 279 (W), which scored Swami's
        # 26.8/28 and ranked it #1 in the county -- a W/NW-only point, on a
        # south swell it barely sees. The buoy's measured 209 (SSW) scores it
        # 0.0. A 27-point swing, and the brief would have sent him 32 minutes
        # north to a spot that wasn't breaking.
        #
        # So: use the long-period component's direction when there IS a real
        # long-period component (that's the energy making rideable waves), and
        # fall back to the TOTAL sea direction -- a trusted field -- not the
        # partition.
        dom_dir, dir_source = tdir, "total"
        if sea and sea["source"] in ("buoy", "model") and sea.get("long_dir") is not None:
            el = (sea["long_hs"] or 0) ** 2
            es = (sea["short_hs"] or 0) ** 2
            share = el / (el + es) if (el + es) > 0 else 0
            if share >= 0.40 and (sea["long_period"] or 0) >= 10:
                dom_dir, dir_source = sea["long_dir"], sea["source"]

        wn = weather["north"]["hourly"]
        ws = weather["south"]["hourly"]
        wnorth = window_avg(wn, ["wind_speed_10m", "temperature_2m"], h0, h1)
        wsouth = window_avg(ws, ["wind_speed_10m"], h0, h1)
        wdir_n = circ_avg(wn, "wind_direction_10m", h0, h1)
        wdir_s = circ_avg(ws, "wind_direction_10m", h0, h1)

        mid_dt = datetime.strptime(day, "%Y-%m-%d") + timedelta(hours=(h0 + h1) / 2)
        tide_h, tide_dir = tide_at(curve, mid_dt)

        is_weekend = datetime.strptime(day, "%Y-%m-%d").weekday() >= 5

        scored = []
        for brk in active_breaks(cfg):
            north = brk["lat"] > 32.78
            cond = {
                # Total wave height drives size -- it is what tracks the buoy.
                "swell_hs": sw["wave_height"],
                "swell_period": sw["wave_period"],
                "swell_dir": dom_dir,
                "wind_speed": wnorth["wind_speed_10m"] if north else wsouth["wind_speed_10m"],
                "wind_dir": wdir_n if north else wdir_s,
                "tide_h": tide_h, "tide_dir": tide_dir,
                "window_end_hour": h1, "is_weekend": is_weekend,
                "sea": sea,
            }
            score, bd, notes, face, local_hs, crowd = score_break(brk, cond)
            primary, backup, bnote = pick_board(brk, face, cond)
            label, cls = verdict_label(score)

            # Water quality is a veto, not a scoring component. A severe read
            # blocks the spot outright and suppresses the board call -- there is
            # no board that makes bad water a good idea.
            wq = water.assess(brk, rain, river)
            if wq["blocked"]:
                label, cls = "Don't paddle", "blocked"
                primary = backup = None
                bnote = wq["headline"]

            scored.append({
                "name": brk["name"], "score": score, "label": label, "cls": cls,
                "breakdown": bd, "notes": notes, "face_ft": face,
                "local_hs": local_hs, "board_primary": primary,
                "board_backup": backup, "board_note": bnote,
                "verdict": brk["verdict"], "hazards": brk["hazards"],
                "crowd": crowd, "localism": brk.get("localism", 1),
                "skill": brk["skill"], "tide_note": brk["tide_note"],
                "wind_local": cond["wind_speed"], "wind_dir_local": cond["wind_dir"],
                "wind_dir_local_txt": compass(cond["wind_dir"]),
                # CLAUDE.md: the quiver is "deep in the ankle-to-head range,
                # nothing built for overhead" -- so anything well overhead is a
                # gap anywhere, not just at the two spots that name it.
                "gap": face is not None and (
                    face >= brk.get("gap_above", 999) or face >= 8),
                "water": wq, "surf_score": score,
                "region": brk.get("region"),
                "drive_minutes": brk.get("drive_minutes"),
                "far": (brk.get("drive_minutes") or 0) > DRIVE_FLAG_MINUTES,
            })
        # Blocked spots sink to the bottom regardless of how good the surf is.
        scored.sort(key=lambda x: (x["water"]["blocked"], -x["score"]))

        results.append({
            "key": w["key"], "label": w["label"], "time_txt": w["time_txt"],
            "swell_hs": sw["wave_height"],
            "swell_period": sw["wave_period"],
            "swell_dir": sdir, "swell_dir_txt": compass(sdir),
            "dom_dir": dom_dir, "dom_dir_txt": compass(dom_dir), "dir_source": dir_source,
            "total_dir": tdir, "total_dir_txt": compass(tdir),
            "swell_partition_ft": sw["swell_wave_height"],
            "swell_partition_period": sw["swell_wave_period"],
            "face_est": face_height(sw["wave_height"], sw["wave_period"]),
            "windwave_ft": sw["wind_wave_height"],
            "sea": sea,
            "wind_speed_n": wnorth["wind_speed_10m"], "wind_dir_n": wdir_n,
            "wind_dir_n_txt": compass(wdir_n),
            "wind_speed_s": wsouth["wind_speed_10m"], "wind_dir_s": wdir_s,
            "wind_dir_s_txt": compass(wdir_s),
            "air_temp": wnorth["temperature_2m"],
            "tide_h": tide_h, "tide_dir": tide_dir, "tide_state": tide_state(tide_h),
            "breaks": scored,
        })

    tides_today = [{"time": p["t"][11:], "height": round(float(p["v"]), 1),
                    "type": "High" if p["type"] == "H" else "Low"}
                   for p in hilo if p["t"].startswith(day)]

    return {
        "date": day,
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sunrise": sunrise_iso[11:], "sunset": sunset_iso[11:],
        "tides": tides_today, "buoy": buoy, "windows": results,
        "rain": rain, "river": river,
        "water_day": water.day_summary(rain, river, results),
    }


def fmt_hour(h):
    hh = int(h)
    mm = int(round((h - hh) * 60))
    if mm == 60:
        hh, mm = hh + 1, 0
    ampm = "am" if hh < 12 else "pm"
    disp = hh % 12 or 12
    return f"{disp}:{mm:02d}{ampm}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--json")
    args = ap.parse_args()
    data = build(args.date)
    out = json.dumps(data, indent=2)
    if args.json:
        with open(args.json, "w") as f:
            f.write(out)
        print(f"wrote {args.json}")
    else:
        print(out)
