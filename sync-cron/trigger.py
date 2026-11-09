"""Railway cron service: calls the api's sync endpoint and nothing else.
Env: API_URL (e.g. https://<api>.up.railway.app), SYNC_SECRET, SYNC_MODE = daily | ids | bootstrap | auto (default: ids on Sundays, daily otherwise)."""
import datetime as dt
import os
import sys
import urllib.error
import urllib.request

mode = os.environ.get("SYNC_MODE", "auto")
if mode == "auto":
    mode = "ids" if dt.datetime.now(dt.timezone.utc).weekday() == 6 else "daily"  # the weekly ID check replaces Sunday's daily run; Monday's 2-day overlap covers it
req = urllib.request.Request(f"{os.environ['API_URL'].rstrip('/')}/admin/sync?mode={mode}", method="POST", headers={"X-Sync-Secret": os.environ["SYNC_SECRET"]})
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        print(mode, r.status, r.read().decode())
except urllib.error.HTTPError as e:  # 409 = a sync is already running; anything else fails the cron run so Railway shows it
    print(mode, e.code, e.read().decode())
    sys.exit(0 if e.code == 409 else 1)
