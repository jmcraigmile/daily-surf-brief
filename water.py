#!/usr/bin/env python3
"""
Bacterial / water-quality risk for the San Diego daily surf brief.

WHAT THIS IS NOT: it does not read live County of San Diego beach advisories.
sdbeachinfo.com is an OutSystems app with no stable endpoint, and Heal the Bay
and EPA BEACON are dead ends. California DOES publish a machine-readable beach
postings/closures dataset (CKAN, data.ca.gov) -- but checked 2026-08-30 its
newest record was 2026-03-06, ~6 months stale, with NO record of the Imperial
Beach or Coronado closures active that week. It is a historical archive, not a
live safety gate. So this INFERS risk from two signals that ARE current, both
machine-readable:

  1. Rainfall history (Open-Meteo, hourly, past 5 days) -- urban runoff after
     rain is the dominant bacterial driver, and the county's own guidance is a
     72-hour rule.
  2. San Diego River discharge (USGS gauge 11023000, San Diego River at Fashion
     Valley) -- the folder is explicit that OB is "toxic if the San Diego River
     is flowing." Live 15-minute data.

sdbeachinfo.com / 619-338-2073 remains the authoritative check and the brief
says so every day.

Rain windows are anchored to the County's OWN published trigger (>=0.20 in ->
72 h). Below that threshold a shorter 24 h window applies, which is more
permissive than a blanket reading of the advice; the output always states the
County rule alongside, so an inside-the-official-window call stays visible.
"""

import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

RIVER_GAUGE = "11023000"  # San Diego River at Fashion Valley

# Discharge thresholds, calibrated 2026-08-27 against 12 months of daily means
# at this gauge: p50 3.7 / p75 14.6 / p90 30.8 / p95 88 / p98 205 / max 1740 cfs.
RIVER_BASEFLOW = 8.0    # below this the river is not meaningfully flowing
RIVER_ELEVATED = 30.0   # ~p90
RIVER_FLOWING = 150.0   # ~p97 -- OB is in the plume
RIVER_HIGH = 400.0      # ~p99 -- storm discharge

# Rain tiers: (inches, base wait hours, label)
#
# Recalibrated 2026-08-30 to the County's ACTUAL published trigger, after an
# external fact-check. Verified against the County's own advisory explanation
# (DEHQ_bb_advisory_explanation.pdf):
#
#   "General (rain) advisories are issued when rainfall equal to or greater than
#    0.20 inch is received in coastal or valley areas of San Diego County...
#    avoid contact with ocean and bay water for a period of 72 hours after
#    rainfall ends."
#
# The old boundaries (0.10 / 0.25) were invented and matched nothing. 0.20 in is
# now the line at which the County itself issues an advisory, so it is the line
# where this brief goes to the full 72 hours.
COUNTY_RAIN_TRIGGER_IN = 0.20   # County's published advisory threshold
COUNTY_RULE_HOURS = 72          # County's published post-rain wait

RAIN_TIERS = [
    (1.00, 96, "heavy"),        # well past the trigger -- longer runoff tail
    (0.20, 72, "advisory"),     # AT the County trigger: their rule, exactly
    (0.05, 24, "sub-advisory"), # measurable but under the County threshold
]


def _fetch_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "sd-surf-brief/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def get_rain(lat=32.78, lon=-117.25, now=None):
    """Recent rainfall: total, when it stopped, and how long ago.

    Sampled at one coastal point -- the county is small enough that a storm hits
    the whole coastal strip, and runoff comes from inland watersheds anyway.
    """
    url = ("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "hourly": "precipitation", "precipitation_unit": "inch",
        "past_days": 5, "forecast_days": 1,
        "timezone": "America/Los_Angeles",
    }))
    try:
        h = _fetch_json(url)["hourly"]
    except Exception as e:
        return {"ok": False, "error": str(e)}

    now = now or datetime.now()
    rows = []
    for t, p in zip(h["time"], h["precipitation"]):
        dt = datetime.strptime(t, "%Y-%m-%dT%H:%M")
        if dt <= now and p is not None:
            rows.append((dt, p))

    total_96 = sum(p for dt, p in rows if (now - dt).total_seconds() <= 96 * 3600)
    wet = [(dt, p) for dt, p in rows if p >= 0.01]
    if not wet:
        return {"ok": True, "total_96h": round(total_96, 2), "event_inches": 0.0,
                "last_rain": None, "hours_since": None, "tier": None, "tier_hours": 0}

    last_dt = max(dt for dt, _ in wet)
    hours_since = (now - last_dt).total_seconds() / 3600.0

    # Size the event by rain falling in the 48h before it stopped -- a storm's
    # own total, not a month of drizzle.
    event = sum(p for dt, p in wet if 0 <= (last_dt - dt).total_seconds() <= 48 * 3600)
    tier, tier_hours = None, 0
    for inches, hrs, label in RAIN_TIERS:
        if event >= inches:
            tier, tier_hours = label, hrs
            break

    return {"ok": True, "total_96h": round(total_96, 2),
            "event_inches": round(event, 2),
            "last_rain": last_dt.strftime("%Y-%m-%d %H:%M"),
            "hours_since": round(hours_since, 1),
            "tier": tier, "tier_hours": tier_hours}


def get_river():
    """Latest San Diego River discharge in cfs, plus a plain-language state."""
    url = ("https://waterservices.usgs.gov/nwis/iv/?" + urllib.parse.urlencode({
        "sites": RIVER_GAUGE, "parameterCd": "00060",
        "period": "P1D", "format": "json",
    }))
    try:
        ts = _fetch_json(url)["value"]["timeSeries"]
        if not ts:
            return {"ok": False, "error": "no timeseries"}
        vals = [v for v in ts[0]["values"][0]["value"] if v["value"] not in ("", "-999999")]
        if not vals:
            return {"ok": False, "error": "no values"}
        cfs = float(vals[-1]["value"])
        when = vals[-1]["dateTime"][:16].replace("T", " ")
    except Exception as e:
        return {"ok": False, "error": str(e)}

    if cfs >= RIVER_HIGH:
        state, label = "high", "running hard"
    elif cfs >= RIVER_FLOWING:
        state, label = "flowing", "flowing"
    elif cfs >= RIVER_ELEVATED:
        state, label = "elevated", "up on baseflow"
    else:
        state, label = "baseflow", "dry-weather baseflow"
    return {"ok": True, "cfs": round(cfs, 1), "when": when, "state": state, "label": label}


# ------------------------------------------------------------------ per break

RANK = {"clear": 0, "caution": 1, "avoid": 2, "severe": 3}


def assess(brk, rain, river):
    """Water risk for one break. Returns level, headline, reasons, blocked."""
    w = brk.get("water") or {}
    chronic = w.get("chronic", "normal")
    river_mouth = w.get("river_mouth", False)

    # OUTLET PROXIMITY replaces the old invented rain_factor multipliers
    # (1.15 / 1.25 / 1.5), which an external fact-check correctly flagged as
    # having no empirical or regulatory basis. This version comes straight from
    # the County's published advisory language, which singles out exactly this:
    #
    #   "...especially those located adjacent to storm drains, creeks, rivers,
    #    and lagoon outlets."
    #
    # "at"     = the break sits on the outlet (OB Jetty at the river mouth,
    #            Cardiff at the San Elijo Lagoon mouth)
    # "nearby" = a named outlet within roughly a mile
    # "none"   = no named outlet
    outlet = w.get("outlet_proximity", "none")
    factor = {"at": 1.5, "nearby": 1.2, "none": 1.0}.get(outlet, 1.0)

    level = "clear"
    reasons = []

    def raise_to(lv, why):
        nonlocal level
        if RANK[lv] > RANK[level]:
            level = lv
        reasons.append(why)

    # --- rain
    #
    # Severity is deliberately spot-dependent. Blanket-blocking all ten breaks
    # for four days after every winter storm would be MORE conservative than the
    # county's flat 72h rule, and would black out the brief for most of the good
    # season. So a block is reserved for genuinely acute cases:
    #   - the acute runoff pulse in the first 24h of real rain, anywhere
    #   - any measurable rain at a river-mouth or chronically-bad spot
    # Everything else inside the window is "avoid": flagged loudly, but it keeps
    # its rank and Jake makes the call.
    if rain.get("ok") and rain.get("tier"):
        hrs, since = rain["tier_hours"] * factor, rain["hours_since"]
        inches, tier = rain.get("event_inches", 0), rain["tier"]
        # Aligned to the County's own 0.20 in trigger rather than an invented 0.25.
        acute = since <= 24 and inches >= COUNTY_RAIN_TRIGGER_IN
        dirty = river_mouth or outlet == "at" or chronic == "high"

        if since <= hrs:
            left = int(hrs - since)
            if acute:
                raise_to("severe", f"{inches}\" of rain only {int(since)}h ago -- this is "
                                   f"the acute runoff pulse, the worst of it")
            elif dirty:
                raise_to("severe", f"{inches}\" of rain {int(since)}h ago, and this spot sits "
                                   f"where the runoff comes out ({left}h left in the "
                                   f"{int(hrs)}h window)")
            else:
                raise_to("avoid", f"{inches}\" of rain {int(since)}h ago -- inside the "
                                  f"{int(hrs)}h runoff window, {left}h to go")
        elif since <= hrs * 1.5:
            lv = "avoid" if dirty else "caution"
            raise_to(lv, f"{inches}\" of rain {int(since)}h ago -- just past the "
                         f"{int(hrs)}h window, and bacteria lag the rain")

        if since <= COUNTY_RULE_HOURS and level not in ("severe",):
            reasons.append(f"Still inside the County's 72-hour post-rain advisory "
                           f"({int(since)}h since rain; County triggers at "
                           f"{COUNTY_RAIN_TRIGGER_IN}\" of rain)")

    # --- river (only meaningful for the spots in its plume)
    if river.get("ok") and river_mouth:
        st, cfs = river["state"], river["cfs"]
        if st == "high":
            raise_to("severe", f"San Diego River running hard at {cfs} cfs -- "
                               f"the folder's word for this is 'toxic'")
        elif st == "flowing":
            raise_to("severe", f"San Diego River flowing at {cfs} cfs -- "
                               f"you are in the plume")
        elif st == "elevated":
            raise_to("avoid", f"San Diego River up on baseflow at {cfs} cfs")

    # --- chronic baseline, independent of weather
    if chronic == "high":
        raise_to("caution", "Chronically the worst water of the ten, storm or no storm")
    elif chronic == "elevated" and level == "clear":
        raise_to("caution", "Chronic source nearby even in dry weather")

    headline = {
        "clear": "Water looks fine",
        "caution": "Check before you paddle",
        "avoid": "Bad water — pick somewhere else",
        "severe": "Do not paddle out here",
    }[level]

    return {
        "level": level, "headline": headline, "reasons": reasons,
        "blocked": level == "severe",
        "note": w.get("note", ""), "chronic": chronic,
    }


def day_summary(rain, river, results):
    """One line for the top of the brief, plus the worst level anywhere."""
    worst = "clear"
    for lv in (b["water"]["level"] for w in results for b in w["breaks"]):
        if RANK[lv] > RANK[worst]:
            worst = lv
    blocked = sorted({b["name"] for w in results for b in w["breaks"]
                      if b["water"]["blocked"]})

    if worst == "clear":
        line = "No rain in the window and the river is at baseflow. Water looks normal."
    elif blocked:
        line = (f"{', '.join(blocked)} blocked on water quality. "
                f"Everything else carries the usual caveats.")
    elif worst == "avoid":
        line = "Elevated bacterial risk at some spots — read the flags before you go."
    else:
        line = "Nothing acute, but the chronic spots are still the chronic spots."
    return {"worst": worst, "line": line, "blocked": blocked}


if __name__ == "__main__":
    r, v = get_rain(), get_river()
    print(json.dumps({"rain": r, "river": v}, indent=2))
