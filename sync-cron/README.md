# sync-cron (Railway)
One cron service, `sync-cron`, runs `trigger.py` daily at 02:00 UTC. It calls the api's `/admin/sync`: `daily` on most days, `ids` (weekly full ID check) on Sundays.
Env: `API_URL`, `SYNC_SECRET` (same value as the api service). Deploy from this folder: `railway up --service sync-cron`.
First deploy only: run the api's bootstrap once with `curl -X POST "<api>/admin/sync?mode=bootstrap" -H "X-Sync-Secret: ..."` (resumable).
Schedule: set to `0 2 * * *` (UTC) on the service. It must be set in Railway (Settings > Cron Schedule) as well as in `railway.json`; if the service shows no schedule it never runs on its own. Deploy it from this folder (`railway up sync-cron --path-as-root --service sync-cron`), not from the repo root: the root `railway.json` belongs to the api. The api itself deploys from GitHub (`main`); this service does not need a redeploy for data to refresh.
