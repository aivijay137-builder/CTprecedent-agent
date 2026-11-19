"""Task-level numbers from app.db (runs + decisions). Read-only.  python -m backend.metrics
Counts every run in the database, so on a dev machine it includes test runs: label the source when you quote it."""
import json
import sqlite3
from datetime import datetime
from statistics import median

from . import appdb


def compute(db=None, since: str = "") -> dict:  # since: ISO date; runs before it are ignored (e.g. old prototype formats)
    c = sqlite3.connect(str(db or appdb.DB))
    runs = {r[0]: (r[1], json.loads(r[2])) for r in c.execute("SELECT run_id, created_at, result FROM runs WHERE created_at >= ?", (since,))}
    dec = c.execute("SELECT ts, run_id, action FROM decisions WHERE kind='flag' AND action != 'undo' ORDER BY ts").fetchall()
    dec = [d for d in dec if d[1] in runs]
    first = {}
    for ts, rid, _ in dec:
        first.setdefault(rid, ts)
    mins = [(datetime.fromisoformat(ts) - datetime.fromisoformat(runs[rid][0])).total_seconds() / 60 for rid, ts in first.items() if rid in runs]
    n = len(runs)
    flagged = [r for _, r in runs.values() if r["flags"]]
    acts = [a for _, _, a in dec]
    return {"runs": n,
            "insufficient_share": round(sum(r["bottom_line"]["risk"] == "insufficient" for _, r in runs.values()) / n, 3) if n else None,
            "runs_with_flags": len(flagged),
            "flags_with_n_and_ids": f"{sum(bool(f.get('evidence_ids')) and bool(f.get('n')) for r in flagged for f in r['flags'])} of {sum(len(r['flags']) for r in flagged)}",
            "decisions": len(acts), "accepted_or_kept_share": round(sum(a in ('accept', 'keep') for a in acts) / len(acts), 3) if acts else None,
            "deferred_share": round(acts.count('defer') / len(acts), 3) if acts else None,
            "median_minutes_run_to_first_decision": round(median(mins), 1) if mins else None,
            "runs_with_own_ai_key": sum(bool((r.get("ai_usage") or {}).get("own_key")) for _, r in runs.values())}


if __name__ == "__main__":
    import sys
    for k, v in compute(since=sys.argv[1] if len(sys.argv) > 1 else "").items():
        print(f"{k:40} {v}")
