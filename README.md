# Daily Surf Brief

Scores the ten written-up San Diego breaks against live swell, tide, wind and
bacterial risk, twice a day, and names a board from Jake's actual quiver.

**Two windows:** dawn patrol 7:00–8:30am, and the hour before sunset (recalculated
daily, so it tracks the season).

> **Ported from Claude Cowork 2026-08-27; scheduling re-wired 2026-08-29.**
> Production is now GitHub Actions + GitHub Pages
> ([jmcraigmile/daily-surf-brief](https://github.com/jmcraigmile/daily-surf-brief)):
> two scheduled runs a day publish to one stable URL for phone access. The
> evening run builds **tomorrow's** brief, the morning run builds today's. See
> [Scheduling and publishing](#scheduling-and-publishing).

---

## Quick start

No dependencies. Python 3.8+ (developed on 3.10), standard library only.

```bash
cd 05-Daily
python3 surf_forecast.py --json brief.json     # fetch + score  (~5s, 6 HTTP calls)
python3 render.py brief.json brief.html        # render
```

Both scripts are cwd-independent — `surf_forecast.py` resolves `breaks.json`
relative to its own file, and `render.py` takes explicit paths. Run them from
anywhere with absolute paths.

```bash
python3 surf_forecast.py --date 2026-09-03 --json future.json   # any day within ~7
python3 water.py                                                # water signals only
```

---

## Files

| File | Role |
|---|---|
| `surf_forecast.py` | Fetches conditions, scores all ten breaks for both windows, picks boards. Writes JSON. |
| `water.py` | Bacterial risk per break from rainfall + river discharge. Imported by `surf_forecast.py`; also runnable standalone. |
| `render.py` | JSON → self-contained HTML. No network, no assets, no external CSS. |
| `breaks.json` | **The knob.** All per-break scoring rules and board ladders. Edit this, not the Python. |
| `test_brief.py` | No-network invariant suite: ladders, board names, direction monotonicity, component maxima, water-veto sims, render regressions. Gates every CI publish. |
| `.github/workflows/publish.yml` | The scheduler + publisher: four UTC crons (two per window, covering DST), tests → fetch → render → deploy to Pages. |

`__pycache__/` is generated — gitignore it.

**Ground truth lives outside this folder.** `breaks.json` is a machine-readable
derivative of:

- `../01-San-Diego-Breaks/Central-SD.md` and `South-County.md` — swell windows,
  tides, wind, crowds, hazards, water quality
- `../02-Gear/Owned-and-Wishlist.md` — the nine boards and their wave ranges
- `../CLAUDE.md` — the quiver's one-line summary and the "nothing built for
  overhead" constraint that drives the gap flag

**When a write-up changes, update `breaks.json` to match.** The brief is only ever
as good as that file, and nothing enforces the link automatically.

---

## Scheduling and publishing

**Production (2026-08-29):** GitHub Actions on the
[daily-surf-brief](https://github.com/jmcraigmile/daily-surf-brief) repo, publishing
to GitHub Pages. `.github/workflows/publish.yml` is the whole thing:

- **Four UTC crons** — ~4:45am Pacific ("day of") and ~8:00pm Pacific ("night
  before"), each scheduled at both PDT and PST offsets so DST never shifts the
  local time. The duplicate run is a harmless rebuild.
- **The evening run builds tomorrow** (`--date`), the morning run builds today —
  so the one URL always shows the next session that matters.
- **`test_brief.py` gates every publish**, plus a grep for leaked `None` on the
  rendered page.
- **Failure is loud, not clever.** If Open-Meteo or NOAA is down after one retry,
  the run fails, GitHub emails, and yesterday's page stays up — the generated-at
  line in the page header is the staleness signal. Check it before trusting a
  pre-dawn read.

The repo root is this folder. Phone access: open the Pages URL, Add to Home Screen.

### Local alternatives (dev only, not the production path)

The scripts are environment-agnostic — plain HTTPS and file writes — so the old
recipes still work if you ever want a machine-local copy:

### cron

```cron
45 5 * * * cd /path/to/Surfing/05-Daily && /usr/bin/python3 surf_forecast.py --json /tmp/surf.json && /usr/bin/python3 render.py /tmp/surf.json ~/surf-brief.html
```

### launchd (macOS — survives sleep, unlike cron)

`~/Library/LaunchAgents/com.jake.surfbrief.plist`, then
`launchctl load ~/Library/LaunchAgents/com.jake.surfbrief.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.jake.surfbrief</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string><string>-lc</string>
    <string>cd /path/to/Surfing/05-Daily &amp;&amp; python3 surf_forecast.py --json /tmp/surf.json &amp;&amp; python3 render.py /tmp/surf.json ~/surf-brief.html &amp;&amp; open ~/surf-brief.html</string>
  </array>
  <key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>5</integer><key>Minute</key><integer>45</integer>
  </dict>
  <key>StandardErrorPath</key><string>/tmp/surfbrief.err</string>
</dict></plist>
```

### Delivery options

The HTML is fully self-contained — no CDN, no external fonts, theme-aware — so it
works as a `file://` bookmark, an email attachment, or anything you can serve
statically. If you want the daily email route, pipe it through your own sender; the
scripts deliberately don't own delivery.

### Changing the windows

`MORNING = (7.0, 8.5)` and `EVENING_LEAD_HOURS = 1.0` near the top of
`surf_forecast.py`. Hours are local floats. Sunset comes from the API, so the
evening window follows the season on its own.

---

## Data sources

All free, no API keys, no auth.

| Source | Used for | Notes |
|---|---|---|
| [Open-Meteo Marine](https://open-meteo.com/en/docs/marine-weather-api) | Swell height, period, direction | ~5km grid, sampled at one offshore point |
| [Open-Meteo Forecast](https://open-meteo.com/) | Wind, air temp, sunrise/sunset, rainfall history | Wind sampled at two points, north and south |
| [NOAA CO-OPS 9410230](https://tidesandcurrents.noaa.gov/stationhome.html?id=9410230) | Tide predictions | La Jolla / Scripps Pier |
| [NDBC 46258](https://www.ndbc.noaa.gov/station_page.php?station=46258) | Live buoy cross-check | Mission Bay, ~3nm offshore |
| [USGS 11023000](https://waterdata.usgs.gov/monitoring-location/11023000/) | San Diego River discharge | Bacterial risk at OB |

**Failure behaviour:** the buoy and the river degrade gracefully (`{"ok": false}`)
and the renderer prints dashes rather than `None`. If Open-Meteo or NOAA fails hard
the run raises — that's deliberate, a silent half-forecast is worse than no
forecast.

### Two calibrations that look wrong but aren't

**Size uses the model's TOTAL wave height, not its swell partition.** Checked
2026-08-27 against buoy 46258: the total tracked the buoy closely (4.66 ft model vs
4.60 ft measured) while the swell/wind-wave split did not — Open-Meteo put ~all
energy in "swell" and ~0 in wind wave, where the buoy read 2.6 ft swell + 3.9 ft
wind wave. Don't "fix" this by switching to `swell_wave_height`.

**Face height is an estimate**, `Hs × (0.80 + 0.045 × (period − 9))`, clamped
0.80–1.45. Longer period shoals higher. It is not a measurement and the page says so.

---

## Scoring

100 points: swell direction 28 · size fit 30 · period 8 · tide 18 · wind 16, minus
up to 4 for crowd, then capped by the break's own surf-forecast star rating so a 2/5
spot can't outrank a 4/5 one on a mechanical tie.

**Go** ≥82 · **Worth it** ≥67 · **Marginal** ≥50 · **Skip** below.

Local knowledge the model physically cannot see, applied from the folder's research:

- **The canyon lens.** Black's is amplified on long-period groundswell while Scripps
  and the Shores are drained on the same swell. Below 11s the lens switches off and
  the three break alike. Scripps' shadow is deepest on *southerly* long-period — a
  long-period WNW is its best swell, not its worst.
- **The kelp at Sunset Cliffs** smooths NW onshore bump, so it scores well on exactly
  the wind that ruins PB, Mission and OB.
- **The south-wind exception at La Jolla Shores.**
- **PB Point needs size to exist at all** — heavy penalty below 3.5ft face.
- **Mission Beach closes out** on long-period straight-in swell at size.

### Board calls

Per-break `board_ladder` rungs: `[min_face, max_face, primary, backup, note]`.
Every board name must exactly match one of the nine in
`../02-Gear/Owned-and-Wishlist.md`.

A `null` primary means **don't paddle out** — Black's above 7ft face, Sunset Cliffs
above 10ft. That's not an oversight: the folder says plainly the 7'6 Magic is "not
the tool when the canyon is doubling a 16-second swell," and the quiver has "nothing
built for overhead." Any face ≥8ft anywhere raises the quiver-gap flag.

---

## Water quality / bacterial warning

**The brief cannot see official County advisories.** There is no public API —
sdbeachinfo.com is an OutSystems app with no stable endpoint, and Heal the Bay and
EPA BEACON are both dead ends (checked 2026-08-27). **A posted advisory or a sewage
spill will not appear in this brief.** [sdbeachinfo.com](https://www.sdbeachinfo.com/)
or **619-338-2073** is the authoritative check, and at OB Jetty the folder's
instruction is to check it *every single time*.

What it does instead is infer risk from the two signals that actually drive it:
rainfall history and live San Diego River discharge.

**Rain windows** are sized by how much fell: trace (<0.10") 24h · light 48h ·
moderate (0.25–1.0") 72h · heavy (≥1.0") 96h. River-mouth and chronic spots multiply
that (OB ×1.5, Mission ×1.25, Scripps ×1.15). **This is more permissive than the
County's flat 72-hour rule**, so the brief always says when you're still inside the
official window.

**River thresholds**, calibrated against 12 months at gauge 11023000 (p50 3.7 /
p90 31 / p98 205 / storm peak 1740 cfs): <8 baseflow · 8–30 elevated · 30–150
flowing · >150 high.

**Four levels.** `clear` · `caution` (flagged, keeps its rank) · `avoid` (flagged
loudly, keeps its rank) · **`severe` → hard block**: drops out of the ranking, loses
its board call, shown in its own always-visible section. Never buried in the
collapsed table.

A block fires only where risk is acute: the first 24h after ≥0.25" of rain
(anywhere), any measurable rain at a river-mouth or chronically-bad spot, or the
river above 150 cfs at OB. A blanket block of all ten breaks for four days after
every storm would be *more* conservative than the County and would black out the
brief for most of the good season.

Water risk is a **veto, not a scoring component** — no board makes bad water a good
idea.

---

## Data contract

`surf_forecast.py` → JSON → `render.py`. Change one, check the other.

```
date, generated, sunrise, sunset          str
tides[]                                   {time, height, type: "High"|"Low"}
buoy                                      {time, swell_ft, swell_period, swell_dir_txt,
                                           windwave_ft, windwave_period, mean_dir} | null
rain                                      {ok, total_96h, event_inches, last_rain,
                                           hours_since, tier, tier_hours}
river                                     {ok, cfs, when, state, label}
water_day                                 {worst, line, blocked[]}
windows[2]                                one per time window
  key, label, time_txt
  swell_hs, swell_period                  TOTAL wave height/period — drives size
  swell_dir, swell_dir_txt                swell-partition direction
  total_dir, total_dir_txt                total-sea direction (displayed)
  swell_partition_ft/_period              partition, kept for reference only
  face_est, windwave_ft
  wind_speed_n/_s, wind_dir_n/_s (+_txt), air_temp
  tide_h, tide_dir, tide_state
  breaks[10]                              sorted: blocked last, then score desc
    name, score, surf_score, label, cls
    breakdown                             {swell_dir, size, period, tide, wind, crowd}
    notes[], face_ft, local_hs
    board_primary, board_backup           null ⇒ don't paddle out
    board_note, verdict, hazards, tide_note
    crowd, localism, skill, gap
    water                                 {level, headline, reasons[], blocked,
                                           note, chronic}
```

`label`/`cls` are presentation-only and already account for a water block
(`"Don't paddle"` / `"blocked"`). `surf_score` preserves the pre-veto surf score.

---

## Verifying a change

```bash
python3 test_brief.py         # the invariant suite — CI runs this before every publish
python3 surf_forecast.py --json /tmp/t.json && python3 render.py /tmp/t.json /tmp/t.html
grep -c None /tmp/t.html      # must be 0 — None in the page means a null leaked
```

`test_brief.py` covers the checklist below with synthetic data (no network), so
edits to `breaks.json` or the scoring are verified automatically on push. One
coupling to know: the test hardcodes the nine owned board names because
`02-Gear/` lives outside the repo — **if the quiver changes, update both**.
The checklist, for reference:

- **Every board name is one of the nine owned.** A typo silently invents a board.
- **Ladders are contiguous, start at 0, end at 99.** Gaps make `pick_board` fall
  through to the last rung.
- **Direction score peaks exactly at each break's `ideal_dir`** and never rises on
  *leaving* a swell window.
- **Score components stay within max** (28/30/8/18/16) and the total in 0–100.
- **Simulate a storm** — pass a fake `rain`/`river` dict to `water.assess()` and
  confirm OB blocks, the day verdict names it, and nothing blocked appears as the
  day's recommendation.

An audit on 2026-08-27 caught and fixed: the evening window averaging only the
post-sunset hour (float/int hour comparison), a non-monotonic direction score where
a swell just outside a window beat one just inside, a `tide_weight` clamp that made
values >1.0 dead, PB Point's window excluding due W, and nine unguarded numeric slots
that printed `None`. A second audit on 2026-08-29 caught a tenth: the buoy line
interpolated NDBC's `MM`-as-`None` fields raw (now guarded, with a regression test),
plus a missing viewport meta that made the page render at 980px on phones. Don't
reintroduce any of them.

---

## Known limits

- Degree windows are **derived from the compass directions in the write-ups**, not
  from a source that publishes degrees. Only Black's has a real published window.
- Face heights are **estimates**, not measurements.
- The marine model grid is ~5km and **cannot resolve one break from its neighbour**.
  Every difference between adjacent spots comes from the folder's research, not the
  model.
- It **cannot read official County advisories or spill notices** — see above.
- It does not know about **sandbars**, which govern OB Jetty and PB Drive entirely.
- **North County is absent** because it isn't written up yet. Add those breaks to
  `../01-San-Diego-Breaks/North-County.md` first, then to `breaks.json`.

---

*Built 2026-08-27 in Claude Cowork. Ported for Claude Code the same day.*
