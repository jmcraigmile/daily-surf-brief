#!/usr/bin/env python3
"""
Invariant suite for the daily surf brief. No network -- everything runs on
breaks.json and synthetic conditions, so it can gate CI before a publish.

Covers the README's "Verifying a change" list plus regressions for bugs found
in the 2026-08-27 and 2026-08-29 audits. Run: python3 test_brief.py
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import render
import surf_forecast as sf
import water

CFG = json.load(open(os.path.join(HERE, "breaks.json")))
BREAKS = CFG["breaks"]

# The nine boards from 02-Gear/Owned-and-Wishlist.md, hardcoded because that
# file lives outside this repo. If the quiver changes, update BOTH.
OWNED_BOARDS = {
    "5'4 Mini-Simmons", "5'8 Fish", "6'0 Surfer Rosa", "6'5 Egg",
    "7'6 Magic", "9'4 Pink Panther", "11'0 Chris Craft",
    "7'0 CI Waterhog", "9'0 Ron Jon",
}

FAILURES = []


def check(ok, msg):
    if not ok:
        FAILURES.append(msg)


def cond(**kw):
    base = dict(swell_hs=4.0, swell_period=12, swell_dir=280, wind_speed=5,
                wind_dir=90, tide_h=2.5, tide_dir="rising",
                window_end_hour=8.5, is_weekend=False)
    base.update(kw)
    return base


# ---------------------------------------------------------------- breaks.json

def test_ladders():
    for b in BREAKS:
        lad = b["board_ladder"]
        check(lad[0][0] == 0, f"{b['name']}: ladder starts at {lad[0][0]}, not 0")
        check(lad[-1][1] == 99, f"{b['name']}: ladder ends at {lad[-1][1]}, not 99")
        for i in range(len(lad) - 1):
            check(lad[i][1] == lad[i + 1][0],
                  f"{b['name']}: ladder gap {lad[i][1]} -> {lad[i + 1][0]}")


def test_board_names():
    for b in BREAKS:
        for rung in b["board_ladder"]:
            for board in (rung[2], rung[3]):
                check(board is None or board in OWNED_BOARDS,
                      f"{b['name']}: unknown board {board!r}")
        # Swaps carry board names too -- a typo here invents a board just as
        # silently as one in a rung.
        for sw in b.get("board_swaps", []):
            for board in (sw["primary"], sw.get("backup")):
                check(board is None or board in OWNED_BOARDS,
                      f"{b['name']}: unknown swap board {board!r}")


def test_board_swaps():
    """Condition-gated swaps: well-formed, and they only ever fire in-band."""
    for b in BREAKS:
        for sw in b.get("board_swaps", []):
            lo, hi = sw["face"]
            check(0 <= lo < hi, f"{b['name']}: bad swap band {sw['face']}")
            check("note" in sw and sw["note"], f"{b['name']}: swap has no note")
            ctx = cond(wind_speed=sw.get("max_wind", 8),
                       swell_period=sw.get("min_period", 12))
            # In band, gates satisfied -> the swap wins.
            mid = (lo + hi) / 2
            check(sf.pick_board(b, mid, ctx)[0] == sw["primary"],
                  f"{b['name']}: swap didn't fire at {mid}ft in clean conditions")
            # Blown out -> ladder stands.
            blown = cond(wind_speed=sw.get("max_wind", 8) + 15,
                         swell_period=sw.get("min_period", 12))
            check(sf.pick_board(b, mid, blown) == sf.pick_board(b, mid),
                  f"{b['name']}: swap fired at {sw.get('max_wind')}+15mph wind")
            # Short-period slop -> ladder stands.
            if sw.get("min_period"):
                slop = cond(wind_speed=sw.get("max_wind", 8),
                            swell_period=sw["min_period"] - 2)
                check(sf.pick_board(b, mid, slop) == sf.pick_board(b, mid),
                      f"{b['name']}: swap fired below its period gate")
            # Above the band -> ladder stands.
            check(sf.pick_board(b, hi + 0.5, ctx) == sf.pick_board(b, hi + 0.5),
                  f"{b['name']}: swap fired above its band")


def test_swaps_never_override_dont_paddle():
    """A null primary means don't paddle out. No swap may undo that."""
    for b in BREAKS:
        for rung in b["board_ladder"]:
            if rung[2] is None:
                face = (rung[0] + min(rung[1], rung[0] + 4)) / 2
                got = sf.pick_board(b, face, cond(wind_speed=1, swell_period=14))
                check(got[0] is None,
                      f"{b['name']}: swap overrode a don't-paddle rung at {face}ft")


# ------------------------------------------------------------------- scoring

def dir_score(b, sdir):
    _, bd, _, _, _, _ = sf.score_break(b, cond(swell_dir=sdir))
    return bd["swell_dir"]


def test_direction_peaks_at_ideal():
    for b in BREAKS:
        peak = dir_score(b, b["ideal_dir"])
        for d in range(0, 360, 2):
            check(dir_score(b, d) <= peak + 1e-9,
                  f"{b['name']}: direction {d} outscores ideal_dir")


def test_direction_monotonic_at_window_edges():
    for b in BREAKS:
        for lo, hi in b["swell_windows"]:
            if (hi - lo) % 360 >= 350:
                continue  # all-directions window (PB Drive) has no edges
            for edge, outside in ((lo, (lo - 3) % 360), (hi, (hi + 3) % 360)):
                check(dir_score(b, outside) <= dir_score(b, edge % 360) + 1e-9,
                      f"{b['name']}: just outside {edge} beats just inside")


def test_component_maxima():
    caps = [("swell_dir", 28), ("size", 30), ("period", 8),
            ("tide", 18), ("wind", 16)]
    for b in BREAKS:
        for sdir in range(0, 360, 30):
            for hs, per in [(1, 8), (3, 12), (5, 16), (8, 18), (12, 20)]:
                for th, td in [(0.5, "rising"), (2.5, "falling"), (5, "rising")]:
                    for wspd, wdir in [(2, 90), (8, 60), (15, 300), (25, 200)]:
                        s, bd, _, _, _, _ = sf.score_break(b, cond(
                            swell_hs=hs, swell_period=per, swell_dir=sdir,
                            wind_speed=wspd, wind_dir=wdir, tide_h=th,
                            tide_dir=td, window_end_hour=19.5, is_weekend=True))
                        check(0 <= s <= 100, f"{b['name']}: total {s} out of 0-100")
                        for k, mx in caps:
                            check(0 <= bd[k] <= mx,
                                  f"{b['name']}: {k}={bd[k]} outside 0-{mx}")


# --------------------------------------------------------------------- water

STORM_RAIN = {"ok": True, "total_96h": 1.4, "event_inches": 1.2,
              "last_rain": "x", "hours_since": 30.0, "tier": "heavy",
              "tier_hours": 96}
STORM_RIVER = {"ok": True, "cfs": 220.0, "when": "x", "state": "flowing",
               "label": "flowing"}
ACUTE_RAIN = {"ok": True, "total_96h": 0.4, "event_inches": 0.4,
              "last_rain": "x", "hours_since": 10.0, "tier": "moderate",
              "tier_hours": 72}
DRY_RIVER = {"ok": True, "cfs": 3.0, "when": "x", "state": "baseflow",
             "label": "dry-weather baseflow"}


def test_storm_blocks_river_mouths():
    for b in BREAKS:
        wq = water.assess(b, STORM_RAIN, STORM_RIVER)
        if b["name"] in ("OB Pier", "OB Jetty"):
            check(wq["blocked"], f"{b['name']} not blocked in storm sim")
        else:
            check(wq["level"] in ("avoid", "severe"),
                  f"{b['name']} not flagged in storm sim ({wq['level']})")


def test_acute_pulse_blocks_everywhere():
    for b in BREAKS:
        wq = water.assess(b, ACUTE_RAIN, DRY_RIVER)
        check(wq["blocked"], f"{b['name']} not blocked in acute-pulse sim")


def test_dry_weather_clear_or_chronic_only():
    rain = {"ok": True, "total_96h": 0.0, "event_inches": 0.0, "last_rain": None,
            "hours_since": None, "tier": None, "tier_hours": 0}
    for b in BREAKS:
        wq = water.assess(b, rain, DRY_RIVER)
        check(not wq["blocked"], f"{b['name']} blocked in dry weather")
        chronic = (b.get("water") or {}).get("chronic", "normal")
        expected = "caution" if chronic in ("elevated", "high") else "clear"
        check(wq["level"] == expected,
              f"{b['name']}: dry-weather level {wq['level']}, expected {expected}")


# -------------------------------------------------------------------- render

def synthetic_break(name, blocked=False):
    wq = ({"level": "severe", "headline": "Do not paddle out here",
           "reasons": ["storm sim"], "blocked": True, "note": "", "chronic": "high"}
          if blocked else
          {"level": "clear", "headline": "Water looks fine", "reasons": [],
           "blocked": False, "note": "", "chronic": "normal"})
    return {
        "name": name, "score": 70, "surf_score": 70,
        "label": "Don't paddle" if blocked else "Worth it",
        "cls": "blocked" if blocked else "good",
        "breakdown": {"swell_dir": 20, "size": 25, "period": 6, "tide": 12,
                      "wind": 10, "crowd": -2},
        "notes": ["a note"], "face_ft": 3.5, "local_hs": 3.0,
        "board_primary": None if blocked else "5'8 Fish",
        "board_backup": None if blocked else "6'5 Egg",
        "board_note": "Do not paddle out here" if blocked else "fine",
        "verdict": "v", "hazards": "h", "crowd": 3, "localism": 1,
        "skill": "All levels", "tide_note": "t", "wind_local": 5,
        "wind_dir_local": 90, "wind_dir_local_txt": "E",
        "gap": False, "water": wq,
    }


def synthetic_data(buoy):
    brks = [synthetic_break("Crystal Pier"), synthetic_break("PB Drive"),
            synthetic_break("Scripps Pier"), synthetic_break("Black's Beach"),
            synthetic_break("OB Pier", blocked=True)]
    win = {
        "key": "morning", "label": "Dawn patrol", "time_txt": "7:00 - 8:30am",
        "swell_hs": 4.0, "swell_period": 12, "swell_dir": 280,
        "swell_dir_txt": "W", "total_dir": 278, "total_dir_txt": "W",
        "swell_partition_ft": 3.0, "swell_partition_period": 14,
        "face_est": 4.5, "windwave_ft": 1.0,
        "wind_speed_n": 5.0, "wind_dir_n": 90, "wind_dir_n_txt": "E",
        "wind_speed_s": 6.0, "wind_dir_s": 95, "wind_dir_s_txt": "E",
        "air_temp": 68.0, "tide_h": 2.5, "tide_dir": "rising",
        "tide_state": "mid", "breaks": brks,
    }
    return {
        "date": "2026-08-29", "generated": "2026-08-29 05:45",
        "sunrise": "06:20", "sunset": "19:15",
        "tides": [{"time": "05:12", "height": 1.2, "type": "Low"},
                  {"time": "11:40", "height": 5.3, "type": "High"}],
        "buoy": buoy, "windows": [win, dict(win, key="evening",
                                            label="Evening glass")],
        "rain": {"ok": True, "total_96h": 0.0, "event_inches": 0.0,
                 "last_rain": None, "hours_since": None, "tier": None,
                 "tier_hours": 0},
        "river": {"ok": True, "cfs": 3.0, "when": "x", "state": "baseflow",
                  "label": "dry-weather baseflow"},
        "water_day": {"worst": "severe",
                      "line": "OB Pier blocked on water quality.",
                      "blocked": ["OB Pier"]},
    }


def test_render_blocked_and_no_none():
    html = render.render(synthetic_data(buoy={
        "time": "2026-08-29 12:00 UTC", "swell_ft": 3.2, "swell_period": 14.0,
        "swell_dir_txt": "WNW", "windwave_ft": 1.1, "windwave_period": 5.0,
        "mean_dir": 285, "steepness": "SWELL"}))
    check("Blocked on water quality" in html, "blocked section missing from render")
    check("Do not paddle out here" in html, "blocked headline missing from render")
    check("None" not in html, "None leaked into rendered page")
    check('name="viewport"' in html, "viewport meta missing -- phone renders at 980px")
    check("<!doctype html>" in html, "doctype missing")
    # The blocked spot must never be the day's recommendation.
    verdict = html.split('class="dayline">')[1].split("</p>")[0]
    check("OB Pier</strong> is" not in verdict, "blocked spot named as the day's call")


def test_render_buoy_partial_data():
    """Regression, 2026-08-29 audit: NDBC 'MM' fields parse to None and leaked
    raw into the buoy line."""
    html = render.render(synthetic_data(buoy={
        "time": "2026-08-29 12:00 UTC", "swell_ft": None, "swell_period": None,
        "swell_dir_txt": None, "windwave_ft": None, "windwave_period": None,
        "mean_dir": None, "steepness": "N/A"}))
    check("None" not in html, "buoy None leaked into rendered page")


# ---------------------------------------------------------------------- main

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    if FAILURES:
        print(f"FAIL ({len(FAILURES)}):")
        for f in FAILURES[:30]:
            print(" -", f)
        sys.exit(1)
    print(f"ok -- {len(tests)} test groups, 0 failures")
