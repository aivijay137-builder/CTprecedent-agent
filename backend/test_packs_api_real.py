"""Packs through the API on the REAL registry (skips itself without it): route, run with a pack, decision log, compare.
Run: python -m pytest backend/test_packs_api_real.py -q"""
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import appdb, main

FIX = Path(__file__).parent / "fixtures" / "packs"


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(appdb, "DB", tmp_path / "t.db")
    appdb.init()
    monkeypatch.setattr(main, "FIXTURES", False)
    monkeypatch.setenv("PACKS_DIR", str(FIX))
    monkeypatch.setenv("LLM_ENABLED", "off")
    return TestClient(main.app)


def run(api, brief, packs=None):
    body = {"brief": brief, "focus": ["population", "endpoints", "size", "sites", "design"], "filters": {}, "excluded_ids": []}
    if packs is not None:
        body["packs"] = packs
    rid = api.post("/api/runs", json=body).json()["run_id"]
    assert "event: done" in api.get(f"/api/runs/{rid}/events").text
    return rid, api.get(f"/api/runs/{rid}").json()


def test_route_suggests_and_previews_without_choosing(api):
    r = api.post("/api/packs/route", json={"condition": "COPD", "mesh_terms": ["Pulmonary Disease, Chronic Obstructive"]}).json()
    assert r["available"] and (r["indication"], r["area"]) == ("copd", "respiratory")
    assert r["preview"]["status"] == "draft" and "AREA NOTES" in r["preview"]["addon_text"] and r["preview"]["hard_filter"] == "intervention_class"
    assert {p["id"] for p in r["all_packs"]} >= {"respiratory", "copd"}   # the lead can pick another


def test_run_with_and_without_a_pack_then_compare(api):
    brief = api.post("/api/briefs/from-nct", json={"nct_id": "NCT03460704"}).json()
    rid_off, off = run(api, brief)
    assert off["pack"] is None
    rid_on, on = run(api, brief, {"area": "respiratory", "parts": {}})
    assert on["pack"]["pack"] == "Respiratory" and on["pack"]["status"] == "draft" and "hard_filter" in on["pack"] and "ranking" in on["pack"]
    assert on["pack"]["parts"] == {"addon": True, "ranking": True, "hard_filter": True, "era": False}
    cmp = api.get("/api/compare", params={"a": rid_off, "b": rid_on}).json()
    assert cmp["a"]["label"] == "Prompt only" and cmp["b"]["label"].startswith("With pack: Respiratory")
    assert cmp["comparables"]["in_both"] + len(cmp["comparables"]["only_a"]) == len(off["comparables"])
    assert "not which result is better" in cmp["note"]


def test_pack_choice_is_written_to_the_decision_log_with_role(api):
    brief = api.post("/api/briefs/from-nct", json={"nct_id": "NCT03460704"}).json()
    rid, _ = run(api, brief, {"area": "respiratory"})
    rows = sqlite3.connect(appdb.DB).execute("SELECT role, kind, action, run_id, reason FROM decisions WHERE kind = 'pack'").fetchall()
    assert len(rows) == 1 and rows[0][:4] == ("lead", "pack", "on", rid)
    assert json.loads(rows[0][4])["ids"] == ["respiratory"]
    run(api, brief)                                                       # prompt only: nothing is logged
    assert len(sqlite3.connect(appdb.DB).execute("SELECT 1 FROM decisions WHERE kind = 'pack'").fetchall()) == 1


def test_compare_with_a_missing_run_is_404(api):
    assert api.get("/api/compare", params={"a": "nope", "b": "nope"}).status_code == 404
