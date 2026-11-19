"""Pack endpoints and request checks that need no registry. Run: python -m pytest backend/test_packs_api.py -q"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import main

FIX = Path(__file__).parent / "fixtures" / "packs"
c = TestClient(main.app)


@pytest.fixture(autouse=True)
def real_mode(monkeypatch):
    monkeypatch.setattr(main, "FIXTURES", False)
    monkeypatch.setenv("PACKS_DIR", str(FIX))


def test_pack_list_hides_the_base_and_says_available():
    r = c.get("/api/packs").json()
    assert r["available"] and {p["id"] for p in r["packs"]} == {"respiratory", "cardiovascular", "oncology_solid", "copd"}
    assert all(p["status"] == "draft" for p in r["packs"])


def test_server_without_pack_files_reports_none_and_refuses_a_pack_choice(monkeypatch, tmp_path):
    monkeypatch.setenv("PACKS_DIR", str(tmp_path))
    assert c.get("/api/packs").json() == {"available": False, "packs": []}
    assert c.post("/api/packs/route", json={"condition": "COPD", "mesh_terms": ["x"]}).json() == {"available": False}
    r = c.post("/api/briefs/parse", json={"eligibility_text": "Age 18 or older", "condition": "COPD", "pack": {"area": "respiratory"}})
    assert r.status_code == 400 and "not available" in r.json()["detail"]


def test_unknown_or_wrong_level_pack_is_refused():
    for choice in ({"area": "nope"}, {"area": "copd"}, {"indication": "respiratory"}):
        r = c.post("/api/briefs/parse", json={"eligibility_text": "Age 18 or older", "condition": "COPD", "pack": choice})
        assert r.status_code == 400, choice


def test_an_empty_choice_means_prompt_only_and_is_not_an_error():
    assert main._effective_pack(None) is None
    assert main._effective_pack(main.PackChoice()) is None


def test_choice_becomes_a_merged_pack_with_the_leads_switches():
    eff = main._effective_pack(main.PackChoice(area="respiratory", indication="copd", parts={"addon": False}))
    assert eff["ids"] == ["respiratory", "copd"] and eff["parts"]["addon"] is False and eff["parts"]["ranking"] is True and eff["parts"]["era"] is False
