"""
Sports scores for the News page ticker.

There's no free/public API from nfl.com, nba.com, nhl.com or mlb.com
themselves. Instead this uses ESPN's scoreboard endpoint -- the same
undocumented-but-public, unauthenticated, no-signup-required JSON API
that powers espn.com's own live scoreboards (found the same way the
Delco dispatch feed was: inspecting what the site's own frontend calls).
Since it's undocumented, ESPN could change or remove it without notice;
if the ticker ever goes empty, that's the first thing to check.

Results are cached in memory for CACHE_SECONDS so a page full of
visitors doesn't trigger a fresh outbound request per visitor.
"""
import time

import requests

from flask import Blueprint, jsonify

sports_bp = Blueprint("sports", __name__, url_prefix="/api")

REQUEST_TIMEOUT_SECONDS = 8
CACHE_SECONDS = 120

LEAGUES = [
    ("NFL", "football", "nfl"),
    ("NBA", "basketball", "nba"),
    ("NHL", "hockey", "nhl"),
    ("MLB", "baseball", "mlb"),
]

_cache = {"at": 0, "games": []}


def _fetch_league(label, sport, league):
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard"
    games = []
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return games

    for event in data.get("events", []):
        try:
            competition = event["competitions"][0]
            competitors = competition["competitors"]
            home = next(c for c in competitors if c.get("homeAway") == "home")
            away = next(c for c in competitors if c.get("homeAway") == "away")
            status = event.get("status", {}).get("type", {})
            games.append({
                "league": label,
                "home": home["team"]["abbreviation"],
                "away": away["team"]["abbreviation"],
                "home_score": home.get("score"),
                "away_score": away.get("score"),
                # e.g. "Final", "In Progress", "Scheduled"
                "state": status.get("shortDetail") or status.get("description") or "",
                "completed": bool(status.get("completed")),
                "in_progress": status.get("state") == "in",
            })
        except (KeyError, IndexError, StopIteration):
            continue

    return games


def get_scores():
    now = time.time()
    if now - _cache["at"] < CACHE_SECONDS:
        return _cache["games"]

    games = []
    for label, sport, league in LEAGUES:
        games.extend(_fetch_league(label, sport, league))

    _cache["at"] = now
    _cache["games"] = games
    return games


@sports_bp.get("/scores")
def scores():
    return jsonify({"games": get_scores()}), 200
