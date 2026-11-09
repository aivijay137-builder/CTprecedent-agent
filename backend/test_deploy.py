"""Step 1b: rate limit, CORS, health. Run: python -m pytest backend/test_deploy.py -q"""
import importlib

from fastapi.testclient import TestClient

from backend import appdb, main


def test_use_check_counts_per_visitor_per_day(tmp_path, monkeypatch):
    monkeypatch.setattr(appdb, "DB", tmp_path / "t.db")
    appdb.init()
    assert [appdb.use_check("a", 2) for _ in range(3)] == [True, True, False]
    assert appdb.use_check("b", 2)          # another visitor is unaffected
    assert appdb.use_check("a", 0)          # 0 = no limit


def test_visitor_is_hashed_and_uses_forwarded_ip():
    class R:
        headers = {"x-forwarded-for": "203.0.113.9, 10.0.0.1"}
        client = None
    v = main._visitor(R())
    assert "203.0.113.9" not in v and len(v) == 16
    R.headers = {"x-forwarded-for": "198.51.100.2"}
    assert main._visitor(R()) != v


def test_run_endpoint_returns_429_over_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(appdb, "DB", tmp_path / "t.db")
    appdb.init()
    monkeypatch.setenv("RATE_LIMIT_PER_DAY", "1")
    monkeypatch.setattr(main, "FIXTURES", False)
    monkeypatch.setattr(main, "_start_job", lambda *a, **k: "run_x")
    c = TestClient(main.app)
    brief = {"source": "form", "condition": "COPD", "phase": ["PHASE3"], "primary_endpoint": "FEV1", "target_enrollment": 100,
             "eligibility_text": "", "mesh_terms": [], "intervention_type": [], "countries": [], "arm_types": []}
    body = {"brief": brief, "focus": ["sites"], "filters": {}, "excluded_ids": []}
    assert c.post("/api/runs", json=body).status_code == 200
    r = c.post("/api/runs", json=body)
    assert r.status_code == 429 and "Daily limit" in r.json()["detail"]


def test_cors_only_for_listed_origin(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://faro-demo.vercel.app")
    m = importlib.reload(main)
    try:
        c = TestClient(m.app)
        ok = c.get("/api/health", headers={"Origin": "https://faro-demo.vercel.app"})
        bad = c.get("/api/health", headers={"Origin": "https://evil.example"})
        assert ok.headers.get("access-control-allow-origin") == "https://faro-demo.vercel.app"
        assert "access-control-allow-origin" not in bad.headers
    finally:
        monkeypatch.delenv("CORS_ORIGINS")
        importlib.reload(m)
