#!/usr/bin/env python3
"""Render the daily surf brief JSON into a self-contained HTML artifact."""

import json
import os
import sys
import html as H
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))


def slugify(name):
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-").replace("--", "-")


_BOARD_SLUGS = None


def board_slug(name):
    """Board name -> quiver.html anchor, from boards.json. Missing file or
    unknown name degrades to no link, never a broken one."""
    global _BOARD_SLUGS
    if _BOARD_SLUGS is None:
        try:
            with open(os.path.join(HERE, "boards.json")) as f:
                _BOARD_SLUGS = {b["name"]: b["slug"] for b in json.load(f)["boards"]}
        except (OSError, KeyError, ValueError):
            _BOARD_SLUGS = {}
    return _BOARD_SLUGS.get(name)


def page_head(title, desc):
    return f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#eaf0ec" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1a2030" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-title" content="greenflash">
<link rel="icon" href="assets/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="assets/icon-180.png">
<link rel="manifest" href="assets/manifest.webmanifest">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:ital,wght@0,300..900;1,300..900&family=Fragment+Mono:ital@0;1&display=swap">
<meta name="description" content="{desc}">
<title>{title}</title>
<style>{CSS}</style>"""


def _logo_svg():
    """Inline the wordmark so its letters take currentColor per theme; the
    rising-sun 'flash' layer stays brand green inside the asset itself."""
    try:
        with open(os.path.join(HERE, "assets", "logo.svg")) as f:
            return f.read()
    except OSError:
        return "<b class='brand'>greenflash</b>"

CSS = """
/* Greenflash design system (Claude Design project "Greenflash Surf Brief System",
   applied 2026-08-30). Dark is the primary theme: the 5:45am read happens in a
   dark room. Verdict colors are functional -- never the only signal. Old alias
   names (--bg, --panel, --ink...) are kept and mapped so component rules below
   stay stable while the token layer evolves. */
:root{
  /* neutrals -- blue hour */
  --bg-0:#1a2030; --bg-1:#222a3c; --bg-2:#2c364a;
  --border-1:#374359; --border-2:#475572;
  --text-1:#e9edf5; --text-2:#9daac0; --text-3:#6f7c93; --horizon:#556480;
  /* verdicts */
  --go:#3fd97f; --go-tint:rgba(63,217,127,.12); --go-border:rgba(63,217,127,.38);
  --maybe:#eac54f; --maybe-tint:rgba(234,197,79,.12); --maybe-border:rgba(234,197,79,.38);
  --skipc:#f0766b; --skip-tint:rgba(240,118,107,.12); --skip-border:rgba(240,118,107,.38);
  --danger:#e5484d; --danger-fill:#b3261e; --danger-on-fill:#ffffff;
  --flash:#3fd97f; --focus-ring:rgba(63,217,127,.5);
  /* type */
  --font-prose:"Archivo","Helvetica Neue",Helvetica,Arial,sans-serif;
  --font-data:"Fragment Mono","SF Mono",Menlo,monospace;
  --tracking-label:.08em;
  /* shape */
  --radius-badge:6px; --radius-card:10px;
  /* aliases for the component rules below */
  --bg:var(--bg-0); --panel:var(--bg-1); --panel-2:var(--bg-2);
  --ink:var(--text-1); --ink-2:var(--text-2); --ink-3:var(--text-3);
  --line:var(--border-1); --line-2:var(--border-2);
  --go-bg:var(--go-tint); --marg:var(--maybe); --marg-bg:var(--maybe-tint);
  --skip:var(--skipc); --skip-bg:var(--skip-tint);
  --accent:var(--flash); --warn:var(--skipc); --warn-bg:var(--skip-tint);
  --bad:var(--danger); --bad-bg:rgba(229,72,77,.14);
  --shadow:none;
}
@media (prefers-color-scheme:light){
  :root:not([data-theme="dark"]){
    --bg-0:#eaf0ec; --bg-1:#fafcfa; --bg-2:#dce6df;
    --border-1:#d0dcd4; --border-2:#b4c4ba;
    --text-1:#1a211d; --text-2:#54615a; --text-3:#78857e;
    --go:#067647; --go-tint:rgba(6,118,71,.09); --go-border:rgba(6,118,71,.35);
    --maybe:#946300; --maybe-tint:rgba(148,99,0,.1); --maybe-border:rgba(148,99,0,.35);
    --skipc:#ba3a2e; --skip-tint:rgba(186,58,46,.09); --skip-border:rgba(186,58,46,.35);
    --danger:#b3261e; --danger-fill:#b3261e;
    --flash:#067647; --focus-ring:rgba(6,118,71,.4);
    --bad-bg:rgba(179,38,30,.1);
    --shadow:0 1px 2px rgba(20,25,30,.06);
  }
}
:root[data-theme="light"]{
  --bg-0:#eaf0ec; --bg-1:#fafcfa; --bg-2:#dce6df;
  --border-1:#d0dcd4; --border-2:#b4c4ba;
  --text-1:#1a211d; --text-2:#54615a; --text-3:#78857e;
  --go:#067647; --go-tint:rgba(6,118,71,.09); --go-border:rgba(6,118,71,.35);
  --maybe:#946300; --maybe-tint:rgba(148,99,0,.1); --maybe-border:rgba(148,99,0,.35);
  --skipc:#ba3a2e; --skip-tint:rgba(186,58,46,.09); --skip-border:rgba(186,58,46,.35);
  --danger:#b3261e; --danger-fill:#b3261e;
  --flash:#067647; --focus-ring:rgba(6,118,71,.4);
  --bad-bg:rgba(179,38,30,.1);
  --shadow:0 1px 2px rgba(20,25,30,.06);
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font:15px/1.55 var(--font-prose);
  -webkit-font-smoothing:antialiased;
}
/* every number, label and timestamp is data -- Fragment Mono, tabular by nature */
.cond .v,.cond .s,.cond .split,.gauge,.tide,.win-time,.eyebrow,.gen,.brk-sub,
th,td,.olface,.olday span,.suitline,.board-k,.cond .k,.board-b,.olspot .win{
  font-family:var(--font-data);
}
.gf-logo{display:inline-block;line-height:0;color:var(--ink)}
.gf-logo svg{height:22px;width:auto;display:block}
.wrap{max-width:1080px;margin:0 auto;padding:calc(28px + env(safe-area-inset-top)) 20px calc(64px + env(safe-area-inset-bottom))}

header.top{margin-bottom:26px}
.eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);font-weight:650}
.eyebrow .brand{color:var(--accent);letter-spacing:.1em}
.eyebrow.gen,.eyebrow .gen{text-transform:none;letter-spacing:.02em;font-weight:500;font-variant-numeric:tabular-nums}
.eyebrow.gen{margin-top:3px;font-size:11.5px}
h1{font-size:clamp(28px,5vw,40px);line-height:1.08;margin:8px 0 10px;letter-spacing:-.022em;font-weight:700}
.dayline{font-size:17px;color:var(--ink-2);max-width:62ch;margin:0}
.dayline strong{color:var(--ink);font-weight:650}

.windows{display:grid;gap:20px;grid-template-columns:1fr}
@media(min-width:860px){.windows{grid-template-columns:1fr 1fr}}

.win{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius-card);box-shadow:var(--shadow);overflow:hidden}
.win-hd{padding:16px 18px 14px;border-bottom:1px solid var(--line);background:var(--panel-2)}
.win-hd h2{margin:0;font-size:19px;letter-spacing:-.01em;font-weight:700}
.win-time{font-size:13px;color:var(--ink-3);margin-top:3px;font-variant-numeric:tabular-nums}

.cond{display:grid;grid-template-columns:repeat(3,1fr);border-bottom:1px solid var(--line)}
.cond>div{padding:12px 14px;border-right:1px solid var(--line)}
.cond>div:last-child{border-right:0}
.cond .k{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3);font-weight:650}
.cond .v{font-size:16px;font-weight:680;margin-top:3px;font-variant-numeric:tabular-nums;letter-spacing:-.01em}
.cond .s{font-size:12px;color:var(--ink-3);margin-top:1px}
.cond .split{margin-top:5px;padding-top:5px;border-top:1px dotted var(--line-2);font-size:11.5px;line-height:1.4}
.cond .split b{color:var(--ink-2);font-weight:650}
@media(max-width:479px){
  .cond{grid-template-columns:1fr}
  .cond>div{border-right:0;border-bottom:1px solid var(--line);padding:10px 14px;
    display:flex;align-items:baseline;gap:4px 12px;flex-wrap:wrap}
  .cond>div:last-child{border-bottom:0}
  .cond .k{flex:0 0 52px}
  .cond .v{margin-top:0}
  .cond .s{margin-top:0;flex-basis:100%;padding-left:64px}
  .cond .split{flex-basis:100%;margin-left:64px}
}

.picks{padding:14px 14px 6px;display:flex;flex-direction:column;gap:11px}
.brk{border:1px solid var(--line);border-radius:var(--radius-card);padding:13px 14px;background:var(--panel)}
.brk.rank1{border-color:var(--line-2);background:var(--panel-2)}
.brk-hd{display:flex;align-items:baseline;justify-content:space-between;gap:10px}
.brk-name{font-size:17px;font-weight:700;letter-spacing:-.012em}
.pill{font-family:var(--font-data);font-size:11px;letter-spacing:var(--tracking-label);
  text-transform:uppercase;padding:3px 8px;border-radius:var(--radius-badge);white-space:nowrap;
  display:inline-flex;align-items:center;gap:6px;border:1px solid transparent}
.pill::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;flex:0 0 auto}
.pill.go{color:var(--go);background:var(--go-tint);border-color:var(--go-border)}
.pill.go::before{animation:gf-breathe 2.4s ease-in-out infinite}
@keyframes gf-breathe{0%,100%{opacity:1}50%{opacity:.35}}
@media (prefers-reduced-motion:reduce){.pill.go::before{animation:none}}
.pill.maybe{color:var(--maybe);background:var(--maybe-tint);border-color:var(--maybe-border)}
.pill.skip{color:var(--skipc);background:var(--skip-tint);border-color:var(--skip-border)}
.pill.blocked{color:var(--danger-on-fill);background:var(--danger-fill);border-color:var(--danger-fill)}
.pill.blocked::before{background:var(--danger-on-fill)}

/* water quality */
.wq{margin-top:22px;border-radius:var(--radius-card);padding:15px 17px;box-shadow:var(--shadow);
    border:1px solid var(--line);background:var(--panel)}
.wq.caution{border-color:var(--marg);background:var(--marg-bg)}
.wq.avoid{border-color:var(--warn);background:var(--warn-bg)}
.wq.severe{border-color:var(--danger-fill);background:var(--danger-fill);color:var(--danger-on-fill)}
.wq.severe .line,.wq.severe .src,.wq.severe .src b{color:rgba(255,255,255,.88)}
.wq.severe a{color:#fff}
.wq.severe .gauge{background:rgba(255,255,255,.12);border-color:rgba(255,255,255,.3);color:#fff}
.wq.severe .dot.severe{background:#fff}
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
.brk-verdict{font-size:13px;color:var(--ink-2);margin-top:6px;line-height:1.45}
.suitline{margin-top:10px;font-size:14px;color:var(--ink-2);font-variant-numeric:tabular-nums}
.suitline b{color:var(--ink);font-weight:680}
.suit-k{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3);font-weight:650;margin-right:2px}
.suit-v{color:var(--flash);font-weight:700;white-space:nowrap}
.outlink{margin-top:6px;font-size:13px}
.outlink a,.olback a{display:inline-block;padding:10px 0}
.nav{margin-top:4px;font-size:13px;display:flex;gap:22px}
.nav a{color:var(--flash);text-decoration:none;font-weight:650;display:inline-block;padding:10px 0}
.nav a:hover{text-decoration:underline}
.wtabs{display:none;gap:8px;margin:0 0 14px}
body.tabbed .wtabs{display:flex}
.wtabs button{flex:1;font-family:var(--font-data);font-size:13px;letter-spacing:var(--tracking-label);
  text-transform:uppercase;padding:12px;border-radius:var(--radius-badge);border:1px solid var(--line);
  background:var(--panel);color:var(--ink-2);cursor:pointer}
.wtabs button.on{border-color:var(--flash);color:var(--flash);background:var(--go-tint)}
body.tabbed .windows .win{display:none}
body.tabbed .windows .win.active{display:block}
.brk-name a{color:inherit;text-decoration:none}
.brk-name a:hover{color:var(--flash)}
.board-v a{color:inherit;text-decoration:none;border-bottom:1px dotted var(--go-border)}
.bk{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius-card);padding:16px;margin-top:14px;scroll-margin-top:16px}
.bk h2{margin:0;font-size:19px;letter-spacing:-.012em}
.bk .meta1{font-family:var(--font-data);font-size:12px;color:var(--ink-3);margin-top:5px}
.bk .prose{margin:10px 0 0;font-size:14px;color:var(--ink-2);line-height:1.55}
.bk .drows{margin-top:12px;border-top:1px solid var(--line)}
.bk .dr{display:flex;gap:12px;padding:7px 0;border-bottom:1px solid var(--line);font-family:var(--font-data);font-size:12.5px;line-height:1.5}
.bk .dr b{flex:0 0 84px;color:var(--ink-3);font-weight:400;text-transform:uppercase;letter-spacing:var(--tracking-label);font-size:10.5px;padding-top:2px}
.bk .dr span{color:var(--ink-2)}
.bk .flag{margin-top:12px}
.laddernote{font-size:11.5px;color:var(--ink-3);font-family:var(--font-prose);padding:2px 6px 8px;line-height:1.45}
.benchhd{margin-top:26px;font-family:var(--font-data);font-size:11px;letter-spacing:var(--tracking-label);text-transform:uppercase;color:var(--ink-3)}
.pagenote{margin-top:16px;font-size:12.5px;color:var(--ink-3);line-height:1.55}
.tabbar{position:fixed;left:0;right:0;bottom:0;z-index:50;display:none;
  grid-template-columns:repeat(4,1fr);background:var(--panel);
  border-top:1px solid var(--line);padding-bottom:env(safe-area-inset-bottom)}
.tabbar a{display:flex;flex-direction:column;align-items:center;gap:3px;
  padding:9px 0 7px;color:var(--ink-3);text-decoration:none;
  font-family:var(--font-data);font-size:10px;letter-spacing:var(--tracking-label);
  text-transform:uppercase}
.tabbar a svg{width:22px;height:22px;display:block}
.tabbar a[aria-current="page"]{color:var(--flash)}
header.top{position:relative}
.themebtn{position:absolute;top:0;right:0;width:44px;height:44px;display:flex;
  align-items:center;justify-content:center;background:var(--panel);
  border:1px solid var(--line);border-radius:var(--radius-badge);
  color:var(--ink-2);cursor:pointer;padding:0}
.themebtn svg{width:20px;height:20px;display:block}
.themebtn .ic-sun{display:none}
:root[data-theme="dark"] .themebtn .ic-sun{display:block}
:root[data-theme="dark"] .themebtn .ic-moon{display:none}
@media(max-width:859px){
  .tabbar{display:grid}
  .nav{display:none}
  .olback{display:none}
  .wrap{padding-bottom:calc(84px + env(safe-area-inset-bottom))}
}
.outlink a,.olback a{color:var(--accent);text-decoration:none;font-weight:650}
.outlink a:hover,.olback a:hover{text-decoration:underline}
.olrows{display:flex;flex-direction:column;gap:10px;margin-top:20px}
.olrow{display:flex;align-items:center;gap:14px;background:var(--panel);border:1px solid var(--line);
       border-radius:var(--radius-card);padding:13px 16px;box-shadow:var(--shadow)}
.olday{width:64px;flex:0 0 auto}
.olday b{display:block;font-size:16px;letter-spacing:-.01em}
.olday span{font-size:12px;color:var(--ink-3);font-variant-numeric:tabular-nums}
.olface{width:84px;flex:0 0 auto;font-size:16px;font-weight:680;font-variant-numeric:tabular-nums}
.olface span{display:block;font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3);font-weight:650}
.olspot{flex:1;font-size:14px;color:var(--ink-2);min-width:0}
.olspot b{color:var(--ink);font-weight:650}
.olspot .win{color:var(--ink-3);font-size:12px}
.olnote{font-size:12.5px;color:var(--ink-3)}
.olback{margin-bottom:14px;font-size:13px}
.olcaveat{margin-top:20px;font-size:12.5px;color:var(--ink-3);line-height:1.55}

.board{margin-top:11px;padding:10px 12px;border-radius:9px;background:var(--bg);border:1px solid var(--line)}
.board-k{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3);font-weight:650}
.board-v{font-size:16px;font-weight:600;margin-top:3px;color:var(--flash);letter-spacing:-.01em}
.board-b{font-size:13px;color:var(--ink-2);margin-top:3px}
.board-b b{color:var(--ink);font-weight:650}
.board-n{font-size:12.5px;color:var(--ink-3);margin-top:6px;line-height:1.45}

.notes{margin:9px 0 0;padding:0;list-style:none;display:flex;flex-direction:column;gap:4px}
.notes li{font-size:12.5px;color:var(--ink-2);line-height:1.45;padding-left:13px;position:relative}
.notes li::before{content:"";position:absolute;left:0;top:7px;width:5px;height:5px;border-radius:50%;background:var(--line-2)}
.flag{color:var(--warn);background:var(--warn-bg);border-radius:7px;padding:7px 9px;font-size:12.5px;line-height:1.45;margin-top:9px}

.rest{border-top:1px solid var(--line);padding:12px 16px 16px}
.rest summary{cursor:pointer;font-size:13px;color:var(--ink-3);font-weight:600;list-style:none;padding:12px 2px;margin:-6px 0}
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

.strip{margin-top:22px;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius-card);padding:16px 18px;box-shadow:var(--shadow)}
.strip h3{margin:0 0 10px;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3);font-weight:650}
.tides{display:flex;flex-wrap:wrap;gap:8px}
.tide{border:1px solid var(--line);border-radius:8px;padding:7px 11px;font-size:13px;font-variant-numeric:tabular-nums;background:var(--bg)}
.tide b{font-weight:680}
.tide.H b{color:var(--flash)} .tide.L b{color:var(--maybe)}
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
    # The tier comes from the break's own label, NOT from re-derived thresholds.
    # The verdict floors are tunable constants in surf_forecast.py; a second
    # copy here already drifted once (2026-08-30: floors moved to 88/62 while
    # this function still said 78/55, so an 80 headlined "is the call" over a
    # Maybe pill). The JSON is the single source of truth.
    cands = []
    for i, w in enumerate(data["windows"]):
        ok = [b for b in w["breaks"] if not (b.get("water") or {}).get("blocked")]
        if ok:
            cands.append((ok[0]["score"], -i, ok[0]["name"], w["label"], ok[0]["label"],
                          ok[0].get("board_primary")))
    if not cands:
        return ("Every break is blocked on water quality today. "
                "<strong>Don't paddle out anywhere.</strong>")
    score, _, name, win, tier, board = max(cands)

    blocked = (data.get("water_day") or {}).get("blocked") or []
    suffix = (f" {', '.join(esc(b) for b in blocked)} "
              f"{'is' if len(blocked) == 1 else 'are'} out on water quality."
              if blocked else "")
    grab = f" Grab the <strong>{esc(board)}</strong>." if board else ""
    if tier == "Go":
        return (f"<strong>{esc(name)}</strong> is the call &mdash; best window is "
                f"{esc(win).lower()}.{grab}{suffix}")
    if tier == "Maybe":
        return (f"A maybe day. <strong>{esc(name)}</strong> is the best of it on the "
                f"{esc(win).lower()}{' with the <strong>' + esc(board) + '</strong>' if board else ''} "
                f"&mdash; read the notes before you commit.{suffix}")
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
        bslug = board_slug(b["board_primary"])
        bname = (f"<a href='quiver.html#{bslug}'>{esc(b['board_primary'])}</a>"
                 if bslug else esc(b["board_primary"]))
        bv = f"<div class='board-v'>{bname}</div>"
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
  <div class="brk-hd"><span class="brk-name"><a href="breaks.html#{slugify(b['name'])}">{esc(b['name'])}</a></span>
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
  <details class="rest"><summary>{len(rest)} more breaks</summary>
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


THEME_BTN = ('<button type="button" id="themebtn" class="themebtn" hidden '
             'aria-label="Toggle light/dark theme">'
             '<svg class="ic-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>'
             '<svg class="ic-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M19.1 4.9l-1.8 1.8M6.7 17.3l-1.8 1.8"/></svg>'
             '</button>')


_ICONS = {
    "home": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M8.5 13a3.5 3.5 0 0 1 7 0" fill="currentColor" stroke="none"/><path d="M2 16.5c3.3-2.6 6.7-2.6 10 0s6.7 2.6 10 0"/></svg>',
    "outlook": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 6h16M4 11h12M4 16h8"/><circle cx="18" cy="16" r="2.6" fill="currentColor" stroke="none"/></svg>',
    "breaks": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 18c2-6 6-11 9-11-2 3-2 6 0 7 1.8.9 5-.5 6-3 .6 3.5-2 8-7 8-3.5 0-6-.5-8-1z"/></svg>',
    "quiver": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6.5 20.5C4 18 9.5 5.5 12 3.5c2.5 2 8 14.5 5.5 17-1.5 1.5-9.5 1.5-11 0z"/><path d="M12 6v13"/></svg>',
}


def tabbar(active):
    """Fixed bottom app bar (phones). aria-current marks the open page."""
    items = [("home", "./", "Home"), ("outlook", "outlook.html", "Outlook"),
             ("breaks", "breaks.html", "Breaks"), ("quiver", "quiver.html", "Quiver")]
    links = ""
    for key, href, label in items:
        cur = ' aria-current="page"' if key == active else ""
        links += f'<a href="{href}"{cur}>{_ICONS[key]}<span>{label}</span></a>' 
    return f'<nav class="tabbar" aria-label="Pages">{links}</nav>'


SUN_JS = """<script>
(function () {
  // Theme follows the sun (sea-mist in daylight, blue-hour otherwise), with a
  // manual toggle override that self-expires at the NEXT sunrise/sunset
  // boundary -- flip to dark at noon and tomorrow is automatic again. The
  // daily page carries real sun times and caches them for the other pages.
  function mins(t) { var p = t.split(":"); return (+p[0]) * 60 + (+p[1]); }
  var sr = document.body.getAttribute("data-sunrise");
  var ss = document.body.getAttribute("data-sunset");
  try {
    if (sr && ss) localStorage.setItem("gf-sun", sr + "|" + ss);
    else { var c = localStorage.getItem("gf-sun"); if (c) { sr = c.split("|")[0]; ss = c.split("|")[1]; } }
  } catch (e) {}
  if (!sr || !ss) { sr = "06:00"; ss = "19:00"; }
  var srm = mins(sr), ssm = mins(ss);
  function nowMins() { var n = new Date(); return n.getHours() * 60 + n.getMinutes(); }
  function sunTheme() { var m = nowMins(); return (m >= srm && m < ssm) ? "light" : "dark"; }
  function nextBoundaryMs() {
    var m = nowMins();
    var d = m < srm ? srm - m : (m < ssm ? ssm - m : 1440 - m + srm);
    return Date.now() + d * 60000;
  }
  function stored() {
    try {
      var o = JSON.parse(localStorage.getItem("gf-theme") || "null");
      if (o && o.until > Date.now()) return o.theme;
      localStorage.removeItem("gf-theme");
    } catch (e) {}
    return null;
  }
  function apply(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    var mc = document.querySelector('meta[name="theme-color"]:not([media])') || document.createElement("meta");
    mc.setAttribute("name", "theme-color");
    mc.setAttribute("content", theme === "light" ? "#eaf0ec" : "#1a2030");
    if (!mc.parentNode) document.head.appendChild(mc);
  }
  apply(stored() || sunTheme());
  var btn = document.getElementById("themebtn");
  if (btn) {
    btn.hidden = false;
    btn.addEventListener("click", function () {
      var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      try { localStorage.setItem("gf-theme", JSON.stringify({ theme: next, until: nextBoundaryMs() })); } catch (e) {}
      apply(next);
    });
  }
})();
</script>"""


def suit_line(data):
    """Water temp + wetsuit call in the header. Measured at the Scripps Pier
    station; no reading means no call, shown honestly, never a guessed suit."""
    wt = data.get("water_temp") or {}
    if not wt.get("ok"):
        return ("<div class='suitline'><span class='suit-k'>Water</span> "
                "temp unavailable this run &mdash; suit call is yours</div>")
    suit = data.get("wetsuit") or "--"
    return (f"<div class='suitline'><span class='suit-k'>Water</span> "
            f"<b>{wt['temp_f']}&deg;F</b> at Scripps Pier &middot; "
            f"<span class='suit-v'>{esc(suit)}</span></div>")


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
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#eaf0ec" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1a2030" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-title" content="greenflash">
<link rel="icon" href="assets/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="assets/icon-180.png">
<link rel="manifest" href="assets/manifest.webmanifest">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:ital,wght@0,300..900;1,300..900&family=Fragment+Mono:ital@0;1&display=swap">
<meta name="description" content="Which break, which board. A daily San Diego surf brief, including the days you shouldn't.">
<title>greenflash.surf</title>
<style>{CSS}</style>
</head>
<body data-date="{esc(data['date'])}" data-sunrise="{esc(data['sunrise'])}" data-sunset="{esc(data['sunset'])}">
<div class="wrap">
<header class="top">
  {THEME_BTN}
  <span class="gf-logo" role="img" aria-label="greenflash">{_logo_svg()}</span>
  <div class="eyebrow" style="margin-top:8px">which break, which board</div>
  <div class="eyebrow gen">San Diego &middot; generated {esc(data['generated'])}</div>
  <h1>{d.strftime('%A, %B %-d')}</h1>
  <p class="dayline">{day_verdict(data)}</p>
  {suit_line(data)}
  <nav class="nav"><a href="outlook.html">Outlook</a><a href="breaks.html">Breaks</a><a href="quiver.html">Quiver</a></nav>
</header>

<div class="wtabs" id="wtabs">
  <button type="button" aria-selected="false">Dawn</button>
  <button type="button" aria-selected="false">Dusk</button>
</div>

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
{tabbar("home")}
{TABS_JS}
{SUN_JS}
</body>
</html>"""


TABS_JS = """<script>
(function () {
  // Dawn/Dusk tabs, phones only. Progressive enhancement: without JS the two
  // windows stack exactly as before. Auto-select: on TODAY'S page an afternoon
  // read opens Dusk; a night-before page (dated tomorrow) always opens Dawn,
  // because that is the session being planned.
  var wins = [].slice.call(document.querySelectorAll(".windows .win"));
  if (wins.length < 2) return;
  var bar = document.getElementById("wtabs");
  var tabs = [].slice.call(bar.querySelectorAll("button"));
  var mq = window.matchMedia("(max-width:859px)");
  var n = new Date();
  var iso = n.getFullYear() + "-" + ("0" + (n.getMonth() + 1)).slice(-2) + "-" + ("0" + n.getDate()).slice(-2);
  var idx = (document.body.getAttribute("data-date") === iso && n.getHours() >= 12) ? 1 : 0;
  function show(i) {
    idx = i;
    wins.forEach(function (w, j) { w.classList.toggle("active", j === i); });
    tabs.forEach(function (t, j) { t.classList.toggle("on", j === i); t.setAttribute("aria-selected", String(j === i)); });
  }
  function apply() { document.body.classList.toggle("tabbed", mq.matches); show(idx); }
  tabs.forEach(function (t, i) { t.addEventListener("click", function () { show(i); }); });
  if (mq.addEventListener) mq.addEventListener("change", apply); else mq.addListener(apply);
  apply();
})();
</script>"""


def _outlook_row(day):
    """One outlook day -> one row. Missing data degrades to dashes, honestly."""
    who = f"<b>{esc(day['dow'])}</b><span>{esc(day['disp'])}</span>"
    if not day.get("ok"):
        return (f"<div class='olrow'><div class='olday'>{who}</div>"
                f"<div class='olface'>--</div>"
                f"<div class='olspot olnote'>couldn't build this day &mdash; source outage</div></div>")
    if day.get("no_data") or not day.get("best"):
        return (f"<div class='olrow'><div class='olday'>{who}</div>"
                f"<div class='olface'>--</div>"
                f"<div class='olspot olnote'>beyond the swell model's horizon</div></div>")
    faces = day.get("faces") or []
    lo, hi = min(faces), max(faces)
    face = f"~{lo:g}ft" if abs(hi - lo) < 0.5 else f"{lo:g}&ndash;{hi:g}ft"
    b = day["best"]
    return f"""<div class="olrow">
  <div class="olday">{who}</div>
  <div class="olface">{face}<span>face</span></div>
  <div class="olspot"><b>{esc(b['name'])}</b> <span class="win">{esc(b['window'])}</span></div>
  <span class="pill {esc(b['cls'])}">{esc(b['label'])}</span>
</div>"""


def render_outlook(data):
    rows = "".join(_outlook_row(d) for d in data["days"])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#eaf0ec" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1a2030" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-title" content="greenflash">
<link rel="icon" href="assets/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="assets/icon-180.png">
<link rel="manifest" href="assets/manifest.webmanifest">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:ital,wght@0,300..900;1,300..900&family=Fragment+Mono:ital@0;1&display=swap">
<title>greenflash &middot; outlook</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="top">
  {THEME_BTN}
  <div class="olback"><a href="./">&larr; today's brief</a></div>
  <span class="gf-logo" role="img" aria-label="greenflash">{_logo_svg()}</span>
  <div class="eyebrow" style="margin-top:8px">5-day outlook</div>
  <div class="eyebrow gen">generated {esc(data['generated'])}</div>
  <h1>The next five days</h1>
</header>
<div class="olrows">{rows}</div>
<div class="olcaveat">Each row is the day's best window and its top-ranked break, from the
same scoring as the daily brief. <b>The further out, the softer the read:</b> beyond
tomorrow the buoy can't help (model-only sea), sizes are estimates, and the water-quality
veto reflects <b>current</b> rain and river conditions &mdash; it cannot see a storm that
hasn't happened yet. Trust the shape, not the decimals; check back as the day gets close.</div>
</div>
{tabbar("outlook")}
{SUN_JS}
</body>
</html>"""




# ---------------------------------------------------------------- breaks page

def _break_card(brk):
    w = brk.get("water") or {}
    stars = "★" * brk["crowd"] + "☆" * (5 - brk["crowd"])
    windows = " / ".join(f"{lo}–{hi}°" for lo, hi in brk["swell_windows"])
    ideal = brk.get("ideal_dir")
    pl, ph = brk.get("period_ideal", [8, 18])
    lo, hi = brk["size_ideal"]
    ladder_rows = ""
    for rlo, rhi, primary, backup, note in brk["board_ladder"]:
        face = f"{rlo:g}–{rhi:g}ft" if rhi < 99 else f"{rlo:g}ft+"
        if primary is None:
            call = "<b style='color:var(--danger)'>don't paddle out</b>"
        else:
            pslug = board_slug(primary)
            call = (f"<a href='quiver.html#{pslug}'>{esc(primary)}</a>" if pslug else esc(primary))
            if backup:
                call += f" <span style='color:var(--ink-3)'>/ {esc(backup)}</span>"
        ladder_rows += (f"<tr><td class='sc' style='text-align:left;width:70px'>{face}</td>"
                        f"<td>{call}</td></tr>"
                        f"<tr><td></td><td class='laddernote'>{esc(note)}</td></tr>")
    drive = f"{brk.get('drive_minutes', '--')} min · {brk.get('drive_miles', '--')} mi"
    hazards = f"<div class='flag'>{esc(brk['hazards'])}</div>" if brk.get("hazards") else ""
    return f"""<article class="bk" id="{slugify(brk['name'])}">
  <h2>{esc(brk['name'])}</h2>
  <div class="meta1">{esc(brk.get('region', ''))} · {drive} · crowd {stars} · {esc(brk['skill'])}</div>
  <p class="prose">{esc(brk['verdict'])}</p>
  <div class="drows">
    <div class="dr"><b>Swell</b><span>{windows}{f" · ideal {ideal}°" if ideal is not None else ""}</span></div>
    <div class="dr"><b>Size</b><span>{lo:g}–{hi:g}ft face ideal · works {brk['size_min']:g}–{brk['size_max']:g}ft</span></div>
    <div class="dr"><b>Period</b><span>{pl:g}–{ph:g}s</span></div>
    <div class="dr"><b>Tide</b><span>{esc('/'.join(brk['tide_pref']))} · {esc(brk['tide_note'])}</span></div>
    <div class="dr"><b>Water</b><span>{esc(w.get('note', 'no notes'))}</span></div>
  </div>
  {hazards}
  <div class="ladder"><div class="board-k" style="margin-top:12px">Board ladder</div>
    <div class="tw"><table><tbody>{ladder_rows}</tbody></table></div></div>
</article>"""


def render_breaks(cfg):
    active = [b for b in cfg["breaks"] if not b.get("hidden")]
    bench = [b for b in cfg["breaks"] if b.get("hidden")]
    cards = "".join(_break_card(b) for b in active)
    benchhtml = ""
    if bench:
        benchhtml = ("<div class='benchhd'>On the bench (hidden from the daily brief)</div>"
                     + "".join(_break_card(b) for b in bench))
    return f"""<!doctype html>
<html lang="en">
<head>
{page_head("greenflash · breaks", "The San Diego breaks the daily brief scores, in full detail.")}
</head>
<body>
<div class="wrap">
<header class="top">
  {THEME_BTN}
  <div class="olback"><a href="./">&larr; today's brief</a></div>
  <span class="gf-logo" role="img" aria-label="greenflash">{_logo_svg()}</span>
  <div class="eyebrow" style="margin-top:8px">the breaks</div>
  <h1>The spots</h1>
  <nav class="nav"><a href="outlook.html">Outlook</a><a href="quiver.html">Quiver</a></nav>
</header>
{cards}
{benchhtml}
<div class="pagenote">Degree windows are derived from the compass directions in the research
notes, not from a degree-publishing source — treat them as approximations. Water risk here is
each spot's chronic profile; the daily brief layers live rain and river on top. sdbeachinfo.com
/ 619-338-2073 is the authoritative water check, every time at the river mouths.</div>
</div>
{tabbar("breaks")}
{SUN_JS}
</body>
</html>"""


# ---------------------------------------------------------------- quiver page

def _board_card(b):
    return f"""<article class="bk" id="{esc(b['slug'])}">
  <h2>{esc(b['name'])}</h2>
  <div class="meta1">{esc(b['shaper'])} · {esc(b['dims'])} · {esc(b['volume'])}</div>
  <p class="prose">{esc(b['role'])}</p>
  <div class="drows">
    <div class="dr"><b>Fins</b><span>{esc(b['fins'])}</span></div>
    <div class="dr"><b>Range</b><span>{esc(b['range'])}</span></div>
  </div>
</article>"""


def render_quiver(data):
    cards = "".join(_board_card(b) for b in data["boards"])
    return f"""<!doctype html>
<html lang="en">
<head>
{page_head("greenflash · quiver", "The nine boards the daily brief picks from.")}
</head>
<body>
<div class="wrap">
<header class="top">
  {THEME_BTN}
  <div class="olback"><a href="./">&larr; today's brief</a></div>
  <span class="gf-logo" role="img" aria-label="greenflash">{_logo_svg()}</span>
  <div class="eyebrow" style="margin-top:8px">the quiver</div>
  <h1>The boards</h1>
  <nav class="nav"><a href="outlook.html">Outlook</a><a href="breaks.html">Breaks</a></nav>
</header>
{cards}
<div class="pagenote">Volumes are estimates from a bounding-box formula on an unvalidated
anchor — the one “measured” figure matched the shaper's published stock number, so treat
every litre here as approximate until the boards are actually measured.</div>
</div>
{tabbar("quiver")}
{SUN_JS}
</body>
</html>"""


if __name__ == "__main__":
    argv = sys.argv[1:]
    mode = "daily"
    for flag, name in (("--outlook", "outlook"), ("--breaks", "breaks"), ("--quiver", "quiver")):
        if flag in argv:
            mode = name
            argv.remove(flag)
    src = argv[0] if len(argv) > 0 else "/tmp/surf.json"
    dst = argv[1] if len(argv) > 1 else "/tmp/surf.html"
    with open(src) as f:
        data = json.load(f)
    out = {"daily": render, "outlook": render_outlook,
           "breaks": render_breaks, "quiver": render_quiver}[mode](data)
    with open(dst, "w") as f:
        f.write(out)
    print(f"wrote {dst}")
