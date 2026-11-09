# sync-cron (Railway)
Two cron services from this folder, same code, different env:
- daily  : schedule `0 2 * * *`  (02:00 UTC), `SYNC_MODE=daily`
- weekly : schedule `0 3 * * 0`  (Sunday 03:00 UTC), `SYNC_MODE=ids`
Both need `API_URL` and the same `SYNC_SECRET` as the api service. Start command: `python trigger.py`.
First deploy only: run once by hand with `SYNC_MODE=bootstrap` (loads all ~610k studies; resumable if interrupted).
