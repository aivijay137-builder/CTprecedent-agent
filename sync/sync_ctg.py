"""Daily data sync for the serving store. Three modes (run as `python -m sync.sync_ctg <mode>`, or from POST /admin/sync):
  bootstrap  first run: stream the full ClinicalTrials.gov download page by page into the flat tables. Resumable.
  daily      fetch studies changed since the watermark (2-day overlap), upsert them, log field-level changes. One transaction:
             it all lands or none of it does (the 5 GB volume has no room for a second copy of the store).
  ids        weekly safety check: fetch every NCT ID and reconcile (fetch missed studies, remove studies the registry dropped).
While a sync holds the file, the app answers "the registry is being updated, try again" (see engine.RegistryBusy)."""
import datetime as dt
import json
import os
import sys
import time

import requests

from . import labels, store

URL = "https://clinicaltrials.gov/api/v2/studies"
OVERLAP_DAYS = 2
PAUSE_S = float(os.environ.get("SYNC_PAUSE_S", "0.5"))
LOCK = store.DATA_DIR / ".sync.lock"


def log(msg):
    print(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def get(params):
    for attempt in range(5):  # exponential backoff on rate limits, server errors and timeouts
        try:
            r = requests.get(URL, params=params, timeout=120)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(str(r.status_code))
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            if attempt == 4:
                raise
            wait = 5 * 3 ** attempt
            log(f"request failed ({e}); retry in {wait}s")
            time.sleep(wait)


def pages(params, token=None):
    """Yield (studies, next_token, total) page by page."""
    while True:
        p = dict(params, pageSize=1000, countTotal="true")
        if token:
            p["pageToken"] = token
        data = get(p)
        token = data.get("nextPageToken")
        yield data.get("studies", []), token, data.get("totalCount")
        if not token:
            return
        time.sleep(PAUSE_S)


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def is_running():
    return LOCK.exists() and _alive(int(LOCK.read_text() or 0))


def _bootstrap(con, run_id):
    token = store.get_state(con, "bootstrap_token")
    if store.get_state(con, "bootstrap_started") is None:
        store.set_state(con, "bootstrap_started", dt.date.today().isoformat())
    n = new = 0
    for studies, token, _ in pages({}, token):
        con.execute("BEGIN")
        a, b, _c = store.apply_studies(con, studies, run_id, log_changes=False)
        store.set_state(con, "bootstrap_token", token)  # saved with the page, so a restart continues from the next page
        con.execute("COMMIT")
        n += a
        new += b
        log(f"bootstrap: {n} studies so far")
    labelled = labels.label_stale(con)
    log(f"labels written: {labelled}")
    store.set_state(con, "watermark", store.get_state(con, "bootstrap_started"))
    store.set_state(con, "bootstrap_token", None)
    return n, new, 0


def _daily(con, run_id):
    wm = store.get_state(con, "watermark")
    if not wm:
        raise RuntimeError("no watermark: run the bootstrap first")
    start = dt.date.fromisoformat(wm) - dt.timedelta(days=OVERLAP_DAYS)
    params = {"filter.advanced": f"AREA[LastUpdatePostDate]RANGE[{start.isoformat()},MAX]"}
    n = new = chg = 0
    total = None
    con.execute("BEGIN")
    try:
        for studies, _t, total in pages(params):
            a, b, c = store.apply_studies(con, studies, run_id)
            n, new, chg = n + a, new + b, chg + c
        if total is not None and n != total:
            raise RuntimeError(f"fetched {n} but the API total is {total}")
        today = dt.date.today()
        if n == 0 and any((start + dt.timedelta(days=k)).weekday() < 5 for k in range((today - start).days)):  # the registry posts on weekdays: a window with one yet no records is suspicious
            raise RuntimeError(f"zero records although the window since {start} includes a weekday")
        labels.label_stale(con)
        store.set_state(con, "watermark", dt.date.today().isoformat())
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return n, new, chg


def _ids(con, run_id):
    live = set()
    for studies, _t, _ in pages({"fields": "NCTId"}):
        live.update(s["protocolSection"]["identificationModule"]["nctId"] for s in studies)
    mine = {r[0] for r in con.execute("SELECT nct_id FROM studies_current").fetchall()}
    missed, removed = sorted(live - mine), sorted(mine - live)
    log(f"ids check: {len(live)} in registry, {len(mine)} here, {len(missed)} missed, {len(removed)} removed")
    n = new = 0
    con.execute("BEGIN")
    try:
        for i in range(0, len(missed), 100):
            for studies, _t, _ in pages({"filter.ids": "|".join(missed[i:i + 100])}):
                a, b, _c = store.apply_studies(con, studies, run_id)
                n, new = n + a, new + b
        if removed:
            con.execute("INSERT INTO study_changes (nct_id, field, change_type, run_folder) SELECT unnest($1::VARCHAR[]), 'study', 'removed', $2", [removed, run_id])
            for t in ["studies_current", "study_labels", *store.flatsql.CHILDREN]:
                con.execute(f"DELETE FROM {t} WHERE nct_id IN (SELECT unnest($1::VARCHAR[]))", [removed])
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return n, new, len(removed)


MODES = {"bootstrap": _bootstrap, "daily": _daily, "ids": _ids}


def run(mode):
    """Run one sync. Returns the sync_runs row as a dict. Never raises: a failure is recorded."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode}")
    store.DATA_DIR.mkdir(parents=True, exist_ok=True)
    if is_running():
        return {"status": "refused", "error": "another sync is running"}
    LOCK.write_text(str(os.getpid()))
    run_id = dt.datetime.now().strftime("%Y-%m-%dT%H%M%S") + "-" + mode
    started = dt.datetime.now()
    con = store.connect()
    store.init(con)
    con.execute("INSERT INTO sync_runs (run_id, mode, started_at, status) VALUES (?, ?, ?, 'running')", [run_id, mode, started])
    status, error, res = "ok", None, (0, 0, 0)
    try:
        res = MODES[mode](con, run_id)
        store.set_state(con, "data_as_of", store.data_as_of(con))
    except Exception as e:  # recorded, shown on /api/health
        status, error = "failed", f"{type(e).__name__}: {e}"
        log("ERROR " + error)
    con.execute("UPDATE sync_runs SET ended_at=?, fetched=?, new_studies=?, changes=?, status=?, error=? WHERE run_id=?",
                [dt.datetime.now(), res[0], res[1], res[2], status, error, run_id])
    con.execute("CHECKPOINT")
    out = dict(zip(["run_id", "mode", "started_at", "ended_at", "fetched", "new_studies", "changes", "status", "error"],
                   con.execute("SELECT * FROM sync_runs WHERE run_id=?", [run_id]).fetchone()))
    con.close()
    LOCK.unlink(missing_ok=True)
    log(f"{mode}: {status} fetched={res[0]} new={res[1]} changes={res[2]} size={store.SERVING_DB.stat().st_size / 1e9:.2f} GB")
    return out


def health(con):
    """Last sync result and a warning when it failed or no good run happened for 2 days. Used by /api/health."""
    r = con.execute("SELECT run_id, mode, ended_at, status, error FROM sync_runs ORDER BY started_at DESC LIMIT 1").fetchone()
    ok = con.execute("SELECT max(ended_at) FROM sync_runs WHERE status='ok' AND mode IN ('daily','bootstrap')").fetchone()[0]
    warn = None
    if r and r[3] == "failed":
        warn = f"Last sync failed: {r[4]}"
    elif ok is None or (dt.datetime.now() - ok).days >= 2 and dt.date.today().weekday() < 5:
        warn = "No successful sync in the last 2 days"
    return {"last_sync": {"run_id": r[0], "mode": r[1], "ended_at": str(r[2]), "status": r[3]} if r else None, "sync_warning": warn}


if __name__ == "__main__":
    out = run(sys.argv[1] if len(sys.argv) > 1 else "daily")
    sys.exit(0 if out["status"] == "ok" else 1)
