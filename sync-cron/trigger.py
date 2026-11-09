"""Railway cron service: calls the api's sync endpoint and nothing else. Env: API_URL (e.g. https://<api>.up.railway.app), SYNC_SECRET, SYNC_MODE (daily|ids)."""
import os
import sys
import urllib.request

req = urllib.request.Request(f"{os.environ['API_URL'].rstrip('/')}/admin/sync?mode={os.environ.get('SYNC_MODE', 'daily')}",
                             method="POST", headers={"X-Sync-Secret": os.environ["SYNC_SECRET"]})
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        print(r.status, r.read().decode())
except urllib.error.HTTPError as e:  # 409 = a sync is already running; anything else fails the cron run so Railway shows it
    print(e.code, e.read().decode())
    sys.exit(0 if e.code == 409 else 1)
