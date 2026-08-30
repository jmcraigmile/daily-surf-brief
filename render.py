#!/usr/bin/env python3
"""Render the daily surf brief JSON into a self-contained HTML artifact."""

import json
import sys
import html as H
from datetime import datetime

CSS = """
:root{
  --bg:#f4f7f9; --panel:#ffffff; --panel-2:#eef3f6; --ink:#0f2027; --ink-2:#4a616d;
  --ink-3:#7c919c; --line:#dde6ec; --line-2:#c9d8e1;
  --go:#0a7d5a; --go-bg:#dff5ec; --good:#1c6fa8; --good-bg:#dcecf8;
  --marg:#8a6410; --marg-bg:#faf0d6; --skip:#7a4a4a; --skip-bg:#f2e4e4;
  --accent:#0b6ea8; --warn:#a8410b; --warn-bg:#fbe8dc;
  --bad:#b3261e; --bad-bg:#fbe1de;
  --shadow:0 1px 2px rgba(15,32,39,.06),0 6px 20px rgba(15,32,39,.06);
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --bg:#0b1418; --panel:#121e24; --panel-2:#182831; --ink:#e8f1f5; --ink-2:#a3bac6;
    --ink-3:#6f8894; --line:#22343d; --line-2:#2e444f;
    --go:#4fd8a4; --go-bg:#0e3529; --good:#66bdf0; --good-bg:#0d2c40;
    --marg:#e5bd63; --marg-bg:#372c11; --skip:#d99b9b; --skip-bg:#361f1f;
    --accent:#5cb6e8; --warn:#f0a271; --warn-bg:#3a2113;
    --bad:#ff8a80; --bad-bg:#451c18;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 6px 20px rgba(0,0,0,.35);
  }
}
:root[data-theme="dark"]{
  --bg:#0b1418; --panel:#121e24; --panel-2:#182831; --ink:#e8f1f5; --ink-2:#a3bac6;
  --ink-3:#6f8894; --line:#22343d; --line-2:#2e444f;
  --go:#4fd8a4; --go-bg:#0e3529; --good:#66bdf0; --good-bg:#0d2c40;
  --marg:#e5bd63; --marg-bg:#372c11; --skip:#d99b9b; --skip-bg:#361f1f;
  --accent:#5cb6e8; --warn:#f0a271; --warn-bg:#3a2113;
  --bad:#ff8a80; --bad-bg:#451c18;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 6px 20px rgba(0,0,0,.35);
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font:16px/1.5 ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1080px;margin:0 auto;padding:28px 20px 64px}

header.top{margin-bottom:26px}
.eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);font-weight:650}
.eyebrow .gen{text-transform:none;letter-spacing:.02em;font-weight:500;font-variant-numeric:tabular-nums}
h1{font-size:clamp(28px,5vw,40px);line-height:1.08;margin:8px 0 10px;letter-spacing:-.022em;font-weight:700}
.dayline{font-size:17px;color:var(--ink-2);max-width:62ch;margin:0}
.dayline strong{color:var(--ink);font-weight:650}

.windows{display:grid;gap:20px;grid-template-columns:1fr}
@media(min-width:860px){.windows{grid-template-columns:1fr 1fr}}

.win{background:var(--panel);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);overflow:hidden}
.win-hd{padding:16px 18px 14px;border-bottom:1px solid var(--line);background:var(--panel-2)}
.win-hd h2{margin:0;font-size:19px;letter-spacing:-.01em;font-weight:700}
.win-time{font-size:13px;color:var(--ink-3);margin-top:3px;font-variant-numeric:tabular-nums}

.cond{display:grid;grid-template-columns:repeat(3,1fr);border-bottom:1px solid var(--line)}
.cond div{padding:12px 14px;border-right:1px solid var(--line)}
.cond div:last-child{border-right:0}
.cond .k{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3);font-weight:650}
.cond .v{font-size:16px;font-weight:680;margin-top:3px;font-variant-numeric:tabular-nums;letter-spacing:-.01em}
.cond .s{font-size:12px;color:var(--ink-3);margin-top:1px}
.cond .split{margin-top:5px;padding-top:5px;border-top:1px dotted var(--line-2);font-size:11.5px;line-height:1.4}
.cond .split b{color:var(--ink-2);font-weight:650}

.picks{padding:14px 14px 6px;display:flex;flex-direction:column;gap:11px}
.brk{border:1px solid var(--line);border-radius:11px;padding:13px 14px;background:var(--panel)}
.brk.rank1{border-color:var(--line-2);background:var(--panel-2)}
.brk-hd{display:flex;align-items:baseline;justify-content:space-between;gap:10px}
.brk-name{font-size:17px;font-weight:700;letter-spacing:-.012em}
.pill{font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;padding:3px 8px;border-radius:99px;white-space:nowrap}
.pill.go{color:var(--go);background:var(--go-bg)}
.pill.good{color:var(--good);background:var(--good-bg)}
.pill.marginal{color:var(--marg);background:var(--marg-bg)}
.pill.skip{color:var(--skip);background:var(--skip-bg)}
.pill.blocked{color:#fff;background:var(--bad);letter-spacing:.06em}

/* water quality */
.wq{margin-top:22px;border-radius:14px;padding:15px 17px;box-shadow:var(--shadow);
    border:1px solid var(--line);background:var(--panel)}
.wq.caution{border-color:var(--marg);background:var(--marg-bg)}
.wq.avoid{border-color:var(--warn);background:var(--warn-bg)}
.wq.severe{border-color:var(--bad);background:var(--bad-bg)}
.wq h3{margin:0 0 4px;font-size:15px;font-weight:700;letter-spacing:-.01em;
       display:flex;align-items:center;gap:8px}
.wq .line{font-size:14px;color:var(--ink-2);line-height:1.5}
.wq .src{margin-top:11px;padding-top:10px;border-top:1px solid var(--line);
         font-size:12.5px;color:var(--ink-3);line-height:1.55}
.wq .src b{color:var(--ink-2)}
.wq a{color:var(--accent)}
.dot{width:9px;height:9px;border-radius:50%;flex:0 0 auto}
.dot.clear{background:var(--go)} .dot.caution{background:var(--marg)}
.dot.avoid{background:var(--warn)} .dot.severe{background:var(--bad)}
.gauges{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.gauge{border:1px solid var(--line);border-radius:8px;padding:7px 11px;font-size:12.5px;
       background:var(--panel);font-variant-numeric:tabular-nums}
.gauge b{font-weight:680}

.wqline{margin-top:9px;border-radius:7px;padding:7px 9px;font-size:12.5px;line-height:1.45;
        display:flex;gap:7px;align-items:flex-start}
.wqline.caution{color:var(--marg);background:var(--marg-bg)}
.wqline.avoid{color:var(--warn);background:var(--warn-bg)}
.wqline.severe{color:var(--bad);background:var(--bad-bg);font-weight:600}
.brk.isblocked{opacity:.72;border-style:dashed}
.brk-sub{font-size:12.5px;color:var(--ink-3);margin-top:3px;font-variant-numeric:tabular-nums}
.brk-sub .far{color:var(--marg);background:var(--marg-bg);border-radius:5px;padding:1px 6px;font-weight:650}

.board{margin-top:11px;padding:10px 12px;border-radius:9px;background:var(--bg);border:1px solid var(--line)}
.board-k{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3);font-weight:650}
.board-v{font-size:16px;font-weight:700;margin-top:3px;color:var(--accent);letter-spacing:-.01em}
.board-b{font-size:13px;color:var(--ink-2);margin-top:3px}
.board-b b{color:var(--ink);font-weight:650}
.board-n{font-size:12.5px;color:var(--ink-3);margin-top:6px;line-height:1.45}

.notes{margin:9px 0 0;padding:0;list-style:none;display:flex;flex-direction:column;gap:4px}
.notes li{font-size:12.5px;color:var(--ink-2);line-height:1.45;padding-left:13px;position:relative}
.notes li::before{content:"";position:absolute;left:0;top:7px;width:5px;height:5px;border-radius:50%;background:var(--line-2)}
.flag{color:var(--warn);background:var(--warn-bg);border-radius:7px;padding:7px 9px;font-size:12.5px;line-height:1.45;margin-top:9px}

.rest{border-top:1px solid var(--line);padding:12px 16px 16px}
.rest summary{cursor:pointer;font-size:12.5px;color:var(--ink-3);font-weight:600;list-style:none}
.rest summary::-webkit-details-marker{display:none}
.blockhd{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--bad);
         font-weight:700;margin:6px 2px 1px}
.rest summary::before{content:"▸ ";color:var(--line-2)}
.rest[open] summary::before{content:"▾ "}
table{width:100%;border-collapse:collapse;margin-top:10px;font-size:13px}
th{text-align:left;font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3);font-weight:650;padding:5px 6px;border-bottom:1px solid var(--line)}
td{padding:6px;border-bottom:1px solid var(--line);color:var(--ink-2);vertical-align:top}
td.n{color:var(--ink);font-weight:620}
td.sc{font-variant-numeric:tabular-nums;text-align:right;width:38px}
.tw{overflow-x:auto}

.strip{margin-top:22px;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px 18px;box-shadow:var(--shadow)}
.strip h3{margin:0 0 10px;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3);font-weight:650}
.tides{display:flex;flex-wrap:wrap;gap:8px}
.tide{border:1px solid var(--line);border-radius:8px;padding:7px 11px;font-size:13px;font-variant-numeric:tabular-nums;background:var(--bg)}
.tide b{font-weight:680}
.tide.H b{color:var(--good)} .tide.L b{color:var(--marg)}
.meta{margin-top:14px;font-size:12.5px;color:var(--ink-3);line-height:1.55}
.meta code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;background:var(--panel-2);padding:1px 5px;border-radius:4px}
footer{margin-top:22px;font-size:11.5px;color:var(--ink-3);line-height:1.6;border-top:1px solid var(--line);padding-top:14px}
"""


def esc(s):
    return H.escape(str(s)) if s is not None else ""


def num(v, unit="", dash="--"):
    """Numeric slot that degrades to a dash instead of printing None.
    Model data can be missing at the forecast horizon or in a NOAA gap."""
    return dash if v is None else f"{v}{unit}"


def day_verdict(data):
    """One honest sentence about the day."""
    # Best window by top SURFABLE break -- a blocked spot is never the day's call.
    cands = []
    for i, w in enumerate(data["windows"]):
        ok = [b for b in w["breaks"] if not (b.get("water") or {}).get("blocked")]
        if ok:
            cands.append((ok[0]["score"], -i, ok[0]["name"], w["label"]))
    if not cands:
        return ("Every break is blocked on water quality today. "
                "<strong>Don't paddle out anywhere.</strong>")
    score, _, name, win = max(cands)

    blocked = (data.get("water_day") or {}).get("blocked") or []
    suffix = (f" {', '.join(esc(b) for b in blocked)} "
              f"{'is' if len(blocked) == 1 else 'are'} out on water quality."
              if blocked else "")
    if score >= 82:
        return (f"<strong>{esc(name)}</strong> is the call &mdash; best window is "
                f"{esc(win).lower()}.{suffix}")
    if score >= 67:
        return (f"Nothing special, but surfable. <strong>{esc(name)}</strong> is the "
                f"best of it on the {esc(win).lower()}.{suffix}")
    if score >= 50:
        return (f"Marginal across the board. <strong>{esc(name)}</strong> scores highest "
                f"on the {esc(win).lower()} &mdash; a go only if you just want to get "
                f"wet.{suffix}")
    return f"Nothing worth the drive today. Best-scoring spot doesn't clear the bar.{suffix}"


def render_break(b, rank):
    cls = "brk rank1" if rank == 0 else "brk"
    stars = "★" * b["crowd"] + "☆" * (5 - b["crowd"])
    face = "size n/a" if b["face_ft"] is None else f"~{b['face_ft']}ft face"
    sub = f"{face} &middot; crowd {stars} &middot; {esc(b['skill'])}"
    dm = b.get("drive_minutes")
    if dm:
        sub += f" &middot; {dm} min"
        if b.get("far"):
            sub += " <span class='far'>worth the drive?</span>"

    if b["board_primary"]:
        bv = f"<div class='board-v'>{esc(b['board_primary'])}</div>"
        bb = (f"<div class='board-b'>Backup: <b>{esc(b['board_backup'])}</b></div>"
              if b["board_backup"] else
              "<div class='board-b'>No backup &mdash; nothing else in the quiver fits</div>")
    elif b["face_ft"] is None:
        bv = "<div class='board-v'>No call</div>"
        bb = "<div class='board-b'>Size data missing this run &mdash; check a cam</div>"
    else:
        bv = "<div class='board-v'>Don't paddle out</div>"
        bb = ""
    board = (f"<div class='board'><div class='board-k'>Board call</div>{bv}{bb}"
             f"<div class='board-n'>{esc(b['board_note'])}</div></div>")

    notes = ""
    if b["notes"]:
        notes = ("<ul class='notes'>"
                 + "".join(f"<li>{esc(n)}</li>" for n in b["notes"][:3])
                 + "</ul>")

    wq = b.get("water") or {}
    wqhtml = ""
    if wq and wq.get("level") != "clear":
        lv = wq["level"]
        bits = list(wq.get("reasons") or [])
        if lv in ("avoid", "severe") and wq.get("note"):
            bits.append(wq["note"])
        wqhtml = (f"<div class='wqline {lv}'><span class='dot {lv}'></span><span>"
                  f"<b>{esc(wq['headline'])}.</b> {esc(' '.join(bits))}</span></div>")

    flag = ""
    if b["gap"]:
        flag = ("<div class='flag'><b>Quiver gap.</b> This is past what anything you own is "
                "built for &mdash; the step-up case, in one line.</div>")
    elif b["localism"] >= 4 or "WORST" in b["hazards"] or "DANGEROUS" in b["hazards"]:
        first = b["hazards"].split(".")[0]
        flag = f"<div class='flag'>{esc(first)}.</div>"

    if wq.get("blocked"):
        cls += " isblocked"
    return f"""<div class="{cls}">
  <div class="brk-hd"><span class="brk-name">{esc(b['name'])}</span>
    <span class="pill {b['cls']}">{esc(b['label'])}</span></div>
  <div class="brk-sub">{sub}</div>
  {wqhtml}{board}{notes}{flag}
</div>"""


def split_line(w):
    """Show the swell/windwave split when a mean period would mislead.

    A single blended figure ("4.7ft @ 10.7s") hides a long-period groundswell
    riding under local chop -- which is exactly the sea the canyon reacts to.
    Only shown when the components are far enough apart to matter.
    """
    s = w.get("sea")
    if not s or s.get("source") == "none":
        return ""
    lp, sp = s.get("long_period"), s.get("short_period")
    if not lp or not sp or abs(lp - sp) < 4:
        return ""
    src = "buoy 46258" if s["source"] == "buoy" else "model"
    return (f"<div class='s split'><b>{s['long_hs']:.1f}ft @ {lp:.0f}s</b> groundswell "
            f"under <b>{s['short_hs']:.1f}ft @ {sp:.0f}s</b> chop &middot; {src}</div>")


def render_window(w):
    # A blocked spot must never be buried in the collapsed table -- it's the most
    # safety-critical thing on the page. Surfable picks first, then blocks in
    # full, then the remainder.
    ok = [b for b in w["breaks"] if not (b.get("water") or {}).get("blocked")]
    blocked = [b for b in w["breaks"] if (b.get("water") or {}).get("blocked")]

    picks = "".join(render_break(b, i) for i, b in enumerate(ok[:3]))
    if blocked:
        picks += ("<div class='blockhd'>Blocked on water quality</div>"
                  + "".join(render_break(b, 9) for b in blocked))
    rest = ok[3:]
    rows = "".join(
        f"<tr><td class='n'>{esc(b['name'])}</td><td>{esc(b['label'])}</td>"
        f"<td>{esc(b['board_primary'] or '--')}</td>"
        f"<td class='sc'>{b.get('drive_minutes') or '--'}</td>"
        f"<td class='sc'>{b['score']}</td></tr>"
        for b in rest
    )
    wn, ws = w["wind_speed_n"], w["wind_speed_s"]
    if wn is None and ws is None:
        wind = "--"
    elif None in (wn, ws) or abs(wn - ws) < 3:
        wind = f"{num(wn if wn is not None else ws)} mph {esc(w['wind_dir_n_txt'])}"
    else:
        wind = (f"{num(wn)}mph {esc(w['wind_dir_n_txt'])} N &middot; "
                f"{num(ws)}mph {esc(w['wind_dir_s_txt'])} S")
    return f"""<section class="win">
  <div class="win-hd"><h2>{esc(w['label'])}</h2><div class="win-time">{w['time_txt']}</div></div>
  <div class="cond">
    <div><div class="k">Swell</div>
      <div class="v">{num(w['swell_hs'], 'ft')} @ {num(w['swell_period'], 's')}</div>
      <div class="s">from {esc(w['total_dir_txt'])} &middot; ~{num(w['face_est'], 'ft')} face</div>
      {split_line(w)}</div>
    <div><div class="k">Tide</div><div class="v">{num(w['tide_h'], 'ft')}</div>
      <div class="s">{esc(w['tide_state'])}, {esc(w['tide_dir'])}</div></div>
    <div><div class="k">Wind</div><div class="v">{wind}</div>
      <div class="s">{num(w['air_temp'], '&deg;F')} air</div></div>
  </div>
  <div class="picks">{picks}</div>
  <details class="rest"><summary>The other {len(rest)} breaks</summary>
    <div class="tw"><table><thead><tr><th>Break</th><th>Call</th><th>Board</th><th class="sc">Min</th><th class="sc">Score</th></tr></thead>
    <tbody>{rows}</tbody></table></div>
  </details>
</section>"""


def render_water(data):
    wd = data.get("water_day") or {}
    lv = wd.get("worst", "clear")
    rain, river = data.get("rain") or {}, data.get("river") or {}

    gauges = []
    if rain.get("ok"):
        if rain.get("hours_since") is None:
            gauges.append("<span class='gauge'>Rain <b>none in 5 days</b></span>")
        else:
            gauges.append(f"<span class='gauge'>Rain <b>{rain.get('event_inches', 0)}\"</b> "
                          f"&middot; {int(rain['hours_since'])}h ago</span>")
    if river.get("ok"):
        gauges.append(f"<span class='gauge'>San Diego River <b>{river['cfs']} cfs</b> "
                      f"&middot; {esc(river['label'])}</span>")
    else:
        gauges.append("<span class='gauge'>River gauge <b>unavailable</b></span>")

    title = {"clear": "Water quality — clear",
             "caution": "Water quality — check before you go",
             "avoid": "Water quality — elevated bacterial risk",
             "severe": "Water quality — do not paddle out"}[lv]

    return f"""<div class="wq {lv}">
  <h3><span class="dot {lv}"></span>{esc(title)}</h3>
  <div class="line">{esc(wd.get('line', ''))}</div>
  <div class="gauges">{''.join(gauges)}</div>
  <div class="src"><b>This is inferred, not official.</b> There is no public API for
    County of San Diego beach advisories, so this brief cannot see them. It reasons from
    rainfall history and live San Diego River discharge (USGS gauge 11023000) against each
    break's known chronic sources. A posted advisory or a sewage spill will not appear here.
    The authoritative check is <a href="https://www.sdbeachinfo.com/">sdbeachinfo.com</a>
    or <b>619-338-2073</b> &mdash; and at OB Jetty, the folder's instruction is to check it
    every single time. Post-rain windows here are 48h for light rain and longer for storms;
    <b>the County advises a flat 72 hours after any rain</b>.</div>
</div>"""


def render(data):
    d = datetime.strptime(data["date"], "%Y-%m-%d")
    tides = "".join(
        f"<span class='tide {t['type'][0]}'>{esc(t['type'])} <b>{t['height']}ft</b> "
        f"{esc(t['time'])}</span>" for t in data["tides"])

    b = data.get("buoy")
    if b:
        # NDBC reports missing fields as "MM", which parse to None -- every slot
        # here must degrade to a dash, same as the rest of the page.
        buoy = (f"<b>Buoy 46258</b> (Mission Bay, last reading {esc(b['time'])}): "
                f"swell {num(b['swell_ft'], 'ft')} @ {num(b['swell_period'], 's')} "
                f"from {esc(b['swell_dir_txt'] or '--')}, "
                f"wind wave {num(b['windwave_ft'], 'ft')} @ {num(b['windwave_period'], 's')}. "
                f"The model and the buoy agree on total height; they split the swell and "
                f"wind-wave partition differently, so size here is driven by the total.")
    else:
        buoy = "<b>Buoy 46258</b> unavailable this run &mdash; size is model-only."

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#f4f7f9" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0b1418" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-title" content="Surf Brief">
<title>SD Surf Brief</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <div class="eyebrow">San Diego &middot; daily surf brief &middot;
    <span class="gen">generated {esc(data['generated'])}</span></div>
  <h1>{d.strftime('%A, %B %-d')}</h1>
  <p class="dayline">{day_verdict(data)}</p>
</header>

<div class="windows">
{''.join(render_window(w) for w in data['windows'])}
</div>

{render_water(data)}

<div class="strip">
  <h3>Tides &mdash; La Jolla / Scripps Pier</h3>
  <div class="tides">{tides}</div>
  <div class="meta">{buoy}</div>
</div>

<footer>
  Sunrise {esc(data['sunrise'])} &middot; sunset {esc(data['sunset'])} &middot;
  generated {esc(data['generated'])}.<br>
  Swell and wind from Open-Meteo Marine + Forecast models; tides from NOAA CO-OPS station
  9410230; buoy from NDBC 46258. Scoring windows are derived from the write-ups in
  <code>01-San-Diego-Breaks/</code> &mdash; degree ranges approximate the compass directions
  in those notes, since no public source publishes degree windows for these spots except
  Black's. Face heights are estimates, not measurements. The marine model grid is ~5km and
  cannot resolve one break from its neighbour: the canyon lens at Black's/Scripps/the Shores
  and the kelp effect at Sunset Cliffs are applied from the folder's own research, not from
  the model. Check <a href="https://www.sdbeachinfo.com/">sdbeachinfo.com</a> before OB.
</footer>
</div>
</body>
</html>"""


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "/tmp/surf.json"
    dst = sys.argv[2] if len(sys.argv) > 2 else "/tmp/surf.html"
    with open(src) as f:
        data = json.load(f)
    with open(dst, "w") as f:
        f.write(render(data))
    print(f"wrote {dst}")
