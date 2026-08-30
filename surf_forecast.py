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

def canyon_transform(brk, hs, period, sdir):
    """Apply the La Jolla canyon lens from Central-SD.md.

    Black's amplifies on long-period; Scripps and the Shores are drained on the
    same swells. The lens only exists for groundswell -- short-period windswell
    skims the whole shelf and the three break much more alike.
    """
    mode = brk.get("canyon", "none")
    if mode == "none" or hs is None or period is None:
        return hs, None
    if period < 11:
        return hs, "Short period -- the canyon is barely in play; the three canyon spots break alike today"

    strength = min(1.0, (period - 11) / 7.0)  # 0 at 11s, full by 18s

    if mode == "amplify":
        # +80% to ~+100% at the focal band. The focal band migrates north as
        # period stretches: from due west, South Peak reads +72% at 14s but
        # -6% at 20s.
        if sdir is not None and 265 <= sdir <= 275 and period >= 19:
            return round(hs * 0.98, 1), ("Very long-period straight W -- the focal band has migrated "
                                         "north. Torrey Pines may be the beneficiary today, not Black's")
        amp = 1.0 + 0.85 * strength
        return round(hs * amp, 1), f"Canyon amplification ~+{int((amp - 1) * 100)}% at {period:.0f}s"
    if mode == "shadow_moderate":
        # Central-SD.md: "Long-period FROM THE SOUTH is the worst case -- canyon
        # shadow up to -64%." A long-period WNW is this spot's best swell.
        southerly = sdir is not None and 170 <= sdir <= 250
        red = 1.0 - (0.64 if southerly else 0.35) * strength
        who = "from the south, the worst case here" if southerly else ""
        return round(hs * red, 1), (f"Canyon shadow ~-{int((1 - red) * 100)}%"
                                    + (f" -- {who}" if who else " -- Black's is taking a cut"))
    if mode == "shadow_deep":
        red = 1.0 - 0.75 * strength
        return round(hs * red, 1), (f"Deep canyon shadow ~-{int((1 - red) * 100)}% -- "
                                    f"long period actively hurts the Shores")
    return hs, None


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

    local_hs, canyon_note = canyon_transform(brk, hs, period, sdir)
    if canyon_note:
        notes.append(canyon_note)
    face = face_height(local_hs, period)

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
        for brk in cfg["breaks"]:
            north = brk["lat"] > 32.78
            cond = {
                # Total wave height drives size -- it is what tracks the buoy.
                "swell_hs": sw["wave_height"],
                "swell_period": sw["wave_period"],
                "swell_dir": sdir,
                "wind_speed": wnorth["wind_speed_10m"] if north else wsouth["wind_speed_10m"],
                "wind_dir": wdir_n if north else wdir_s,
                "tide_h": tide_h, "tide_dir": tide_dir,
                "window_end_hour": h1, "is_weekend": is_weekend,
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
            })
        # Blocked spots sink to the bottom regardless of how good the surf is.
        scored.sort(key=lambda x: (x["water"]["blocked"], -x["score"]))

        results.append({
            "key": w["key"], "label": w["label"], "time_txt": w["time_txt"],
            "swell_hs": sw["wave_height"],
            "swell_period": sw["wave_period"],
            "swell_dir": sdir, "swell_dir_txt": compass(sdir),
            "total_dir": tdir, "total_dir_txt": compass(tdir),
            "swell_partition_ft": sw["swell_wave_height"],
            "swell_partition_period": sw["swell_wave_period"],
            "face_est": face_height(sw["wave_height"], sw["wave_period"]),
            "windwave_ft": sw["wind_wave_height"],
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
