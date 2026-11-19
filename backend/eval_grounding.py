"""Groundedness check: every NCT ID a run shows exists in the registry, and every finding's n matches its evidence list.
Runs the real engine (AI off) on a few registry trials as drafts. Exit 1 on any miss.
  python -m backend.eval_grounding
"""
import os
import sys

os.environ["LLM_ENABLED"] = "off"
from fastapi.testclient import TestClient  # noqa: E402

from . import engine, main  # noqa: E402

SEEDS = ["NCT03460704", "NCT00207337", "NCT07440914", "NCT00183560", "NCT07037680"]  # five different conditions; ponytail: add more IDs here


def check(seed: str) -> dict:
    c = TestClient(main.app)
    main.FIXTURES = False
    brief = c.post("/api/briefs/from-nct", json={"nct_id": seed}).json()
    rid = c.post("/api/runs", json={"brief": brief, "excluded_ids": []}).json()["run_id"]
    assert "event: done" in c.get(f"/api/runs/{rid}/events").text
    run = c.get(f"/api/runs/{rid}").json()
    findings = [f for el in run["elements"].values() for f in el["findings"]]
    flags = run["flags"]  # a flag's n is the group counted; its evidence may be the flagged subset (e.g. 8 of 11 posted no results), so only len(evidence) <= n is required
    ids = {i for f in findings + flags for i in f.get("evidence_ids", [])} | {x["nct_id"] for x in run["comparables"]}
    con = engine.connect()
    known = {r[0] for r in con.execute("SELECT nct_id FROM studies_current WHERE nct_id IN (SELECT unnest(?))", [sorted(ids)]).fetchall()}
    bad_n = [f["text"][:80] for f in findings if f["n"] != len(f["evidence_ids"]) and len(f["evidence_ids"]) != engine.EVIDENCE_CAP]
    bad_n += [f["id"] for f in flags if len(f["evidence_ids"]) > f["n"]]
    return {"seed": seed, "ids": len(ids), "unknown_ids": sorted(ids - known), "bad_n": bad_n, "findings": len(findings), "flags": len(flags)}


if __name__ == "__main__":
    res = [check(s) for s in SEEDS]
    for r in res:
        print(r)
    sys.exit(any(r["unknown_ids"] or r["bad_n"] for r in res))
