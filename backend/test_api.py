"""One smoke test of the whole fixture flow. Run: python -m pytest backend -q"""
from fastapi.testclient import TestClient
import pytest

from backend import main
from backend.main import app

c = TestClient(app)


@pytest.fixture(autouse=True)
def fixtures_mode(monkeypatch):
    monkeypatch.setattr(main, "FIXTURES", True)  # this file tests the canned-data mode whatever .env says


def test_flow():
    b = c.post("/api/briefs/from-nct", json={"nct_id": "NCT03460704"}).json()
    assert c.post("/api/briefs/from-nct", json={"nct_id": "NCT00000000"}).status_code == 404
    rid = c.post("/api/runs", json={"brief": b}).json()["run_id"]
    assert "event: done" in c.get(f"/api/runs/{rid}/events").text
    run = c.get(f"/api/runs/{rid}").json()
    assert run["bottom_line"]["n_comparables"] == 28 and len(run["flags"]) == 3
    fid = run["flags"][0]["id"]
    assert c.post(f"/api/runs/{rid}/flags/{fid}/decision", json={"action": "keep"}).status_code == 422
    for f in run["flags"]:
        assert c.post(f"/api/runs/{rid}/flags/{f['id']}/decision", json={"action": "defer"}).status_code == 200
    pid = c.post(f"/api/runs/{rid}/package").json()["package_id"]
    assert c.post(f"/api/packages/{pid}/review", json={"flag_id": fid, "action": "send_back"}).json()["reviews"][fid]
    assert c.get(f"/api/runs/{rid}").json()["flags"][0]["status"] == "open"
    gone = run["comparables"][0]["nct_id"]
    rr = c.post(f"/api/runs/{rid}/rerun", json={"brief": b, "excluded_ids": [gone]}).json()
    assert len(rr["diff"]["still_open"]) + len(rr["diff"]["resolved"]) == 3
    few = c.get(f"/api/runs/{c.post('/api/runs', json={'brief': c.post('/api/briefs/from-nct', json={'nct_id': 'NCT05000002'}).json()}).json()['run_id']}").json()
    assert few["flags"] == [] and few["no_flags_reason"]
    bad = c.post("/api/briefs/from-nct", json={"nct_id": "NCT05000004"}).json()
    assert c.post("/api/runs", json={"brief": bad}).status_code == 422
