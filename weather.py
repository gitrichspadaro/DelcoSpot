"""
Live weather for the header badge and the "More Delco resources" weather
link.

weather.com (The Weather Company/IBM) has no public, free, third-party API
-- same situation as Zillow/Redfin/Realtor.com elsewhere in this app, where
a named source turned out not to be usable and a real substitute was used
instead. This uses the National Weather Service API (api.weather.gov)
instead: free, no API key, official US government data, and it covers
Media, PA directly. The weather.com link itself is kept as the click-through
target since that's just a normal outbound link, not data reuse.

NWS requires every request to send a real User-Agent identifying the
application (they rate-limit/block the default urllib/requests UA), so this
is fetched server-side rather than directly from the browser -- browsers
don't let JS set a custom User-Agent anyway.

Responses are cached in memory for a few minutes so a burst of page loads
doesn't hammer api.weather.gov; "update every time user opens or refreshes
the page" is satisfied from the frontend's point of view (it always makes
a fresh request), the cache just avoids redundant upstream calls.
"""
import time

import requests
from flask import Blueprint, jsonify

weather_bp = Blueprint("weather", __name__, url_prefix="/api")

# Media, PA (county seat of Delaware County).
_LAT, _LON = 39.9168, -75.3880

_HEADERS = {
    "User-Agent": "DelcoSpot (https://delcospot.com, contact: support@delcospot.com)",
    "Accept": "application/geo+json",
}

_CACHE_TTL_SECONDS = 600  # 10 minutes
_cache = {"data": None, "fetched_at": 0}


def _c_to_f(celsius):
    return round((celsius * 9 / 5) + 32)


def _fetch_from_nws():
    # Step 1: resolve the lat/lon to the nearest observation stations.
    points_resp = requests.get(
        f"https://api.weather.gov/points/{_LAT},{_LON}",
        headers=_HEADERS, timeout=8,
    )
    points_resp.raise_for_status()
    stations_url = points_resp.json()["properties"]["observationStations"]

    stations_resp = requests.get(stations_url, headers=_HEADERS, timeout=8)
    stations_resp.raise_for_status()
    stations = stations_resp.json()["features"]
    if not stations:
        raise RuntimeError("No observation stations returned for this point.")
    station_id = stations[0]["properties"]["stationIdentifier"]

    # Step 2: pull that station's latest observation.
    obs_resp = requests.get(
        f"https://api.weather.gov/stations/{station_id}/observations/latest",
        headers=_HEADERS, timeout=8,
    )
    obs_resp.raise_for_status()
    props = obs_resp.json()["properties"]

    temp_c = props.get("temperature", {}).get("value")
    condition = props.get("textDescription") or "Unknown"

    return {
        "temp_f": _c_to_f(temp_c) if temp_c is not None else None,
        "condition": condition,
        "location": "Media, PA",
    }


@weather_bp.get("/weather")
def get_weather():
    now = time.time()
    if _cache["data"] and (now - _cache["fetched_at"]) < _CACHE_TTL_SECONDS:
        return jsonify(_cache["data"]), 200

    try:
        data = _fetch_from_nws()
        _cache["data"] = data
        _cache["fetched_at"] = now
        return jsonify(data), 200
    except Exception:
        # If NWS is unreachable or returns something unexpected, serve the
        # last good reading if we have one rather than breaking the page.
        if _cache["data"]:
            return jsonify(_cache["data"]), 200
        return jsonify({"temp_f": None, "condition": "Unavailable", "location": "Media, PA"}), 200
