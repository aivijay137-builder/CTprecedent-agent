# sync-cron (Railway)
One cron service, `sync-cron`, runs `trigger.py` daily at 02:00 UTC. It calls the api's `/admin/sync`: `daily` on most days, `ids` (weekly full ID check) on Sundays.
Env: `API_URL`, `SYNC_SECRET` (same value as the api service). Deploy from this folder: `railway up --service sync-cron`.
First deploy only: run the api's bootstrap once with `curl -X POST "<api>/admin/sync?mode=bootstrap" -H "X-Sync-Secret: ..."` (resumable).
