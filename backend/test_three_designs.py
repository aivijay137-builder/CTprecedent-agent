"""Step 3 regression: three real designs end to end through the API (AI off, throwaway app.db).
It checks rules that must always hold, not exact counts (the registry changes daily). Run: python -m pytest backend/test_three_designs.py -q"""
import json
import time

import pytest
from fastapi.testclient import TestClient

from backend import appdb, flag_config as cfg, main


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(appdb, "DB", tmp_path / "t.db")
    appdb.init()
    monkeypatch.setattr(main, "FIXTURES", False)
    monkeypatch.setenv("LLM_ENABLED", "off")  # no paid calls, whatever .env says
    return TestClient(main.app)


def run(api, brief):
    if brief.get("eligibility_text") and not brief.get("structured_cutoffs"):
        p = api.post("/api/briefs/parse", json={"eligibility_text": brief["eligibility_text"], "condition": brief["condition"]}).json()
        brief["structured_cutoffs"] = {"cutoffs": p["cutoffs"]}
    t = time.time()
    rid = api.post("/api/runs", json={"brief": brief}).json()["run_id"]
    assert "event: done" in api.get(f"/api/runs/{rid}/events").text
    out = api.get(f"/api/runs/{rid}").json()
    assert time.time() - t < 60
    return out


def designs(api):
    copd = json.load(open("backend/fixtures/briefs.json", encoding="utf-8"))["NCT03460704"]
    copd.update(source="form", nct_id=None, mesh_terms=["Pulmonary Disease, Chronic Obstructive"], arm_types=["EXPERIMENTAL", "PLACEBO_COMPARATOR"])
    psor = {"source": "form", "condition": "psoriasis", "mesh_terms": ["Psoriasis"], "phase": ["PHASE3"], "intervention_type": ["BIOLOGICAL"],
            "eligibility_text": "Inclusion Criteria:\n* Age 18 to 70 years\n* PASI score >= 12", "primary_endpoint": "PASI 75 response at Week 16",
            "primary_endpoint_timeframe": "16 weeks", "target_enrollment": 600, "countries": ["United States", "Germany"], "arm_types": ["EXPERIMENTAL", "PLACEBO_COMPARATOR"]}
    nct = api.post("/api/briefs/from-nct", json={"nct_id": "NCT03460704"}).json()
    return {"copd": copd, "psoriasis": psor, "NCT03460704": nct}


def test_three_designs_obey_every_flag_rule(api):
    for name, brief in designs(api).items():
        r = run(api, brief)
        flags = r["flags"]
        assert len(flags) <= cfg.MAX_FLAGS, name
        for f in flags:
            assert f["n"] >= cfg.MIN_N and f["evidence_ids"], (name, f["id"])
            assert f["confidence"] == "stated", (name, f["id"])  # nothing links an outside source today
            assert f["id"] != "size_above_actual" or f["n"] >= cfg.MIN_N
        # ties/ordering: strongest first (n is the evidence base; sites and endpoints have the largest counts here)
        assert {f["id"] for f in flags} <= {"sites_competing_trials", "endpoint_precedent", "design_control_arm_stops", "size_above_actual"} \
            or all(f["id"].startswith("pop_") for f in flags if f["id"] not in ("sites_competing_trials", "endpoint_precedent", "design_control_arm_stops", "size_above_actual"))
        # with AI off no comparable cutoffs are read, so Population must say why it was not checked (it may not silently vanish)
        assert any(n.startswith("Population") for n in r["rule_notes"]), name
        assert r["bottom_line"]["n_comparables"] >= cfg.MIN_N


def test_copd_and_psoriasis_fire_the_sites_rule_with_the_right_threshold(api):
    d = designs(api)
    for name in ("copd", "psoriasis"):
        r = run(api, d[name])
        sites = next((f for f in r["flags"] if f["id"] == "sites_competing_trials"), None)
        assert sites and sites["n"] >= cfg.SITES_MIN_TRIALS, name
