"""7-day Broadcastify Calls volume test. Standard library only.

Pulls the previous 7 days of archived calls for each talkgroup in 8-hour windows,
stops at 15 minutes ago (archives are not guaranteed until then), removes
duplicates by (groupId, ts), and reports counts and airtime.

Run from the folder that contains broadcastify_auth.py, in the Render shell:
  python3 calls_volume_test.py 13264-224

Unit IDs ("src") are dropped before anything is saved to disk.
"""
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone

import broadcastify_auth as bcfy

DAYS = 7
LAG_SECONDS = 15 * 60          # archives are not guaranteed until 15 minutes after receipt
PAUSE_SECONDS = 0.3            # stay well under the 5 requests/second limit

# Use New York time when the system has timezone data (Render does). Windows Python often
# doesn't, so fall back to a fixed UTC-5 offset. That's off by one hour before 1 Nov (DST), which
# only moves a few calls across midnight in the per-day counts.
try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("America/New_York")
    TZ_LABEL = "America/New_York"
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=-5))
    TZ_LABEL = "fixed UTC-5"


def fetch(group_id, start, end):
    """Return (status, body). body is parsed JSON on success, short text on error."""
    url = bcfy.group_archive_url(group_id, start, end)
    req = urllib.request.Request(url, headers=bcfy.auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", "replace")[:300]


def windows_for_test(now):
    """8-hour windows covering the last DAYS days, ending LAG_SECONDS ago, newest first."""
    end_all = now - LAG_SECONDS
    start_all = end_all - DAYS * 24 * 3600
    windows, end = [], end_all
    while end > start_all:
        start = max(start_all, end - bcfy.MAX_ARCHIVE_WINDOW_SECONDS)
        windows.append((start, end))
        end = start
    return windows


def run_group(group_id, windows):
    calls = {}
    requests = 0
    failures = []
    for start, end in windows:
        status, body = fetch(group_id, start, end)
        requests += 1
        if status == 200:
            for call in body.get("calls", []):
                calls[(call["groupId"], call["ts"])] = call
        else:
            failures.append({"start": start, "status": status, "body": body})
            # If the very first request is rejected, the cause is auth or access.
            # Stop now so the test doesn't spend more reads.
            if requests == 1:
                break
        time.sleep(PAUSE_SECONDS)
    return calls, requests, failures


def summarize(group_id, calls, requests, failures, windows):
    print(f"\n=== {group_id} ===")
    print(f"windows requested: {requests} of {len(windows)}")
    print(f"failed windows:    {len(failures)}")
    if failures:
        print(f"first failure:     HTTP {failures[0]['status']} {str(failures[0]['body'])[:200]}")
    if not calls:
        print("unique calls:      0")
        return
    durations = [c.get("duration", 0) for c in calls.values()]
    total_seconds = sum(durations)
    per_day = Counter(
        datetime.fromtimestamp(c["ts"], LOCAL_TZ).strftime("%a %m/%d")
        for c in calls.values()
    )
    print(f"unique calls:      {len(calls)}")
    print(f"total airtime:     {total_seconds} s ({total_seconds / 60:.1f} min)")
    print(f"average duration:  {total_seconds / len(calls):.1f} s")
    print(f"calls per day ({TZ_LABEL}):")
    for day in sorted(per_day, key=lambda d: datetime.strptime(d, "%a %m/%d").replace(year=2026)):
        print(f"  {day}: {per_day[day]}")

    # Save without unit IDs
    safe = [{k: v for k, v in c.items() if k != "src"} for c in calls.values()]
    out = f"/tmp/calls_{group_id}_{int(time.time())}.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(sorted(safe, key=lambda c: c["ts"]), fh, indent=1)
    print(f"saved (no unit IDs): {out}")


def main():
    groups = sys.argv[1:] or ["13264-224"]
    now = int(time.time())
    windows = windows_for_test(now)
    print(f"Test window: {DAYS} days, {len(windows)} requests per talkgroup, "
          f"ending {datetime.fromtimestamp(now - LAG_SECONDS, LOCAL_TZ)}")
    for group_id in groups:
        calls, requests, failures = run_group(group_id, windows)
        summarize(group_id, calls, requests, failures, windows)


if __name__ == "__main__":
    main()
