"""
Travel board: SEPTA service status for the lines that serve Delaware County,
plus active PennDOT (511PA) road events in the county.

Routes:
  GET /api/travel   JSON for the home-page card
  GET /travel/      server-rendered page (crawlable)

Sources
  SEPTA  - public alerts API, no key:
             https://www3.septa.org/api/Alerts/index.php        (all routes, flags only)
             https://www3.septa.org/api/Alerts/get_alert_data.php?route_id=X  (messages)
  PennDOT - RCRS liveEvents, HTTP Basic auth. Credentials come from PennDOT
            after the Data Feed Request Form. Set PENNDOT_RCRS_USER and
            PENNDOT_RCRS_PASS in Render (never in the repo). Until they are
            set, the roads section says "coming soon" and links to 511PA.

Both feeds are cached for CACHE_SECONDS, so visitors never hit SEPTA or
PennDOT directly. If a refresh fails, the last good copy is served with its
original timestamp; with no good copy, that section reports "unavailable"
rather than pretending service is normal.
"""
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import escape, unescape

import requests
from flask import Blueprint, Response, jsonify

travel_bp = Blueprint("travel", __name__)

CACHE_SECONDS = int(os.environ.get("TRAVEL_CACHE_SECONDS", "300"))
TIMEOUT = 8
UA = {"User-Agent": "DelcoSpot travel board (https://www.delcospot.com)"}

SEPTA_INDEX = "https://www3.septa.org/api/Alerts/index.php"
SEPTA_DETAIL = "https://www3.septa.org/api/Alerts/get_alert_data.php"
RCRS_URL = os.environ.get("PENNDOT_RCRS_URL", "https://eventsdata.dot.pa.gov/liveEvents")
DELAWARE_COUNTY_CODE = "23"  # PennDOT county codes are alphabetical; Delaware is 23

# Lines serving Delaware County. `ids` are candidate SEPTA route IDs, tried in
# order (SEPTA renamed trolleys under "SEPTA Metro", e.g. 101 -> D1); `names`
# are fallbacks matched against route_name. A line SEPTA's feed doesn't list
# shows "Not in SEPTA's feed" -- check it there before assuming it's gone.
LINES = [
    {"key": "med", "name": "Media/Wawa line", "kind": "rail",
     "ids": ["rr_route_med"], "names": ["media"]},
    {"key": "wil", "name": "Wilmington/Newark line", "kind": "rail",
     "ids": ["rr_route_wil"], "names": ["wilmington"]},
    {"key": "air", "name": "Airport line", "kind": "rail",
     "ids": ["rr_route_air"], "names": ["airport"]},
    {"key": "pao", "name": "Paoli/Thorndale line", "kind": "rail",
     "ids": ["rr_route_pao"], "names": ["paoli"]},
    {"key": "101", "name": "101 trolley (D1)", "kind": "trolley",
     "ids": ["trolley_route_101", "trolley_route_d1", "bus_route_101"], "names": ["101", "d1"]},
    {"key": "102", "name": "102 trolley (D2)", "kind": "trolley",
     "ids": ["trolley_route_102", "trolley_route_d2", "bus_route_102"], "names": ["102", "d2"]},
    {"key": "nhsl", "name": "Norristown High Speed Line (M)", "kind": "trolley",
     "ids": ["rr_route_nhsl", "trolley_route_nhsl", "bus_route_nhsl", "trolley_route_m",
             "trolley_route_100", "bus_route_100"], "names": ["norristown high", "nhsl"]},
]

_cache = {"septa": None, "septa_at": 0.0, "roads": None, "roads_at": 0.0}
_lock = threading.Lock()


# ---------- helpers ----------

def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z") if dt else None


def _yes(v):
    return str(v).strip().lower() in ("y", "yes", "true", "t", "1")


def _clean(text, limit=280):
    """SEPTA messages are HTML fragments; reduce to one line of plain text."""
    if not text:
        return ""
    t = re.sub(r"<(script|style)\b.*?</\1\s*>", " ", str(text), flags=re.I | re.S)
    t = re.sub(r"<br\s*/?>|</p>|</li>", " ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"\s+", " ", unescape(t)).strip()
    return t if len(t) <= limit else t[: limit - 1].rsplit(" ", 1)[0] + "…"


def _when(text):
    """PennDOT times are local 'YYYY-MM-DD HH:MM[:SS]'; show '6:10 AM' or 'Nov 18, 6:10 AM'."""
    try:
        dt = datetime.strptime(str(text).strip()[:16], "%Y-%m-%d %H:%M")
    except ValueError:
        return str(text or "")
    from stats import EASTERN
    today = datetime.now(EASTERN).date()
    clock = dt.strftime("%I:%M %p").lstrip("0")
    return clock if dt.date() == today else f"{dt.strftime('%b')} {dt.day}, {clock}"


def _get_json(url, **kw):
    r = requests.get(url, headers=UA, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r.json()


# ---------- SEPTA ----------

def _resolve(line, routes):
    by_id = {str(r.get("route_id", "")).lower(): r for r in routes}
    for cid in line["ids"]:
        if cid in by_id:
            return by_id[cid]
    for r in routes:
        rn = str(r.get("route_name", "")).lower()
        if any(n == rn or (len(n) > 3 and n in rn) for n in line["names"]):
            return r
    return None


NOTICE_LABELS = {"alert": "Alert", "detour": "Detour", "advisory": "Advisory"}
_SEVERITY = ["alert", "detour", "advisory"]  # worst first


def _notices_from_detail(rows):
    """All notices (alerts, detours, advisories) for a route, worst first, duplicates removed.
    Mirrors SEPTA's own 'All Notices' view rather than showing alerts only."""
    found, seen, snow = [], set(), False
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        for field, kind in (("current_message", "alert"), ("detour_message", "detour"),
                            ("advisory_message", "advisory")):
            text = _clean(r.get(field), 600)
            if text and (kind, text) not in seen:
                seen.add((kind, text))
                found.append({"type": kind, "label": NOTICE_LABELS[kind], "text": text})
        snow = snow or _yes(r.get("isSnow"))
    if snow and not any(n["type"] == "advisory" for n in found):
        found.append({"type": "advisory", "label": "Advisory", "text": "Snow schedule in effect."})
    found.sort(key=lambda n: _SEVERITY.index(n["type"]))
    return found


def _line_status(notices):
    """(state, pill label) from the worst notice on the line."""
    if not notices:
        return "ok", "Normal service"
    worst = notices[0]["type"]
    return worst, {"alert": "Service alert", "detour": "Detour", "advisory": "Advisory"}[worst]


def fetch_septa():
    routes = _get_json(SEPTA_INDEX)
    if isinstance(routes, dict):
        routes = routes.get("alerts") or routes.get("routes") or list(routes.values())
    if not isinstance(routes, list) or not routes:
        raise ValueError("SEPTA alerts index returned no routes")

    resolved = [(line, _resolve(line, routes)) for line in LINES]

    def detail(pair):
        line, row = pair
        base = {"key": line["key"], "name": line["name"], "kind": line["kind"]}
        if row is None:
            return {**base, "state": "unknown", "label": "Not in SEPTA's feed", "message": "", "notices": []}
        flagged = any(_yes(row.get(k)) for k in ("isalert", "isadvisory", "isdetour", "issuppend", "isSnow"))
        notices = []
        if flagged:
            try:
                rows = _get_json(SEPTA_DETAIL, params={"route_id": row.get("route_id")})
                notices = _notices_from_detail(rows if isinstance(rows, list) else [rows])
                if not notices:  # flagged, but no text came back
                    notices = [{"type": "advisory", "label": "Advisory",
                                "text": "SEPTA has posted a notice. See SEPTA for details."}]
            except Exception:
                notices = [{"type": "advisory", "label": "Advisory",
                            "text": "Details unavailable. Check SEPTA."}]
        state, label = _line_status(notices)
        return {**base, "state": state, "label": label,
                "message": notices[0]["text"] if notices else "", "notices": notices}

    with ThreadPoolExecutor(max_workers=len(LINES)) as pool:
        return list(pool.map(detail, resolved))


# ---------- PennDOT / 511PA ----------

def _rcrs_creds():
    user, pw = os.environ.get("PENNDOT_RCRS_USER"), os.environ.get("PENNDOT_RCRS_PASS")
    return (user, pw) if user and pw else None


def _in_delco(ev):
    names = {str(ev.get(k, "")).strip().upper() for k in
             ("CountyName", "CountyIncName", "CountyFromName", "CountyToName")}
    codes = {str(ev.get(k, "")).strip().lstrip("0") for k in ("County", "CountyInc", "CountyFrom", "CountyTo")}
    return "DELAWARE" in names or DELAWARE_COUNTY_CODE in codes


def _road_item(ev):
    road = (ev.get("Facility") or "").strip()
    direction = (ev.get("Direction") or "").strip()
    where = ev.get("IncidentLoc") or ev.get("FromLoc") or ""
    town = (ev.get("IncidentMuniName") or "").strip().title()
    if town:
        from towns import display_name
        town = display_name(town)
    title = " ".join(x for x in (road, direction) if x)
    if where:
        title += f" at {str(where).strip()}" if title else str(where).strip()
    if town:
        title += f", {town}"
    kind = (ev.get("EventType") or "").strip().lower()
    detail = _clean(ev.get("Description"), 220)
    lanes = (ev.get("LaneStatus") or "").strip()
    lanes = lanes[:1].upper() + lanes[1:]
    sev = "alert" if (_yes(ev.get("IsFatality")) or "closed" in lanes.lower()
                      or kind in ("crash", "accident", "disabled vehicle", "fire")) else "advisory"
    return {"id": ev.get("EventID"), "title": title or "Road event", "type": kind.capitalize() or "Event",
            "lanes": lanes, "detail": detail, "detour": _yes(ev.get("DetourInEffect")),
            "since": _when(ev.get("DateTimeEventOccurs") or ev.get("CreateTime") or ""),
            "updated": ev.get("LastUpdate") or "", "state": sev,
            "_sort": str(ev.get("DateTimeEventOccurs") or ev.get("CreateTime") or ""),
            "reopened": bool(ev.get("ActualDateTimeOpened"))}


def fetch_roads():
    creds = _rcrs_creds()
    if not creds:
        return None
    data = _get_json(RCRS_URL, auth=creds)
    events = data.get("Values", []) if isinstance(data, dict) else data
    items = [_road_item(ev) for ev in (events or []) if isinstance(ev, dict) and _in_delco(ev)]
    items = [i for i in items if not i["reopened"]]
    items.sort(key=lambda i: (i["state"] != "alert", i["_sort"]))
    for i in items:
        i.pop("_sort", None)
    return items


# ---------- cache ----------

def _refresh(name, fn):
    now = time.time()
    if _cache[name] is not None and now - _cache[f"{name}_at"] < CACHE_SECONDS:
        return
    try:
        _cache[name] = {"items": fn(), "at": _now(), "error": None}
    except Exception as exc:  # keep the last good copy, note the failure
        prev = _cache[name] or {"items": None, "at": None}
        _cache[name] = {"items": prev["items"], "at": prev["at"], "error": type(exc).__name__}
    _cache[f"{name}_at"] = now


def board():
    with _lock:
        _refresh("septa", fetch_septa)
        if _rcrs_creds():
            _refresh("roads", fetch_roads)
    s, r = _cache["septa"] or {}, _cache["roads"] or {}
    septa = {"lines": s.get("items"), "updated_at": _iso(s.get("at")),
             "state": "ok" if s.get("items") is not None and not s.get("error")
             else ("stale" if s.get("items") is not None else "unavailable")}
    if not _rcrs_creds():
        roads = {"events": None, "updated_at": None, "state": "not_configured"}
    else:
        roads = {"events": r.get("items"), "updated_at": _iso(r.get("at")),
                 "state": "ok" if r.get("items") is not None and not r.get("error")
                 else ("stale" if r.get("items") is not None else "unavailable")}
    return {"septa": septa, "roads": roads}


def health():
    """Small summary for /api/health. Never raises."""
    try:
        s, r = _cache["septa"] or {}, _cache["roads"] or {}
        return {"septa_updated_at": _iso(s.get("at")), "septa_error": s.get("error"),
                "roads_configured": bool(_rcrs_creds()),
                "roads_updated_at": _iso(r.get("at")), "roads_error": r.get("error")}
    except Exception:
        return {"state": "unknown"}


# ---------- routes ----------

@travel_bp.get("/api/travel")
def api_travel():
    resp = jsonify(board())
    resp.headers["Cache-Control"] = "public, max-age=60"
    return resp


def _eastern(iso):
    if not iso:
        return ""
    from stats import EASTERN
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(EASTERN)
    return dt.strftime("%I:%M %p").lstrip("0")


EXT = 'target="_blank" rel="noopener noreferrer"'
SITE = "https://www.delcospot.com"
SEPTA_ALERTS = "https://www.septa.org/alerts/"
PA511 = "https://www.511pa.com"

PAGE_CSS = """
.board{background:#fff;border:1px solid var(--border);border-radius:10px;overflow:hidden;margin-bottom:8px}
.row{display:flex;gap:12px;align-items:flex-start;padding:11px 14px;border-bottom:1px solid var(--border)}
.row:last-child{border-bottom:0}.row .what{flex:1}.row .msg{font-size:14px;color:var(--soft);margin:3px 0 0}
.pill{font-size:13px;padding:2px 10px;border-radius:999px;white-space:nowrap;font-weight:600}
.ok{background:#E3F1E6;color:#14432A}.advisory,.detour{background:#FBF0DC;color:#6B4A0C}
.alert{background:#FBE4E1;color:#8A1F14}.unknown{background:#EEECE7;color:#5A645E}
.kind{font-size:12px;color:var(--soft);text-transform:uppercase;letter-spacing:.04em}
.ntype{display:inline-block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;padding:0 7px;border-radius:4px;margin-right:4px}
.ntype.alert{background:#FBE4E1;color:#8A1F14}.ntype.detour{background:#FBF0DC;color:#6B4A0C}.ntype.advisory{background:#E8ECF2;color:#2A3B52}
.stamp{font-size:14px;color:var(--soft);margin:0 0 10px}
"""


def _jsonld(updated_iso):
    import json
    graph = [
        {"@type": "WebPage", "@id": f"{SITE}/travel/#webpage", "url": f"{SITE}/travel/",
         "name": "Delaware County travel: SEPTA status and road incidents",
         "description": "SEPTA service status for Delaware County rail lines and trolleys, plus active road incidents and roadwork.",
         "inLanguage": "en-US", "isPartOf": {"@type": "WebSite", "name": "DelcoSpot", "url": SITE + "/"},
         "about": {"@type": "AdministrativeArea", "name": "Delaware County, Pennsylvania"},
         **({"dateModified": updated_iso} if updated_iso else {})},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "DelcoSpot", "item": SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": "Travel", "item": f"{SITE}/travel/"}]},
    ]
    blob = json.dumps({"@context": "https://schema.org", "@graph": graph}).replace("</", "<\\/")
    return f'<script type="application/ld+json">{blob}</script>\n'


def _render_page(data):
    from towns import _page  # same shell and styles as the town pages
    s, r = data["septa"], data["roads"]
    parts = ['<p class="crumbs"><a href="/">DelcoSpot</a> &rsaquo; Travel</p>',
             '<h1>Delaware County travel: SEPTA status and road incidents</h1>',
             '<p class="lede">All current SEPTA notices (alerts, advisories and detours) for the Media/Wawa, Wilmington/Newark, Airport and '
             'Paoli/Thorndale Regional Rail lines, the 101 and 102 trolleys and the Norristown High Speed Line, '
             'plus active road incidents and roadwork in Delaware County, Pennsylvania. '
             'Refreshed about every 5 minutes.</p>',
             "<h2>SEPTA service notices</h2>"]
    if s["lines"] is None:
        parts.append(f'<p class="stamp">SEPTA status is unavailable right now. '
                     f'<a href="{SEPTA_ALERTS}" {EXT}>Check SEPTA alerts</a>.</p>')
    else:
        stale = " (SEPTA didn't respond to the last check)" if s["state"] == "stale" else ""
        parts.append(f'<p class="stamp">Updated {escape(_eastern(s["updated_at"]))}{stale}</p><div class="board">')
        for ln in s["lines"]:
            msg = "".join(f'<p class="msg"><span class="ntype {escape(n["type"])}">{escape(n["label"])}</span> '
                          f'{escape(n["text"])}</p>' for n in ln.get("notices", []))
            parts.append(f'<div class="row"><div class="what"><span class="kind">{escape(ln["kind"])}</span><br>'
                         f'{escape(ln["name"])}{msg}</div><span class="pill {escape(ln["state"])}">'
                         f'{escape(ln["label"])}</span></div>')
        parts.append("</div>")

    parts.append("<h2>Delaware County road incidents</h2>")
    if r["state"] == "not_configured":
        parts.append(f'<p class="stamp">Road incidents are coming soon. For now, see '
                     f'<a href="{PA511}" {EXT}>511PA</a>.</p>')
    elif r["events"] is None:
        parts.append(f'<p class="stamp">Road information is unavailable right now. '
                     f'<a href="{PA511}" {EXT}>Check 511PA</a>.</p>')
    else:
        stale = " (511PA didn't respond to the last check)" if r["state"] == "stale" else ""
        parts.append(f'<p class="stamp">Updated {escape(_eastern(r["updated_at"]))}{stale}</p>')
        if not r["events"]:
            parts.append('<p>No active road incidents or roadwork reported in Delaware County.</p>')
        else:
            parts.append('<div class="board">')
            for ev in r["events"][:40]:
                bits = [b for b in (ev["type"], ev["lanes"], "Detour in effect" if ev["detour"] else "",
                                    f'since {ev["since"]}' if ev["since"] else "") if b]
                detail = f'<p class="msg">{escape(ev["detail"])}</p>' if ev["detail"] else ""
                parts.append(f'<div class="row"><div class="what">{escape(ev["title"])}'
                             f'<p class="msg">{escape(" · ".join(bits))}</p>{detail}</div></div>')
            parts.append("</div>")

    parts.append(f'<p class="note">Sources: SEPTA and PennDOT 511PA. Information can lag real conditions; '
                 f'check <a href="{SEPTA_ALERTS}" {EXT}>SEPTA</a> or '
                 f'<a href="{PA511}" {EXT}>511PA</a> before you travel. '
                 f'See also <a href="/town/">fire and EMS activity by town</a> and '
                 f'<a href="/stats/">countywide statistics</a>.</p>')
    html = _page("Delco travel: SEPTA status and road incidents · DelcoSpot",
                 "SEPTA alerts, advisories and detours for Delaware County rail lines and trolleys, "
                 "plus road incidents and roadwork in the county.",
                 "/travel/", "".join(parts), current="/travel/",
                 extra_head=_jsonld(s["updated_at"] if s["lines"] is not None else None))
    return html.replace("</style>", PAGE_CSS + "</style>", 1)


@travel_bp.get("/travel/")
def travel_page():
    resp = Response(_render_page(board()), mimetype="text/html")
    resp.headers["Cache-Control"] = "public, max-age=120"
    return resp
