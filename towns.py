"""
Public town pages: one crawlable page per municipality.

Routes:
  GET /town/           list of towns
  GET /town/<slug>/    30-day activity summary for one town

Same privacy rule as stats.py: only counts leave this module (no addresses,
unit IDs or narratives), and any group with fewer than MIN_COUNT calls is
dropped. A town page whose 30-day total is below MIN_COUNT is still served,
but marked noindex and left out of the sitemap, so thin pages don't get
indexed.

Towns come from the incidents table (the dispatch feed's own municipality
names), so a town with no calls on record has no page (404).
"""
import re
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import quote

from flask import Blueprint, Response, abort

from incidents import classify_service
from models import Incident, db
from stats import MIN_COUNT, WINDOW_DAYS, _to_eastern, pretty_type

towns_bp = Blueprint("towns", __name__)

SITE = "https://www.delcospot.com"
CACHE_SECONDS = 600
_cache = {"data": None, "at": 0.0}


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def display_name(name):
    """Spell out the feed's abbreviations for people and search engines."""
    out = re.sub(r"\bTwp\.?(?=\s|$)", "Township", name.strip(), flags=re.I)
    out = re.sub(r"\bBoro\.?(?=\s|$)", "Borough", out, flags=re.I)
    return out


def build_town_stats(now_utc=None):
    """{slug: {...}} for every town seen in the feed, with 30-day aggregates."""
    now_utc = now_utc or datetime.now(timezone.utc).replace(tzinfo=None)
    start = now_utc - timedelta(days=WINDOW_DAYS)
    last7_start = now_utc - timedelta(days=7)
    prev7_start = now_utc - timedelta(days=14)

    towns = {}
    for (name,) in db.session.query(Incident.town).distinct().all():
        if not name or name.strip().lower() in ("unknown", ""):
            continue
        slug = slugify(name)
        if slug and slug not in towns:
            towns[slug] = {"raw": name, "total": 0, "last7": 0, "prev7": 0,
                           "services": Counter(), "types": Counter(), "hours": Counter()}

    rows = (Incident.query
            .with_entities(Incident.occurred_at, Incident.town, Incident.incident_type, Incident.unit)
            .filter(Incident.occurred_at >= start).all())
    for occurred, name, incident_type, unit in rows:
        t = towns.get(slugify(name or ""))
        if not t:
            continue
        t["total"] += 1
        if occurred >= last7_start:
            t["last7"] += 1
        elif occurred >= prev7_start:
            t["prev7"] += 1
        t["services"][classify_service(incident_type, unit)] += 1
        if incident_type:
            t["types"][pretty_type(incident_type)] += 1
        t["hours"][_to_eastern(occurred).hour] += 1
    return towns


def cached_towns():
    now = time.time()
    if _cache["data"] is None or now - _cache["at"] > CACHE_SECONDS:
        _cache["data"] = build_town_stats()
        _cache["at"] = now
    return _cache["data"]


def indexable_slugs():
    """Towns with enough calls to be worth indexing (used by the sitemap)."""
    return sorted(s for s, t in cached_towns().items() if t["total"] >= MIN_COUNT)


def _hour_label(h):
    return f"{(h % 12) or 12} {'AM' if h < 12 else 'PM'}"


def _visible(counter, limit=None):
    items = [(k, v) for k, v in counter.most_common() if v >= MIN_COUNT]
    return items[:limit] if limit else items


CSS = """
:root{--paper:#FAF8F4;--surface:#fff;--ink:#26302B;--soft:#5A645E;--border:#E4DFD5;--green:#1D6B32}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:'Public Sans',system-ui,sans-serif;line-height:1.55}
a{color:var(--green)}header{background:var(--surface);border-bottom:1px solid var(--border)}
.wrap{max-width:900px;margin:0 auto;padding:0 20px}.top{display:flex;align-items:center;justify-content:space-between;padding:14px 0;gap:16px;flex-wrap:wrap}
.brand{font-family:'Source Serif 4',Georgia,serif;font-weight:700;font-size:22px;color:var(--ink);text-decoration:none}
h1{font-family:'Source Serif 4',Georgia,serif;font-size:32px;margin:26px 0 6px}h2{font-family:'Source Serif 4',Georgia,serif;font-size:21px;margin:26px 0 10px}
.lede{color:var(--soft);max-width:68ch}.crumbs{font-size:14px;color:var(--soft);margin-top:18px}
table{width:100%;border-collapse:collapse;background:var(--surface);border:1px solid var(--border);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:9px 14px;border-bottom:1px solid var(--border)}th{font-size:14px;color:var(--soft);font-weight:600}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}tr:last-child td{border-bottom:0}
.cta{display:inline-block;margin:18px 0 4px;padding:10px 16px;background:var(--green);color:#fff;border-radius:8px;font-weight:600;text-decoration:none}
.note{font-size:14px;color:var(--soft);margin-top:22px}footer{color:var(--soft);font-size:14px;padding:30px 0 40px}
ul.towns{columns:2;column-gap:30px;padding-left:18px}@media(max-width:560px){ul.towns{columns:1}h1{font-size:27px}}
"""


def _page(title, description, path, body, indexable=True):
    robots = "" if indexable else '<meta name="robots" content="noindex,follow">\n'
    url = f"{SITE}{path}"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<meta name="description" content="{escape(description)}">
{robots}<link rel="canonical" href="{url}">
<link rel="icon" href="/favicon.ico" sizes="any"><link rel="icon" type="image/png" sizes="48x48" href="/favicon.png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta property="og:type" content="website"><meta property="og:site_name" content="DelcoSpot">
<meta property="og:title" content="{escape(title)}"><meta property="og:description" content="{escape(description)}">
<meta property="og:url" content="{url}"><meta property="og:image" content="{SITE}/og.png">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{escape(title)}">
<meta name="twitter:description" content="{escape(description)}"><meta name="twitter:image" content="{SITE}/og.png">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;600;700&family=Source+Serif+4:wght@700&display=swap">
<style>{CSS}</style></head><body>
<header><div class="wrap top"><a class="brand" href="/">DelcoSpot</a>
<nav><a href="/">Home</a> &middot; <a href="/town/">Towns</a> &middot; <a href="/stats/">Statistics</a></nav></div></header>
<main class="wrap">{body}</main>
<footer class="wrap">&copy; DelcoSpot &middot; Dispatch data is a public summary and not an official record of any agency.</footer>
</body></html>"""


def _table(headers, rows):
    head = "".join(f'<th class="{"n" if i else ""}">{escape(h)}</th>' for i, h in enumerate(headers))
    body = "".join(
        "<tr>" + "".join(f'<td class="{"n" if i else ""}">{escape(str(c))}</td>' for i, c in enumerate(r)) + "</tr>"
        for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


@towns_bp.get("/town/")
def town_index():
    towns = cached_towns()
    items = "".join(
        f'<li><a href="/town/{escape(slug)}/">{escape(display_name(t["raw"]))}</a></li>'
        for slug, t in sorted(towns.items(), key=lambda kv: display_name(kv[1]["raw"]).lower())
        if t["total"] >= MIN_COUNT)
    body = (f'<h1>Delaware County towns</h1><p class="lede">Fire and EMS dispatch activity for the last '
            f'{WINDOW_DAYS} days, by municipality. Only towns with at least {MIN_COUNT} calls in that period are listed.</p>'
            f'<ul class="towns">{items or "<li>No towns to show yet.</li>"}</ul>')
    resp = Response(_page("Delaware County towns: fire and EMS activity · DelcoSpot",
                          "Fire and EMS dispatch activity for the last 30 days in each Delaware County, PA municipality.",
                          "/town/", body), mimetype="text/html")
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


@towns_bp.get("/town/<slug>/")
def town_page(slug):
    t = cached_towns().get(slug)
    if not t:
        abort(404)
    name = display_name(t["raw"])
    total = t["total"]
    indexable = total >= MIN_COUNT
    board = f"/?town={quote(t['raw'])}#dispatch"

    if indexable:
        change = ""
        if t["prev7"] >= MIN_COUNT:
            pct = round((t["last7"] - t["prev7"]) / t["prev7"] * 100)
            change = (f" That is {abs(pct)}% {'more' if pct > 0 else 'fewer'} than the week before"
                      if pct else " That is about the same as the week before")
            change += "."
        lede = (f"Dispatchers logged {total} fire and EMS calls in {name} over the last {WINDOW_DAYS} days, "
                f"{t['last7']} of them in the last 7 days.{change}")
        parts = [f'<p class="crumbs"><a href="/town/">All towns</a> &rsaquo; {escape(name)}</p>',
                 f"<h1>{escape(name)} fire and EMS activity</h1>", f'<p class="lede">{escape(lede)}</p>',
                 f'<a class="cta" href="{escape(board)}">See live activity in {escape(name)}</a>']
        svc = _visible(t["services"])
        if svc:
            parts += ["<h2>By service</h2>", _table(["Service", "Calls"], svc)]
        hours = _visible(t["hours"])[:3]
        if hours:
            parts += ["<h2>Busiest hours (Eastern)</h2>",
                      _table(["Hour", "Calls"], [(f"{_hour_label(h)} to {_hour_label((h + 1) % 24)}", c) for h, c in hours])]
        types = _visible(t["types"], 8)
        if types:
            parts += ["<h2>Most common call types</h2>", _table(["Call type", "Calls"], types)]
        parts.append(f'<p class="note">Totals only: no addresses, unit numbers or call details are shown, and any '
                     f"group with fewer than {MIN_COUNT} calls is left out. Figures refresh about every 10 minutes "
                     f'and come from the public county dispatch feed. See <a href="/stats/">countywide statistics</a>.</p>')
        description = (f"{total} fire and EMS calls in {name}, PA over the last {WINDOW_DAYS} days: "
                       f"busiest hours, call types and live activity.")
    else:
        parts = [f'<p class="crumbs"><a href="/town/">All towns</a> &rsaquo; {escape(name)}</p>',
                 f"<h1>{escape(name)} fire and EMS activity</h1>",
                 f'<p class="lede">There were fewer than {MIN_COUNT} calls in {escape(name)} in the last '
                 f"{WINDOW_DAYS} days, so no figures are shown.</p>",
                 f'<a class="cta" href="{escape(board)}">See live activity in {escape(name)}</a>']
        description = f"Fire and EMS dispatch activity in {name}, PA."

    resp = Response(_page(f"{name}, PA fire and EMS activity · DelcoSpot", description,
                          f"/town/{slug}/", "".join(parts), indexable=indexable), mimetype="text/html")
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp
