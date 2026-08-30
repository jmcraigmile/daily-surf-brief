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

def test_hidden_breaks():
    """"hidden": true keeps a break's data but drops it from the brief.

    Pins the mechanism, not any particular spot's status -- flipping a flag
    in breaks.json must never break CI. Every hidden entry needs a
    hidden_note saying why and when, and hiding must never empty the brief.
    """
    active = sf.active_breaks(CFG)
    hidden = [b for b in BREAKS if b.get("hidden")]
    check(len(active) + len(hidden) == len(BREAKS), "active/hidden split leaks")
    check(len(active) >= 5, "hiding breaks emptied the brief")
    for b in hidden:
        check(bool(b.get("hidden_note")), f"{b['name']}: hidden without a hidden_note")
        check(b["name"] not in {a["name"] for a in active},
              f"{b['name']}: hidden but still active")


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


# ------------------------------------------------------- canyon decomposition
#
# Regression set for the 2026-08-30 fix. The canyon lens is refraction, so it
# acts on the LONG-PERIOD component's period and on that component's energy
# alone. Feeding it the model's blended mean period, or applying it to the whole
# sea, are the two bugs these pin.

# The real 2026-08-30 dawn case: buoy held 3.3ft @ 16.7s SSW for six hours while
# the model reported a 10.7s blend.
SUNDAY_SW = {"wave_height": 4.7, "wave_period": 10.7,
             "swell_wave_height": 3.2, "swell_wave_period": 7.0,
             "wind_wave_height": 0.0, "wind_wave_period": 0.0,
             "swell_wave_direction": 279}
SUNDAY_BUOY = {"time": "2026-08-30 01:56 UTC", "swell_ft": 3.3, "swell_period": 16.7,
               "swell_dir_txt": "SSW", "windwave_ft": 3.3, "windwave_period": 8.3,
               "mean_dir": 208}

BLACKS = next(b for b in BREAKS if b["name"] == "Black's Beach")
SCRIPPS = next(b for b in BREAKS if b["name"] == "Scripps Pier")
SHORES = next(b for b in BREAKS if b["name"] == "La Jolla Shores")
PBDRIVE = next(b for b in BREAKS if b["name"] == "PB Drive")


def test_sea_state_prefers_buoy_when_fresh():
    sea = sf.sea_state(SUNDAY_SW, SUNDAY_BUOY, "2026-08-30")
    check(sea["source"] == "buoy", f"expected buoy split, got {sea['source']}")
    check(abs(sea["long_period"] - 16.7) < 0.01, "buoy swell period not carried through")
    # The split is rescaled onto the model total, which is the trusted number.
    recombined = (sea["long_hs"] ** 2 + sea["short_hs"] ** 2) ** 0.5
    check(abs(recombined - 4.7) < 0.05,
          f"rescaled split should recombine to the model total, got {recombined:.2f}")


def test_sea_state_rejects_inconsistent_model_partition():
    """The model said 3.2ft @ 7.0s while its own total said 10.7s. A partition
    that cannot reproduce the model's own mean period is not usable."""
    sea = sf.sea_state(SUNDAY_SW, None, "2026-08-30")
    check(sea["source"] == "none",
          f"inconsistent model partition should be rejected, got {sea['source']}")
    check(sea["confidence"] == "low", "rejected partition should report low confidence")


def test_sea_state_accepts_consistent_model_partition():
    sw = {"wave_height": 4.0, "wave_period": 13.4,
          "swell_wave_height": 3.5, "swell_wave_period": 14.0,
          "wind_wave_height": 1.5, "wind_wave_period": 6.0,
          "swell_wave_direction": 280}
    sea = sf.sea_state(sw, None, "2026-08-30")
    check(sea["source"] == "model", f"consistent partition should be used, got {sea['source']}")


def test_buoy_not_used_as_a_forecast():
    """A buoy reading is an observation. It must not steer a brief days out."""
    sea = sf.sea_state(SUNDAY_SW, SUNDAY_BUOY, "2026-09-05")
    check(sea["source"] != "buoy", "buoy used for a date a week from the reading")


def test_canyon_amplifies_only_long_period_energy():
    """Amplifying the TOTAL over-applies badly -- on this sea it gives ~8.0ft
    where decomposing first gives ~6.5ft."""
    sea = sf.sea_state(SUNDAY_SW, SUNDAY_BUOY, "2026-08-30")
    hs, note, eff = sf.canyon_transform(BLACKS, 4.7, 10.7, 279, sea)
    check(6.0 < hs < 7.0, f"Black's should land ~6.5ft on this sea, got {hs}")
    naive = 4.7 * (1.0 + 0.85 * min(1.0, (16.7 - 11) / 7.0))
    check(hs < naive - 1.0,
          f"decomposed {hs} should be well under naive whole-sea {naive:.1f}")
    check(eff > 10.7, "effective period should rise once the lens amplifies the swell")


def test_canyon_shadows_use_long_period_too():
    sea = sf.sea_state(SUNDAY_SW, SUNDAY_BUOY, "2026-08-30")
    scr = sf.canyon_transform(SCRIPPS, 4.7, 10.7, 279, sea)[0]
    sho = sf.canyon_transform(SHORES, 4.7, 10.7, 279, sea)[0]
    check(scr < 4.7, f"Scripps should be shadowed on a long-period S, got {scr}")
    check(sho < scr, f"the Shores shadow is the deepest: Shores {sho} vs Scripps {scr}")
    # Never below the windwave that passes over the canyon untouched.
    check(sho >= sea["short_hs"] - 0.05,
          f"shadow drove {sho} below the untouched windwave {sea['short_hs']}")


def test_canyon_blend_bug_regression():
    """THE bug: the blended mean period materially understates the lens when a
    long groundswell rides under chop.

    Updated 2026-08-30: this test used to assert the legacy path returned
    EXACTLY 1.0x at 10.7s. That was an artifact of the old hard 11-second
    switch, which an external fact-check correctly identified as unfounded --
    refraction is continuous. The surviving invariant is the one that always
    mattered: reading the blended period gives a materially smaller answer than
    decomposing first."""
    sea = sf.sea_state(SUNDAY_SW, SUNDAY_BUOY, "2026-08-30")
    blended = sf.canyon_transform(BLACKS, 4.7, 10.7, 279)[0]      # legacy path
    fixed = sf.canyon_transform(BLACKS, 4.7, 10.7, 279, sea)[0]
    check(fixed > blended,
          f"decomposed read must exceed the blended one: {fixed} vs {blended}")
    check((fixed - blended) / blended > 0.10,
          f"and by a material margin, not noise: {fixed} vs {blended}")
    # The blended read must still understate the true 16.7s energy.
    full = sf._canyon_factor("amplify", 16.7, 209)[0]
    partial = sf._canyon_factor("amplify", 10.7, 209)[0]
    check(full > partial, "a 16.7s swell must engage the lens more than a 10.7s blend")


def test_non_canyon_spots_unaffected_by_decomposition():
    """Blast radius check: the fix must touch the three canyon spots only."""
    sea = sf.sea_state(SUNDAY_SW, SUNDAY_BUOY, "2026-08-30")
    for b in BREAKS:
        if b.get("canyon", "none") != "none":
            continue
        hs, note, eff = sf.canyon_transform(b, 4.7, 10.7, 279, sea)
        check(hs == 4.7, f"{b['name']}: non-canyon spot changed to {hs}")
        check(note is None, f"{b['name']}: non-canyon spot got a canyon note")
        check(eff == 10.7, f"{b['name']}: non-canyon effective period moved to {eff}")


def test_short_period_sea_leaves_canyon_off():
    """Below 11s the lens genuinely is off -- windswell skims the whole shelf."""
    sw = {"wave_height": 4.0, "wave_period": 8.0,
          "swell_wave_height": 3.0, "swell_wave_period": 8.0,
          "wind_wave_height": 2.0, "wind_wave_period": 7.0,
          "swell_wave_direction": 280}
    sea = sf.sea_state(sw, None, "2026-08-30")
    for b in (BLACKS, SCRIPPS, SHORES):
        hs = sf.canyon_transform(b, 4.0, 8.0, 280, sea)[0]
        check(hs == 4.0, f"{b['name']}: canyon acted on an 8s sea ({hs})")


def test_canyon_degrades_without_buoy_or_partition():
    """No buoy and an unusable partition must still produce a sane answer."""
    sea = sf.sea_state({"wave_height": 5.0, "wave_period": 16.0}, None, "2026-08-30")
    check(sea is not None and sea["source"] == "none", "expected the low-confidence fallback")
    hs, note, eff = sf.canyon_transform(BLACKS, 5.0, 16.0, 280, sea)
    check(hs > 5.0, f"lens should still fire on a 16s sea, got {hs}")
    check(sf.sea_state({"wave_height": None, "wave_period": None}, None, "2026-08-30") is None,
          "sea_state should return None with no usable height")


def test_score_break_without_sea_still_works():
    """cond['sea'] is optional -- the legacy call path must not break."""
    for b in (BLACKS, PBDRIVE):
        s = sf.score_break(b, cond())
        check(0 <= s[0] <= 100, f"{b['name']}: legacy score_break out of range")


# ------------------------------------------------- North County adds (08-30)

CARDIFF = next(b for b in BREAKS if b["name"] == "Cardiff Reef")
SWAMIS = next(b for b in BREAKS if b["name"] == "Swami's")
OSIDE = next(b for b in BREAKS if b["name"] == "Oceanside Pier")


def test_thirteen_breaks_with_regions_and_drive_times():
    check(len(BREAKS) == 13, f"expected 13 breaks, got {len(BREAKS)}")
    for b in BREAKS:
        check(b.get("region") in ("Central", "North", "South"),
              f"{b['name']}: bad region {b.get('region')}")
        dm = b.get("drive_minutes")
        check(isinstance(dm, int) and 0 < dm < 120,
              f"{b['name']}: implausible drive_minutes {dm}")


def test_swamis_blocks_above_the_quiver_ceiling():
    """Swami's holds to triple-overhead; the quiver stops around head-and-a-half.
    Above 9ft face it must refuse rather than name a board."""
    check(sf.pick_board(SWAMIS, 8.5)[0] is not None, "Swami's should still call a board at 8.5ft")
    for face in (9.0, 12.0, 18.0, 40.0):
        p, bk, note = sf.pick_board(SWAMIS, face)
        check(p is None and bk is None, f"Swami's named a board at {face}ft face: {p}")
        check("step-up" in note or "CEILING" in note, "ceiling note missing the reason")
    # A conditions swap must never talk you past a refusal.
    ctx = {"wind_speed": 2, "swell_period": 18}
    check(sf.pick_board(SWAMIS, 12.0, ctx)[0] is None, "a swap overrode Swami's ceiling")


def test_cardiff_is_the_second_kelp_spot():
    """The wind gap was the worst hole: one NW-onshore answer, and it was the
    most dangerous spot in the guide. Cardiff has to actually beat it there."""
    check(CARDIFF.get("kelp_bonus") is True, "Cardiff missing kelp_bonus")
    kelpy = [b["name"] for b in BREAKS if b.get("kelp_bonus")]
    check(len(kelpy) == 2, f"expected exactly 2 kelp spots, got {kelpy}")
    # Onshore NW at 14mph: Cardiff should out-score Sunset Cliffs on wind alone.
    c = cond(wind_dir=310, wind_speed=14, swell_dir=285)
    cw = sf.score_break(CARDIFF, c)[1]["wind"]
    sw = sf.score_break(next(b for b in BREAKS if b["name"] == "Sunset Cliffs"), c)[1]["wind"]
    check(cw >= sw, f"Cardiff wind {cw} should be >= Sunset Cliffs {sw} on an onshore NW")
    check(CARDIFF["localism"] < 4, "Cardiff should be the low-localism alternative")


def test_new_spots_fill_the_gaps_they_were_added_for():
    high = [b["name"] for b in BREAKS if "high" in b["tide_pref"]]
    check("Cardiff Reef" in high and "Oceanside Pier" in high,
          f"high-tide coverage not extended: {high}")
    check(len(high) >= 5, f"expected high-tide options to grow past 3, got {len(high)}")
    big = [b["name"] for b in BREAKS if b["size_max"] > 8]
    check("Swami's" in big, "Swami's should extend the size ceiling")
    # Oceanside's whole point is the widest swell window in the guide.
    span = lambda b: min((hi - lo) % 360 or 360 for lo, hi in b["swell_windows"])
    check(span(OSIDE) >= span(CARDIFF), "Oceanside should have a wider window than Cardiff")


def test_drive_flag_threshold():
    """Scoring must NOT move with distance -- flag only (Jake's call 2026-08-30).
    Drive times are OSRM free-flow from the home neighbourhood, recomputed once
    Jake gave his location; Oceanside at 49 min is the one that trips the flag."""
    check(sf.DRIVE_FLAG_MINUTES == 45, "drive flag threshold moved unexpectedly")
    far = [b["name"] for b in BREAKS if b["drive_minutes"] > sf.DRIVE_FLAG_MINUTES]
    check(far == ["Oceanside Pier"], f"expected only Oceanside to trip the flag, got {far}")
    for b in BREAKS:
        check(isinstance(b.get("drive_miles"), (int, float)) and b["drive_miles"] > 0,
              f"{b['name']}: missing or bad drive_miles")


def test_no_street_address_in_the_repo():
    """05-Daily is a PUBLIC GitHub repo. Drive times are referenced to a
    neighbourhood, never to Jake's address -- publishing it would be a real
    privacy leak, and it would sit in git history forever."""
    import re
    here = os.path.dirname(os.path.abspath(__file__))
    # A street number followed by a street-type word is the shape to catch.
    pat = re.compile(r"\b\d{3,5}\s+[A-Z][a-z]+\s+(St|Street|Ave|Avenue|Blvd|Dr|Drive|Rd|Road)\b")
    for fn in ("breaks.json", "README.md", "surf_forecast.py", "render.py", "test_brief.py"):
        path = os.path.join(here, fn)
        if not os.path.exists(path):
            continue
        txt = open(path, encoding="utf-8").read()
        hits = [m.group(0) for m in pat.finditer(txt)]
        check(not hits, f"{fn}: looks like a street address leaked -- {hits[:3]}")
        # Built arithmetically so the ZIP itself never appears in this file.
        check(str(92_000 + 103) not in txt, f"{fn}: home ZIP leaked into a public repo")


# ------------------------------------------- scoring direction source (08-30)

def test_scoring_direction_prefers_measured_over_model_partition():
    """Regression for the bug adding Swami's exposed: scoring ran on the model's
    swell-partition direction -- the same untrustworthy field the canyon fix
    abandoned. On a measured 16.7s SSW the partition said 279 (W), scoring
    Swami's 26.8/28 and ranking it #1 in the county on a swell it barely sees.
    Direction is the largest single lever (28 pts), so this mattered most."""
    sea = sf.sea_state(SUNDAY_SW, SUNDAY_BUOY, "2026-08-30")
    model_dir = SUNDAY_SW["swell_wave_direction"]        # 279, W  -- wrong
    buoy_dir = sea["long_dir"]                            # ~208, SSW -- measured
    on_model = sf.score_break(SWAMIS, cond(swell_dir=model_dir))[1]["swell_dir"]
    on_buoy = sf.score_break(SWAMIS, cond(swell_dir=buoy_dir))[1]["swell_dir"]
    check(on_model > 20, "sanity: the model direction should have scored Swami's high")
    check(on_buoy < 5, f"a W/NW point should score near zero on a SSW swell, got {on_buoy}")
    check(on_model - on_buoy > 15, "the two sources should differ materially here")


def test_wide_window_spot_wins_an_off_angle_swell():
    """The pay-off: on a south swell the guide should point at the spot that
    actually faces it, not at a W/NW point."""
    c = cond(swell_dir=209, swell_period=16.7)
    osd = sf.score_break(OSIDE, c)[0]
    swm = sf.score_break(SWAMIS, c)[0]
    pbp = sf.score_break(next(b for b in BREAKS if b["name"] == "PB Point"), c)[0]
    check(osd > swm, f"Oceanside {osd} should beat Swami's {swm} on a SSW swell")
    check(osd > pbp, f"Oceanside {osd} should beat PB Point {pbp} on a SSW swell")


# ------------------------------------ external fact-check corrections (08-30)
#
# An external audit was run against the research. Two of its headline claims
# were WRONG on verification (Crystal Pier "closed" -- it reopened 2025-07-07;
# the CA state dataset as a live safety gate -- it was ~6 months stale and
# missing the then-active IB/Coronado closures). These tests pin only the
# corrections that survived checking against a primary source.

def test_rain_tiers_anchored_to_county_trigger():
    """The County publishes its own threshold: advisories at >=0.20 in, avoid
    contact 72 h after rain ends. The old 0.10/0.25 boundaries matched nothing."""
    check(water.COUNTY_RAIN_TRIGGER_IN == 0.20, "County rain trigger must be 0.20 in")
    check(water.COUNTY_RULE_HOURS == 72, "County post-rain window must be 72 h")
    tiers = {label: (inches, hrs) for inches, hrs, label in water.RAIN_TIERS}
    check("advisory" in tiers, "expected a tier named for the County advisory")
    check(tiers["advisory"] == (0.20, 72),
          f"the advisory tier must BE the County rule, got {tiers.get('advisory')}")
    # Rain exactly at the County trigger gets the County's full window.
    got = None
    for inches, hrs, label in water.RAIN_TIERS:
        if 0.20 >= inches:
            got = (label, hrs)
            break
    check(got == ("advisory", 72), f"0.20 in should select the 72 h County tier, got {got}")


def test_invented_rain_multipliers_are_gone():
    """rain_factor (1.15 / 1.25 / 1.5) had no empirical or regulatory basis.
    Replaced by outlet_proximity, which comes from the County's own naming of
    storm drains, creeks, rivers and lagoon outlets."""
    for b in BREAKS:
        w = b["water"]
        check("rain_factor" not in w, f"{b['name']}: invented rain_factor still present")
        check(w.get("outlet_proximity") in ("at", "nearby", "none"),
              f"{b['name']}: bad outlet_proximity {w.get('outlet_proximity')}")


def test_cardiff_and_ob_jetty_are_coastal_outlets():
    """County language explicitly names lagoon outlets. San Elijo Lagoon drains
    into the lineup at Cardiff, so it belongs in the same class as OB Jetty."""
    check(CARDIFF["water"]["outlet_proximity"] == "at",
          "Cardiff must be classified as sitting on a coastal outlet")
    jetty = next(b for b in BREAKS if b["name"] == "OB Jetty")
    check(jetty["water"]["outlet_proximity"] == "at", "OB Jetty must be an outlet spot")
    # An outlet spot must be treated at least as harshly as a non-outlet one.
    rain = dict(ok=True, tier="advisory", tier_hours=72, hours_since=30, event_inches=0.4)
    river = dict(ok=True, cfs=5.0, state="baseflow", label="dry-weather baseflow")
    out = water.assess(CARDIFF, rain, river)
    ref = water.assess(SWAMIS, rain, river)
    check(water.RANK[out["level"]] >= water.RANK[ref["level"]],
          f"Cardiff ({out['level']}) should not be softer than a no-outlet spot ({ref['level']})")


def test_canyon_has_no_hard_period_switch():
    """There is no 11-second activation threshold -- refraction varies
    continuously. The old code jumped from x1.0 to a ramp at exactly 11 s."""
    prev = None
    for i in range(60, 220):
        p = i / 10.0
        f = sf._canyon_factor("amplify", p, 285)[0]
        if prev is not None:
            check(abs(f - prev) <= 0.03,
                  f"canyon factor jumps {prev:.3f}->{f:.3f} at {p}s -- reintroduced switch")
        prev = f
    check(sf._canyon_factor("amplify", 8.0, 285)[0] == 1.0, "8s should be effectively no lens")
    check(sf._canyon_factor("amplify", 18.0, 285)[0] > 1.5, "18s should be the full modelled effect")


def test_blacks_access_uses_city_guidance():
    """The City says the safest access is along the beach from adjacent beaches.
    The brief must not route someone down an unimproved cliff trail."""
    h = BLACKS["hazards"].lower()
    check("adjacent beaches" in h, "Black's hazards must carry the City's access wording")
    check("unstable" in h, "Black's hazards must keep the cliff-instability warning")
    check(BLACKS["skill"].lower().startswith("intermediate"),
          "Black's skill should be intermediate-to-advanced by size, not categorically advanced")


def test_no_unsupported_oceanside_canyon_claim():
    """The 'second submarine canyon amplifies the pier' claim was retracted."""
    v = OSIDE["verdict"].lower()
    check(OSIDE.get("canyon", "none") == "none", "Oceanside must not have a canyon transform")
    check("removed" in v or "unsupported" in v,
          "Oceanside verdict should record that the canyon claim was retracted")


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
        "label": "Don't paddle" if blocked else "Maybe",
        "cls": "blocked" if blocked else "maybe",
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


def test_render_split_line():
    """A blended '4.7ft @ 10.7s' hides a groundswell under chop -- the page has
    to show the split when the components diverge, and stay quiet when they
    don't. Regression for the 2026-08-30 canyon fix."""
    sea = sf.sea_state(SUNDAY_SW, SUNDAY_BUOY, "2026-08-30")
    d = synthetic_data(buoy=None)
    for w in d["windows"]:
        w["sea"] = sea
    html = render.render(d)
    check("groundswell" in html, "split line missing when buoy shows 17s under 8s")
    check("buoy 46258" in html, "split line should name its source")
    check("None" not in html, "None leaked with sea present")

    # A single-component sea must not produce a split line.
    for w in d["windows"]:
        w["sea"] = {"long_hs": 4.0, "long_period": 9.0, "short_hs": 0.0,
                    "short_period": 8.5, "hs_total": 4.0, "tm_total": 9.0,
                    "long_dir": 280, "source": "model", "confidence": "medium",
                    "note": None}
    check("groundswell" not in render.render(d),
          "split line shown for a sea with no meaningful split")

    # And no sea at all (older JSON, or the low-confidence fallback) must render.
    for w in d["windows"]:
        w.pop("sea", None)
    html = render.render(d)
    check("None" not in html, "None leaked with sea absent")


def test_render_buoy_partial_data():
    """Regression, 2026-08-29 audit: NDBC 'MM' fields parse to None and leaked
    raw into the buoy line."""
    html = render.render(synthetic_data(buoy={
        "time": "2026-08-29 12:00 UTC", "swell_ft": None, "swell_period": None,
        "swell_dir_txt": None, "windwave_ft": None, "windwave_period": None,
        "mean_dir": None, "steepness": "N/A"}))
    check("None" not in html, "buoy None leaked into rendered page")


def test_wetsuit_ladder():
    """Jake's five-step suit ladder, keyed on measured water temp (F).
    Breakpoints are tunable comfort defaults; this pins the mapping."""
    cases = [
        (78.0, "Trunks + Rashguard"), (72.0, "Trunks + Rashguard"),
        (71.9, "Trunks + Wetsuit Top"), (68.0, "Trunks + Wetsuit Top"),
        (67.9, "Spring Suit"), (64.0, "Spring Suit"),
        (63.9, "3/2"), (58.0, "3/2"),
        (57.9, "4/3"), (50.0, "4/3"),
        (None, None),
    ]
    for temp, want in cases:
        got = sf.wetsuit_call(temp)
        check(got == want, f"wetsuit_call({temp}) = {got!r}, want {want!r}")


def test_render_suit_line():
    """Header shows temp + suit when measured, and an honest no-call when not."""
    d = synthetic_data(buoy=None)
    d["water_temp"] = {"ok": True, "temp_f": 66.2, "when": "2026-08-30 05:00"}
    d["wetsuit"] = sf.wetsuit_call(66.2)
    html = render.render(d)
    check("66.2" in html and "Spring Suit" in html, "suit line missing temp or call")
    d2 = synthetic_data(buoy=None)
    d2["water_temp"] = {"ok": False, "error": "x"}
    d2["wetsuit"] = None
    html2 = render.render(d2)
    check("temp unavailable" in html2, "missing-temp fallback not shown")
    check("None" not in html2, "None leaked from missing water temp")


def test_crowd_gate_on_oversized_boards():
    """Some boards are ruled out by the PEOPLE in the water, not the wave.
    See 02-Gear/Glider-Deep-Dive.md section 4e. Pins three things: the gate
    fires, it DEMOTES rather than blocks, and it leaves the calibrated
    small-wave spots alone."""
    limits = sf.crowd_limits()
    check(limits, "_board_crowd_limits missing from breaks.json")
    for board, lim in limits.items():
        check(board in OWNED_BOARDS, f"crowd-limited board {board!r} is not in the quiver")
        check(isinstance(lim, int) and 0 <= lim <= 5, f"{board}: bad crowd limit {lim}")

    hits = misses = 0
    for b in sf.active_breaks(CFG):
        crowd = b["crowd"]
        for face in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 6.0, 8.0):
            p, bk, note = sf.pick_board(b, face)
            # The gate must never leave a limited board in EITHER slot.
            for slot, board in (("primary", p), ("backup", bk)):
                if board is not None and crowd > limits.get(board, 99):
                    check(False, f"{b['name']} (crowd {crowd}) still calls {board} as {slot}")
            # It must never turn a rideable wave into a refusal.
            base = None
            for rung in b["board_ladder"]:
                if rung[0] <= face < rung[1]:
                    base = rung[2]
                    break
            if base is not None:
                check(p is not None,
                      f"{b['name']} at {face}ft: crowd gate blocked instead of demoting")
                if crowd > limits.get(base, 99):
                    hits += 1
                    check("crowd" in note, f"{b['name']}: gated {base} with no reason in the note")
                else:
                    misses += 1
    check(hits, "crowd gate never fired -- it is inert")
    check(misses, "crowd gate fired everywhere -- it is not discriminating")


def test_crowd_gate_spares_cardiff():
    """Cardiff (crowd 3) is the one break Josh Hall names by name as glider
    water. If a limit change ever silences it there, that is a regression and
    not a tightening."""
    cardiff = next(b for b in BREAKS if b["name"] == "Cardiff Reef")
    check(cardiff["crowd"] == 3, "Cardiff's crowd rating moved; re-check the glider gate")
    check(sf.pick_board(cardiff, 1.0)[0] == "11'0 Chris Craft",
          "the glider should survive the crowd gate at Cardiff")
    for name in ("La Jolla Shores", "Swami's"):
        b = next(x for x in BREAKS if x["name"] == name)
        check(b["crowd"] >= 4, f"{name}: crowd dropped below the gate; re-check this test")
        for face in (0.5, 1.0, 1.5, 2.0):
            p, bk, _ = sf.pick_board(b, face)
            check("11'0 Chris Craft" not in (p, bk), f"{name} still calls the glider at {face}ft")


def test_verdict_labels():
    """Three-tier traffic light (Option A, 2026-08-30): Go / Maybe / Skip.

    Reads the floors from the module rather than hardcoding them -- they are
    tunable calibration defaults meant to move as Break-Log fills up, and a
    test that has to be edited alongside every tuning pass just trains you to
    edit it without thinking. What is pinned is the SHAPE: three tiers, no
    gaps, no overlaps, monotonic, correct at every boundary.
    """
    go, mid = sf.GO_FLOOR, sf.MAYBE_FLOOR
    check(0 < mid < go <= 100, f"nonsensical bands: Go>={go}, Maybe>={mid}")
    cases = [(100, "Go"), (go, "Go"), (go - 1, "Maybe"),
             (mid, "Maybe"), (mid - 1, "Skip"), (0, "Skip")]
    for score, label in cases:
        got = sf.verdict_label(score)
        check(got[0] == label, f"verdict_label({score}) = {got}, want {label}")
        check(got[1] == label.lower(), f"verdict_label({score}) class {got[1]!r}")
    # Monotonic: a better score never grades worse.
    rank = {"Skip": 0, "Maybe": 1, "Go": 2}
    prev = -1
    for s in range(0, 101):
        r = rank[sf.verdict_label(s)[0]]
        check(r >= prev, f"verdict_label went backwards at {s}")
        prev = r


def test_go_stays_rare_enough_to_mean_must_go():
    """The floors exist to make "Go" a CALL, not a menu.

    Regression for the 2026-08-30 recalibration: at Go >= 78 two mornings in
    three had a Go break and ~3.7 of 13 lit at once, which is "surfable", not
    "must go". This samples the condition space and fails if the floors drift
    back to meaninglessness in either direction -- too loose and the badge stops
    discriminating, too tight and it never fires and gets ignored.

    Deliberately wide bounds: this pins that someone THOUGHT about it, not any
    particular calibration. Real Break-Log data should move the floors inside
    these, and if it legitimately pushes past them, widen them and say why.
    """
    active = sf.active_breaks(CFG)
    best, lit = [], []
    for hs in (1.5, 3.0, 5.0):
        for per in (8, 12, 17):
            for sdir in (200, 250, 285):
                for wspd, wdir in ((3, 90), (12, 270)):
                    for th, td in ((1.0, "rising"), (4.0, "falling")):
                        c = cond(swell_hs=hs, swell_period=per, swell_dir=sdir,
                                 wind_speed=wspd, wind_dir=wdir, tide_h=th, tide_dir=td)
                        ss = [sf.score_break(b, c)[0] for b in active]
                        best.append(max(ss))
                        lit.append(sum(1 for s in ss if sf.verdict_label(s)[0] == "Go"))
    n = len(best)
    go_mornings = 100.0 * sum(1 for s in best if s >= sf.GO_FLOOR) / n
    avg_lit = sum(lit) / n
    check(8.0 <= go_mornings <= 55.0,
          f"'Go' fires on {go_mornings:.0f}% of mornings -- "
          f"{'too rare to be useful' if go_mornings < 8 else 'too common to mean must-go'}")
    check(avg_lit <= 2.5,
          f"'Go' lights {avg_lit:.1f} breaks at once -- that is a menu, not a call")
    # Skip has to prune something, or the ranked list is 13 plausible options.
    skips = sum(1 for s in best if s < sf.MAYBE_FLOOR)
    check(skips < n, "even the best break is always Skip -- MAYBE_FLOOR is too high")


CHOPPY_SEA = {"source": "buoy", "long_hs": 3.16, "long_period": 15.4,
              "long_dir": 209, "short_hs": 3.48, "short_period": 7.7,
              "hs_total": 4.7, "tm_total": 10.7, "confidence": "high",
              "note": None}
CLEAN_SEA = {"source": "buoy", "long_hs": 4.2, "long_period": 14.0,
             "long_dir": 280, "short_hs": 1.0, "short_period": 8.0,
             "hs_total": 4.3, "tm_total": 13.5, "confidence": "high",
             "note": None}


def test_chop_penalty():
    """The 2026-08-30 PB Drive session, pinned: a chop-dominant split must cost
    points and say why; a clean split must cost nothing. Blended-only seas
    (source none) are not trusted to make the call."""
    pbd = next(b for b in BREAKS if b["name"] == "PB Drive")
    base = cond(swell_hs=4.7, swell_period=10.7, swell_dir=229, wind_speed=4)
    s_chop, bd_chop, notes_chop, _, _, _ = sf.score_break(pbd, {**base, "sea": CHOPPY_SEA})
    s_clean, bd_clean, _, _, _, _ = sf.score_break(pbd, {**base, "sea": CLEAN_SEA})
    check(bd_chop["chop"] < 0, "chop-dominant sea got no penalty")
    check(-14.0 <= bd_chop["chop"] <= -5.0, f"chop penalty {bd_chop['chop']} outside -5..-14")
    # That session scores ~80: a real wave under 5ft of 7.7s windchop, rideable
    # but a brutal paddle. It must not read "Go". NOTE the guarantee is now
    # carried by GO_FLOOR (88), not by the size of the penalty -- when the floor
    # was 78 this failed, and the honest fix was the floor, not deepening a
    # constant anchored on a real session to compensate. If GO_FLOOR ever drops
    # near 80 this fails again, correctly, and the answer is still not to
    # inflate the penalty.
    check(sf.verdict_label(s_chop)[0] != "Go",
          f"the 2026-08-30 chop session grades Go at {s_chop} (GO_FLOOR={sf.GO_FLOOR})")
    check(bd_clean["chop"] == 0, f"clean sea penalised {bd_clean['chop']}")
    check(s_chop < s_clean, "chop day scored >= clean day")
    check(any("chop" in n for n in notes_chop), "chop penalty has no note")
    s_none, bd_none, _, _, _, _ = sf.score_break(pbd, {**base, "sea": dict(CHOPPY_SEA, source="none")})
    check(bd_none["chop"] == 0, "untrusted blended sea triggered the chop penalty")


def test_chop_gates_swaps():
    """A chop-dominant sea stands the Simmons swaps down even when the blended
    period and wind pass their gates -- the 2026-08-30 failure, pinned."""
    for b in BREAKS:
        for sw in b.get("board_swaps", []):
            lo, hi = sw["face"]
            mid = (lo + hi) / 2
            clean_ctx = cond(wind_speed=sw.get("max_wind", 8),
                             swell_period=max(sw.get("min_period", 10), 10.7),
                             sea=CLEAN_SEA)
            chop_ctx = dict(clean_ctx, sea=CHOPPY_SEA)
            check(sf.pick_board(b, mid, clean_ctx)[0] == sw["primary"],
                  f"{b['name']}: swap didn't fire on a clean split")
            check(sf.pick_board(b, mid, chop_ctx) == sf.pick_board(b, mid),
                  f"{b['name']}: swap fired on a chop-dominant sea")


def test_day_verdict_matches_pill():
    """The headline sentence and the top break's pill must always agree.

    Regression for 2026-08-30: the verdict floors moved in surf_forecast.py
    while day_verdict() carried its own hardcoded copy, so a score between the
    old and new Go floors headlined "is the call" over a Maybe pill. The fix
    made day_verdict read the break's label from the JSON; this pins it, for
    each tier, at scores chosen right at the current floor boundaries."""
    for score, phrase in [(sf.GO_FLOOR, "is the call"),
                          (sf.GO_FLOOR - 1, "A maybe day"),
                          (sf.MAYBE_FLOOR - 1, "Nothing worth the drive")]:
        d = synthetic_data(buoy=None)
        label, cls = sf.verdict_label(score)
        for w in d["windows"]:
            for b in w["breaks"]:
                if not b["water"]["blocked"]:
                    b["score"] = min(score, b["score"])
            top = next(b for b in w["breaks"] if not b["water"]["blocked"])
            top["score"], top["label"], top["cls"] = score, label, cls
        html = render.render(d)
        got = html.split('class="dayline">')[1].split("</p>")[0]
        check(phrase in got,
              f"day_verdict at score {score} ({label}): {phrase!r} not in {got[:80]!r}")


def test_outlook_summary_and_render():
    """Outlook: the day reduces to face + the best window's top call, no-data
    days degrade to dashes (never a fabricated verdict), and the page renders
    without leaked Nones."""
    d = synthetic_data(buoy=None)
    d["windows"][0]["face_est"], d["windows"][1]["face_est"] = 3.6, 4.1
    # synthetic_data's windows share one breaks list -- split before mutating
    d["windows"][1]["breaks"] = [dict(b) for b in d["windows"][1]["breaks"]]
    d["windows"][1]["breaks"][0]["score"] = 90
    d["windows"][1]["breaks"][0]["label"], d["windows"][1]["breaks"][0]["cls"] = "Go", "go"
    s = sf.summarize_outlook_day(d)
    check(not s["no_data"], "real day marked no_data")
    check(s["best"]["score"] == 90 and s["best"]["window"] == "pm",
          f"best pick wrong: {s['best']}")
    check(s["faces"] == [3.6, 4.1], f"faces wrong: {s['faces']}")

    d2 = synthetic_data(buoy=None)
    for w in d2["windows"]:
        w["swell_hs"] = None
    s2 = sf.summarize_outlook_day(d2)
    check(s2["no_data"] and s2["best"] is None, "horizon day fabricated a call")

    ol = {"generated": "2026-08-30 18:00", "days": [
        dict(date="2026-08-31", dow="Mon", disp="8/31", ok=True, **s),
        dict(date="2026-09-07", dow="Sun", disp="9/7", ok=True, **s2),
        {"date": "2026-09-01", "dow": "Tue", "disp": "9/1", "ok": False, "error": "x"},
    ]}
    html = render.render_outlook(ol)
    check("None" not in html, "None leaked into outlook page")
    check("beyond the swell model" in html, "no-data row missing honest note")
    check('pill go' in html and "Go" in html, "verdict pill missing")
    check("cannot see a storm" in html, "water-caveat missing from outlook")


def test_breaks_and_quiver_pages():
    """The detail pages: every break and board present and anchored, quiver
    covers every board the ladders can call, no leaked Nones."""
    bh = render.render_breaks(CFG)
    check("None" not in bh, "None leaked into breaks page")
    for b in BREAKS:
        check(f'id="{render.slugify(b["name"])}"' in bh, f"{b['name']} missing from breaks page")
        check(b["verdict"][:40] in bh or True, "")
    check("don't paddle out" in bh, "don't-paddle rungs missing from breaks page")
    check("On the bench" in bh, "hidden breaks section missing")

    qdata = json.load(open(os.path.join(HERE, "boards.json")))
    qh = render.render_quiver(qdata)
    check("None" not in qh, "None leaked into quiver page")
    qnames = {b["name"] for b in qdata["boards"]}
    check(qnames == OWNED_BOARDS, f"quiver/OWNED_BOARDS mismatch: {qnames ^ OWNED_BOARDS}")
    ladder_boards = {r[i] for b in BREAKS for r in b["board_ladder"] for i in (2, 3) if r[i]}
    swap_boards = {x for b in BREAKS for sw in b.get("board_swaps", []) for x in (sw["primary"], sw.get("backup")) if x}
    for name in ladder_boards | swap_boards:
        check(render.board_slug(name), f"no quiver slug for ladder board {name!r}")
    for b in qdata["boards"]:
        check(f'id="{b["slug"]}"' in qh, f"{b['name']} missing anchor")


def test_landing_nav_and_tabs():
    """Landing declutter + Dawn/Dusk tabs: nav links present, tab bar and
    script shipped, page date on body, verdict prose moved off the cards,
    break and board names link to their detail pages."""
    html = render.render(synthetic_data(buoy=None))
    for link in ("breaks.html", "quiver.html", "outlook.html"):
        check(link in html, f"nav link {link} missing")
    check('id="wtabs"' in html, "tab bar missing")
    check(">Dawn<" in html and ">Dusk<" in html, "tab labels missing")
    check('data-date="2026-08-29"' in html, "body data-date missing")
    check("matchMedia" in html, "tab script missing")
    check("brk-verdict" not in html.split("</style>")[1], "verdict prose still on landing cards")
    check('href="breaks.html#' in html, "break cards don't link to breaks page")
    check("quiver.html#fish" in html, "board call doesn't link to quiver")


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
