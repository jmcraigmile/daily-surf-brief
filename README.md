# Daily Surf Brief

Scores the written-up San Diego breaks (13 on file, 12 in the daily rotation --
Oceanside Pier is `"hidden": true`, kept but not shown) against live swell, tide, wind and
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
| `surf_forecast.py` | Fetches conditions, scores every non-hidden break for both windows, picks boards. Writes JSON. |
| `water.py` | Bacterial risk per break from rainfall + river discharge. Imported by `surf_forecast.py`; also runnable standalone. |
| `render.py` | JSON → self-contained HTML. No network, no assets, no external CSS. |
| `breaks.json` | **The knob.** All per-break scoring rules and board ladders. Edit this, not the Python. |
| `test_brief.py` | No-network invariant suite: ladders, board names, direction monotonicity, component maxima, water-veto sims, render regressions. Gates every CI publish. |
| `boards.json` | The quiver, curated for the public quiver page. Names must match `breaks.json` ladders and the test suite. Volumes carry the audit's honest labels. |
| `breaks.html` / `quiver.html` (published) | **Detail pages**: per-spot research (verdict prose, data ledger, hazards, board ladder) and per-board cards. The landing page stays data-and-selection; prose lives here. |
| `outlook.html` (published) | **5-day outlook**: one row per day -- face height, the day's best break, Go/Maybe/Skip. Built by `--outlook 5` + `render.py --outlook`; non-fatal in CI (a failure writes a fallback page, never blocks the daily brief). Beyond tomorrow the buoy split is out of trust range and the water veto reflects current conditions -- the page says so. |
| `.github/workflows/publish.yml` | The scheduler + publisher: four UTC crons (two per window, covering DST), tests → fetch → render → deploy to Pages. |

`__pycache__/` is generated — gitignore it.

**Ground truth lives outside this folder.** `breaks.json` is a machine-readable
derivative of:

- `../01-San-Diego-Breaks/Central-SD.md`, `South-County.md` and `North-County.md` —
  swell windows, tides, wind, crowds, hazards, water quality
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

The repo root is this folder. **Live at [greenflash.surf](https://greenflash.surf)**
(custom domain added 2026-08-30, renamed from glassoff.surf 2026-08-29:
Cloudflare-registered, DNS-only records pointing at GitHub Pages, which serves the
SSL cert — the DNS-only choice is deliberate, Cloudflare's proxy would block
GitHub's cert issuance). Phone access: open greenflash.surf, Add to Home Screen.
The old jmcraigmile.github.io/daily-surf-brief URL redirects.

**The rename needs three manual steps outside this repo**, and the page stays
broken until all three are done:

1. Register/confirm `greenflash.surf` in Cloudflare and recreate the DNS records —
   the four apex `A` records to GitHub Pages' IPs plus the `www` `CNAME` to
   `jmcraigmile.github.io`, all **DNS-only (grey cloud)**, never proxied.
2. In the repo's Settings → Pages, change the custom domain to `greenflash.surf`,
   then wait for the new cert to issue before ticking "Enforce HTTPS".
3. Re-add the phone home-screen shortcut — the old icon points at the previous
   host and won't follow a redirect.

Keep `glassoff.surf` registered and redirecting while any old bookmark or
home-screen icon might still be in use.

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

### Scoring direction comes from the measured swell, not the model partition

**Added 2026-08-30, alongside the North County spots.** Direction is the largest
single scoring lever (28 of 100), and it was running on Open-Meteo's
swell-partition direction — the same field the canyon fix had already abandoned as
untrustworthy.

Adding Swami's exposed it. On a measured 16.7s SSW groundswell the partition
reported **279° (W)**, which scored Swami's **26.8/28 and ranked it first in the
county** — a W/NW-only point, on a south swell it barely sees. The buoy's measured
**209° (SSW)** scores it **0.0**. A 27-point swing on the top lever, and the brief
would have sent him 32 minutes north to a spot that wasn't breaking.

Scoring now uses `dom_dir`: the **long-period component's** direction when there is
a real long-period component (energy share ≥40% and period ≥10s), falling back to
the **total-sea** direction — a trusted field — rather than the partition. The
window output carries `dom_dir`, `dom_dir_txt` and `dir_source` so the choice is
visible.

Known limitation, unchanged: beyond ~17.5° outside a window the direction score is
0, so a 20°-off and a 90°-off swell are indistinguishable. Pre-existing, and it
matters more now that the input is correct.

### The canyon runs on the long-period component

**Added 2026-08-30.** Total height and period still come from the model. What
`sea_state()` sources carefully is the **split** between long-period groundswell
and short-period chop, because the canyon lens needs it. Background and the
physics are in `../01-San-Diego-Breaks/Conditions-and-Forecasting.md`.

The bug it fixes: the lens was fed the model's *blended* mean period. On
2026-08-30 the buoy held 3.3ft @ 16.7s SSW for six hours while the model reported
a 10.7s blend, so the lens read "barely in play" on exactly the south groundswell
`Central-SD.md` says the canyon wraps into Black's through summer. Two errors at
once — wrong period, applied to the wrong energy.

**Partition sources, in priority order:**

| Source | When | Confidence |
|---|---|---|
| **buoy** | NDBC 46258 measures the split directly. Used only if it's self-consistent with the model total (within 35%) **and** the target day is within one day of the reading. | high |
| **model** | Open-Meteo's own partition, **only if** it reproduces the model's own mean period (within 2s). It frequently doesn't. | medium |
| **none** | No usable split. Falls back to old whole-sea behaviour, and the brief says the read is approximate. | low |

**A buoy is an observation, not a forecast** — it's ignored for dates more than a
day out. That's why the evening CI run (which builds tomorrow) can use it and a
`--date` five days out cannot.

**The lens acts on the groundswell only**, then recombines in quadrature
(`√(H_long'² + H_short²)`) — wave energy adds, heights don't. Amplifying the whole
sea over-applies badly: 8.0ft vs the correct ~6.5ft on that morning's data.

Effective period is re-weighted by the new energy mix afterward, so an amplified
groundswell also shoals higher. **Blast radius is the three canyon spots only** —
`test_non_canyon_spots_unaffected_by_decomposition` pins that.

The page shows the split in the Swell cell whenever the two components are ≥4s
apart, so a misleading mean period is visible rather than silent.

---

## Scoring

100 points: swell direction 28 · size fit 30 · period 8 · tide 18 · wind 16, minus
up to 4 for crowd, then capped by the break's own surf-forecast star rating so a 2/5
spot can't outrank a 4/5 one on a mechanical tie.

**Verdicts are a three-tier traffic light** (Option A, 2026-08-30): 🟢 **Go** ≥88 ·
🟡 **Maybe** 62–87 · 🔴 **Skip** below. Water-quality **Don't paddle** stays a separate
fourth state — a veto, not a grade. Three tiers because they are the only three
decisions actually made: rearrange the morning / go if convenient / don't bother.

**The floors were re-set the same day, and the reasoning matters more than the
numbers** (`GO_FLOOR` / `MAYBE_FLOOR` in `surf_forecast.py`). They opened at 78/55,
which sounded reasonable and measured badly: across a sweep of the condition space
Go fired on **66.7% of mornings** and lit **~3.7 of 13 breaks at once**. That is
"surfable" — which in San Diego is most days — and four simultaneous Go badges is a
menu, not a call. At **88** it fires on ~30.8% of mornings (~2/week) and typically
names ~0.9 breaks. `MAYBE_FLOOR` went 55 → 62 for the mirror reason: at 55 only 1.9%
of mornings had no rideable option, so Skip was barely pruning the ranked list.

⚠️ Measured over an **even sweep**, not a real year. Real weather clusters, so the
true firing rate will drift. **Recalibrate from `Break-Log.md`: if Go fires and the
session is mediocre, `GO_FLOOR` is still too low.** `test_go_stays_rare_enough_to_mean_must_go`
guards the intent with deliberately wide bounds — it fails if Go becomes a menu again
*or* becomes so rare you'd ignore it.

> This also settled a live conflict worth remembering. The PB Drive chop session
> scores 80; under Go ≥78 it read **Go**, which broke the guarantee the chop penalty
> was built to provide. The tempting fix was deepening the penalty to ~−12.4 (still
> inside its allowed band). That would have been **tuning a physical constant
> anchored on a real session to compensate for a threshold set too low.** The
> threshold was the bug.

**Chop dominance** (Break-Log 2026-08-30, PB Drive): when the sea split shows the
short-period component carrying ≥40% of the energy at ≤9s, the day takes a graded
penalty (−5 to −14) *and* is capped at Maybe — a sea that is mostly 8-second windwave
is a conveyor-belt paddle with textured faces no matter what else aligns. The same
condition stands the mini-Simmons swaps down (the blended period can pass the swap
gate while hiding exactly the texture the planing hull hates). Thresholds are
tunable calibration defaults in `CHOP_*` constants, anchored to that first logged
session.

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

**Condition-gated swaps (added 2026-08-29).** The ladder answers *how big is it*. An
optional per-break `board_swaps` list answers *what shape is it in*, and overrides the
rung when it matches:

```json
"board_swaps": [
  {"face": [2.5, 5.5], "max_wind": 8, "min_period": 9,
   "primary": "5'4 Mini-Simmons", "backup": "5'8 Fish", "note": "..."}
]
```

First match wins; a swap **never** overrides a `null` "don't paddle out" rung; with no
condition context (`pick_board(brk, face)` with no third argument) swaps are skipped and
the ladder result stands. Swap board names are subject to the same nine-board rule as
rungs — check both.

This exists because the **mini-Simmons is gated by takeoff shape and surface texture, not
by wave height**. It's a planing hull, not an ankle-to-waist groveller: fast and legitimate
past waist-high on a clean organised face, genuinely bad on a steep late drop. Full
reasoning and sources in [`../02-Gear/Mini-Simmons-Deep-Dive.md`](../02-Gear/Mini-Simmons-Deep-Dive.md).
It currently has swap bands at La Jolla Shores, Scripps, PB Drive, Mission and OB Pier, and
is deliberately absent from Black's, OB Jetty, Sunset Cliffs, Crystal Pier and PB Point —
that file explains each exclusion.

⚠️ **Gates use wind (mph) and period, never wind-wave height.** Open-Meteo puts ~all energy
in the swell partition and ~0 in wind wave here — see *Two calibrations that look wrong but
aren't* above. Wind-wave height is not a usable texture proxy in this pipeline; adding it
to a swap would look like an improvement and silently disable the gate.

The glider has a swap too, at **Cardiff only** (added 2026-08-30): the ladder capped it
at 2ft, and Josh Hall — Skip Frye's protégé, and the category's clearest voice — names
the Cardiff reefs by name as glider water. It now runs to **4ft face** when the sea is
clean. It reuses the chop gate rather than inventing one, which is the point: chop is
*precisely* the glider's documented weakness (it chatters like speed wobbles), so the
extension inherited a Break-Log-calibrated texture gate for free. **4ft is our number,
not Hall's** — he gave no band. Unvalidated; log the sessions. See
[`../02-Gear/Glider-Deep-Dive.md`](../02-Gear/Glider-Deep-Dive.md).

### The crowd gate

Some boards are ruled out by the **people** in the water, not the wave. `_board_crowd_limits`
in `breaks.json` maps a board to the highest break `crowd` rating it may be called at, in
**both** the primary and backup slot — recommending a board as the fallback at a mobbed
peak has the identical problem. `_crowd_gate()` applies it after the ladder and swaps.

Currently one entry: **`11'0 Chris Craft` → 3**. An 11ft glider on a 10ft leash swings a
~20ft radius when a closeout tears it loose, and it out-paddles the entire lineup, so a
packed peak is the one place the shape is a genuine liability — a point Frye and Hall both
make in their own words. It stands at Cardiff (crowd 3) and is gated at La Jolla Shores
and Swami's (crowd 4).

**A gated board is demoted, never blocked.** If nothing safer sits on the ladder the board
is still called, with the warning attached — the wave is fine, only the board choice is
wrong, and turning a rideable morning into a refusal over an etiquette rule would be a bad
failure. Pinned by `test_crowd_gate_on_oversized_boards`.

Note this gate is **not** in the same evidential class as the mini-Simmons swap thresholds.
Those are unvalidated personal heuristics; this needed no calibration — the limit is a
judgment the sources state directly, reading a `crowd` field already researched per break.

A `null` primary means **don't paddle out** — Black's above 7ft face, **Swami's above
9ft**, Sunset Cliffs above 10ft. That's not an oversight: the folder says plainly the
7'6 Magic is "not the tool when the canyon is doubling a 16-second swell," and the
quiver has "nothing built for overhead." Any face ≥8ft anywhere raises the quiver-gap
flag. Swami's ceiling sits higher than Black's because a point takeoff is more
forgiving than a Black's late drop, not because the quiver improved.

### Region, drive time, and the thirteen

**Cardiff Reef, Swami's and Oceanside Pier were added 2026-08-30** to close measured
coverage gaps — NW-onshore wind, high tide, and size — rather than by reputation. The
rationale, the spots deliberately rejected as redundant, and the hard exclusions
(**Imperial Beach, the Tijuana Sloughs and Coronado on standing sewage closures;
Windansea on documented extreme localism**) are all in
[`../01-San-Diego-Breaks/North-County.md`](../01-San-Diego-Breaks/North-County.md).

Each break carries `region`, `drive_minutes` and `drive_miles` — **OSRM free-flow
driving times from Jake's home neighbourhood (Mission Hills)**, recomputed 2026-08-30
when he gave his location. The earlier numbers assumed Pacific Beach and were wrong,
badly so for the PB and OB spots.

🔒 **This repo is public. The reference point is deliberately neighbourhood-level —
never a street address or ZIP.** `test_no_street_address_in_the_repo` enforces that:
a leak here would sit in git history permanently. House-level precision changes no
drive time worth having.

Free-flow is fair for the dawn window; the evening window meets real traffic, so treat
the North County numbers as a floor. Anything over `DRIVE_FLAG_MINUTES` (45) gets a
"worth the drive?" marker — currently **Oceanside Pier at 49 min**, the only one that
trips it. **Scoring is deliberately unaffected**: rank on quality, show the distance,
let the reader judge.

---

## Water quality / bacterial warning

**The brief cannot see official County advisories.** sdbeachinfo.com is an OutSystems
app with no stable endpoint, and Heal the Bay and EPA BEACON are dead ends (checked
2026-08-27).

⚠️ **Corrected 2026-08-30.** An earlier version of this file said flatly "there is no
public API." That was too absolute: **California does publish a machine-readable beach
postings/closures dataset** (CKAN on `data.ca.gov`, 35,748 records, fully queryable).
But it is **not a live safety gate** — queried 2026-08-30, its newest record anywhere
was **2026-03-06**, roughly six months stale, and it contained **no record of the
Imperial Beach or Coronado closures active that week**. The Water Board publishes it
monthly. Wiring it in as a safety check would report "no advisories" for a beach under
an active sewage closure, which is worse than saying nothing. Use it for historical
base rates if ever needed; never as current status.

**A posted advisory or a sewage
spill will not appear in this brief.** [sdbeachinfo.com](https://www.sdbeachinfo.com/)
or **619-338-2073** is the authoritative check, and at OB Jetty the folder's
instruction is to check it *every single time*.

What it does instead is infer risk from the two signals that actually drive it:
rainfall history and live San Diego River discharge.

**Rain windows are anchored to the County's own published trigger** (corrected
2026-08-30, verified against `DEHQ_bb_advisory_explanation.pdf`):

> *"General (rain) advisories are issued when rainfall equal to or greater than
> **0.20 inch** is received... avoid contact with ocean and bay water for a period of
> **72 hours** after rainfall ends."*

So: **≥0.20″ → 72h** (the County's rule, exactly) · ≥1.0″ → 96h (longer runoff tail) ·
0.05–0.20″ → 24h (measurable but under the County's threshold). The previous 0.10/0.25
boundaries were invented and matched nothing.

**`outlet_proximity` replaced the invented `rain_factor` multipliers.** The old
×1.15/×1.25/×1.5 had no empirical or regulatory basis — a fair hit from the fact-check.
The replacement comes straight from the County's own wording, which singles out
*"storm drains, creeks, rivers, and lagoon outlets"*: `at` (on the outlet — OB Jetty at
the river mouth, Cardiff at the San Elijo Lagoon mouth) · `nearby` (named outlet within
~a mile) · `none`.

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
water_temp                                {ok, temp_f, when} | {ok: false, error}
wetsuit                                   str from WETSUIT_LADDER | null (no reading, no call)
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
    breakdown                             {swell_dir, size, period, tide, wind, crowd, chop}
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
- **The canyon reads the long-period component**, never the blended mean period,
  and amplifies only that component's energy. Non-canyon spots must be untouched
  by the decomposition.
- **Scoring direction uses `dom_dir`**, never the raw model swell partition.
- **Every board name is one of the nine owned** — `test_brief.py` hardcodes that
  list because `02-Gear/` is outside this repo. Quiver changes need both updated.
- **Swami's refuses above 9ft face** and Black's above 7ft; a `board_swaps` entry
  must never override a refusal.

An audit on 2026-08-27 caught and fixed: the evening window averaging only the
post-sunset hour (float/int hour comparison), a non-monotonic direction score where
a swell just outside a window beat one just inside, a `tide_weight` clamp that made
values >1.0 dead, PB Point's window excluding due W, and nine unguarded numeric slots
that printed `None`. A second audit on 2026-08-29 caught a tenth: the buoy line
interpolated NDBC's `MM`-as-`None` fields raw (now guarded, with a regression test),
plus a missing viewport meta that made the page render at 980px on phones. A third,
2026-08-30, caught the canyon lens running on the model's blended mean period and
applying itself to the whole sea instead of the groundswell component -- see "The
canyon runs on the long-period component" above — and, in the same pass, scoring
direction running on that same bad partition field, which ranked a W/NW point first
on a south swell. Don't reintroduce any of them.

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
