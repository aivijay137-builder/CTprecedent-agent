"""Real-engine test (reads the real databases). Run: python -m pytest backend/test_real.py -q"""
import time

import pytest
from fastapi.testclient import TestClient

from backend import engine, main

c = TestClient(main.app)


@pytest.fixture(autouse=True)
def real_mode(monkeypatch):
    monkeypatch.setattr(main, "FIXTURES", False)


def _run(brief, excluded=()):
    rid = c.post("/api/runs", json={"brief": brief, "excluded_ids": list(excluded)}).json()["run_id"]
    text = c.get(f"/api/runs/{rid}/events").text
    assert "event: done" in text, text
    return rid, c.get(f"/api/runs/{rid}").json()


def test_from_nct_to_package_under_60s():
    t = time.time()
    brief = c.post("/api/briefs/from-nct", json={"nct_id": "NCT03460704"}).json()
    rid, run = _run(brief)
    assert time.time() - t < 60
    assert run["bottom_line"]["n_comparables"] >= 5 and "NCT03460704" not in [x["nct_id"] for x in run["comparables"]]
    # every finding: n matches its evidence (unless capped at 50)
    for el in run["elements"].values():
        for f in el["findings"]:
            assert f["n"] == len(f["evidence_ids"]) or len(f["evidence_ids"]) == engine.EVIDENCE_CAP, f
    # the numbers on screen equal the audited SQL re-run by hand
    audit = {a["name"][:2]: a["sql"] for a in run["audit"]}
    con = engine.connect()
    by_hand = dict(con.execute(audit["2a"]).fetchall())
    assert {k: v for k, v in run["outcomes"]["comparables"].items() if v} == by_hand
    base = dict(con.execute(audit["2b"]).fetchall())
    assert {k: v for k, v in run["outcomes"]["baseline"].items() if v} == base
    assert sum(by_hand.values()) == run["bottom_line"]["n_comparables"]
    # decisions + rerun with a removed comparable lowers the count and returns a diff
    for f in run["flags"]:
        assert c.post(f"/api/runs/{rid}/flags/{f['id']}/decision", json={"action": "defer"}).status_code == 200
    pid = c.post(f"/api/runs/{rid}/package").json()["package_id"]
    fid = run["flags"][0]["id"]
    assert c.post(f"/api/packages/{pid}/review", json={"flag_id": fid, "action": "send_back"}).json()["reviews"][fid]
    assert c.get(f"/api/runs/{rid}").json()["flags"][0]["status"] == "open"  # sent back = reopened for the lead
    gone = run["comparables"][0]["nct_id"]
    rr = c.post(f"/api/runs/{rid}/rerun", json={"brief": brief, "excluded_ids": [gone]}).json()
    run2 = None
    for _ in range(100):
        r = c.get(f"/api/runs/{rr['run_id']}")
        if r.status_code == 200:
            run2 = r.json()
            break
        time.sleep(0.2)
    assert run2 and run2["bottom_line"]["n_comparables"] == run["bottom_line"]["n_comparables"] - 1
    assert run2["diff"] is not None
    assert c.get(f"/api/trials/{gone}").json()["nct_id"] == gone


def test_unknown_nct_is_404_and_few_comparables_gives_no_flags():
    assert c.post("/api/briefs/from-nct", json={"nct_id": "NCT00000000"}).status_code == 404
    brief = c.post("/api/briefs/from-nct", json={"nct_id": "NCT03460704"}).json()
    brief.update(mesh_terms=["Alpha 1-Antitrypsin Deficiency"], condition="AATD", phase=["PHASE1"], nct_id=None)
    _, run = _run(brief)
    if run["bottom_line"]["n_comparables"] < 5:
        assert run["flags"] == [] and run["bottom_line"]["risk"] == "insufficient" and run["no_flags_reason"]


def test_health_reports_real_date():
    h = c.get("/api/health").json()
    assert h["fixtures"] is False and h["data_as_of"].startswith("2026-") and h["row_counts"]["studies_current"] > 500000


def test_any_disease_form_design_and_criteria_reader():
    # condition lookup works with words in any order
    assert any(x["term"] == "Diabetes Mellitus, Type 2" for x in c.get("/api/conditions/suggest", params={"q": "type 2 diab"}).json())
    # rule-based reader: numbers + the verbatim sentence they came from
    text = chr(10).join(["Inclusion Criteria:", "* Age 18 to 70 years", "* PASI score >= 12", "* Plaque psoriasis for at least 6 months"])
    cut = c.post("/api/briefs/parse", json={"eligibility_text": text, "condition": "psoriasis"}).json()["cutoffs"]
    by = {x["key"]: x for x in cut}
    assert by["min_age"]["value"] == "18" and by["max_age"]["value"] == "70" and by["pasi_score_min"]["value"] == "12"
    assert all(x["source_sentence"] in text for x in cut)
    assert not any(k.startswith("psoriasis_for") for k in by)
    # a brand-new design for a disease nobody pre-loaded runs end to end
    brief = {"source": "form", "condition": "psoriasis", "mesh_terms": ["Psoriasis"], "phase": ["PHASE3"], "intervention_type": ["BIOLOGICAL"],
             "eligibility_text": text, "primary_endpoint": "PASI 75 response at Week 16", "primary_endpoint_timeframe": "16 weeks",
             "target_enrollment": 600, "countries": ["United States"]}
    _, run = _run(brief)
    assert run["bottom_line"]["n_comparables"] >= 5 and run["condition_support"] == "basic"
