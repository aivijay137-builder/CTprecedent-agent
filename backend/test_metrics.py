"""metrics.compute on a tiny app.db. Run: python -m pytest backend/test_metrics.py -q"""
import json

from backend import appdb, metrics


def _run(rid, ts, risk, flags):
    import sqlite3
    c = sqlite3.connect(str(appdb.DB))
    c.execute("INSERT INTO runs VALUES(?,?,?,?)", (rid, None, ts, json.dumps({"bottom_line": {"risk": risk}, "flags": flags, "ai_usage": {"own_key": False}})))
    c.commit()


def test_counts_and_since(tmp_path, monkeypatch):
    monkeypatch.setattr(appdb, "DB", tmp_path / "t.db")
    appdb.init()
    good = {"evidence_ids": ["NCT1"], "n": 1}
    _run("old", "2026-11-01T00:00:00+00:00", "low", [{"evidence_ids": [], "n": None}])          # old format: excluded by since
    _run("a", "2026-11-10T10:00:00+00:00", "low", [good])
    _run("b", "2026-11-10T11:00:00+00:00", "insufficient", [])
    appdb.log("lead", "flag", "accept", run_id="a", flag_id="x")
    m = metrics.compute(since="2026-11-09")
    assert m["runs"] == 2 and m["insufficient_share"] == 0.5 and m["flags_with_n_and_ids"] == "1 of 1"
    assert m["decisions"] == 1 and m["accepted_or_kept_share"] == 1.0
    assert metrics.compute()["flags_with_n_and_ids"] == "1 of 2"
