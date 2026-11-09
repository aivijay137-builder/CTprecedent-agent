"""Step 1c: bring-your-own-key. The key must never be stored or logged. Run: python -m pytest backend/test_byok.py -q"""
import logging
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import llm
from backend import appdb, byok, llmsvc, main

KEY = "sk-SECRETKEY1234567890abcdefXYZ"
HDR = {"X-LLM-Key": KEY, "X-LLM-Base-URL": "https://8.8.8.8/v1", "X-LLM-Model": "my-model"}


class AuthenticationError(Exception):  # same class name the provider library uses
    pass


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(appdb, "DB", tmp_path / "t.db")
    appdb.init()
    monkeypatch.setenv("LLM_MODEL", "server-model")        # the server's own settings, which a visitor's key must never use
    monkeypatch.setenv("LLM_API_KEY", "server-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://server.example/v1")
    monkeypatch.setenv("LLM_ENABLED", "off")
    return tmp_path / "t.db"


def creds():
    return byok.Creds("https://8.8.8.8/v1", KEY, "my-model")


def fake_ok(monkeypatch, seen=None):
    def ask_json(system, user, model=None, client=None, retries=8):
        if seen is not None:
            seen.append(model)
        return {"ok": True}, {"prompt_tokens": 100, "completion_tokens": 20}
    monkeypatch.setattr(llm, "ask_json", ask_json)
    monkeypatch.setattr(llm, "client_for", lambda b, k: object())


def test_own_key_works_even_when_server_ai_is_off_and_uses_only_its_model(monkeypatch):
    seen = []
    fake_ok(monkeypatch, seen)
    assert not llmsvc.enabled()                       # server switch is off
    b = llmsvc.Budget()
    with llmsvc.use(creds()):
        assert llmsvc.enabled() and llmsvc.models() == ["my-model"]
        llmsvc.ask("t", "v1", "sys", "user", b)
    assert seen == ["my-model"] and b.used == 1 and b.tokens == 120
    assert not llmsvc.enabled()                       # the key does not leak past the block


def test_own_key_costs_nothing_against_the_server_cap(monkeypatch):
    fake_ok(monkeypatch)
    with llmsvc.use(creds()):
        llmsvc.ask("t", "v1", "sys", "u2")
    assert llmsvc.spent_today() == 0.0


def test_key_never_stored_or_logged(monkeypatch, tmp_db, caplog, capsys):
    def boom(system, user, model=None, client=None, retries=8):
        raise AuthenticationError(f"Incorrect API key provided: {KEY[:8]}****{KEY[-4:]} / {KEY}")
    monkeypatch.setattr(llm, "ask_json", boom)
    monkeypatch.setattr(llm, "client_for", lambda b, k: object())
    caplog.set_level(logging.DEBUG)
    with llmsvc.use(creds()):
        with pytest.raises(llmsvc.LLMUnavailable) as e:
            llmsvc.ask("t", "v1", "sys", "u3")
    assert KEY not in str(e.value)
    fake_ok(monkeypatch)
    with llmsvc.use(creds()):
        llmsvc.ask("t", "v1", "sys", "u4")
    out = capsys.readouterr()
    blob = tmp_db.read_bytes() + (caplog.text + out.out + out.err).encode()
    for bit in (KEY, KEY[:8], KEY[-4:]):
        assert bit.encode() not in blob, bit


def test_rejected_key_stops_further_calls_and_never_falls_back_to_server(monkeypatch):
    calls = []

    def boom(system, user, model=None, client=None, retries=8):
        calls.append(model)
        raise AuthenticationError("nope")
    monkeypatch.setattr(llm, "ask_json", boom)
    monkeypatch.setattr(llm, "client_for", lambda b, k: object())
    c = creds()
    with llmsvc.use(c):
        for n in range(3):
            with pytest.raises(llmsvc.LLMUnavailable, match="not accepted"):
                llmsvc.ask("t", "v1", "sys", f"u{n}")
    assert calls == ["my-model"]                      # one try; no server model; no repeat after the first refusal


def test_unknown_model_gives_a_clear_message_and_one_try(monkeypatch):
    calls = []

    class NotFoundError(Exception):
        pass

    def boom(system, user, model=None, client=None, retries=8):
        calls.append(model)
        raise NotFoundError("model not found")
    monkeypatch.setattr(llm, "ask_json", boom)
    monkeypatch.setattr(llm, "client_for", lambda b, k: object())
    with llmsvc.use(creds()):
        for n in range(3):
            with pytest.raises(llmsvc.LLMUnavailable, match='does not know the model "my-model"'):
                llmsvc.ask("t", "v1", "sys", f"nf{n}")
    assert calls == ["my-model"]


def test_test_key_shows_the_providers_reason_without_the_key(monkeypatch):
    c = TestClient(main.app)

    class PermissionDeniedError(Exception):
        message = f"Model requires terms acceptance for key {KEY}"

    def boom(*a, **k):
        raise PermissionDeniedError("x")
    monkeypatch.setattr(llm, "ask_json", boom)
    r = c.post("/api/llm/test", headers=HDR).json()
    assert r["ok"] is False and "not allowed to use that model" in r["message"] and "terms acceptance" in r["message"]
    assert KEY not in r["message"] and KEY[:8] not in r["message"]


def test_permission_denied_is_not_called_a_bad_key(monkeypatch):
    class PermissionDeniedError(Exception):
        pass

    def boom(system, user, model=None, client=None, retries=8):
        raise PermissionDeniedError("403")
    monkeypatch.setattr(llm, "ask_json", boom)
    monkeypatch.setattr(llm, "client_for", lambda b, k: object())
    with llmsvc.use(creds()):
        with pytest.raises(llmsvc.LLMUnavailable, match="permission denied"):
            llmsvc.ask("t", "v1", "sys", "pd1")


def test_url_guard():
    for bad in ("http://8.8.8.8/v1", "https://127.0.0.1/v1", "https://localhost/v1", "https://10.0.0.5/v1",
                "https://169.254.169.254/latest", "https://user:pw@8.8.8.8/v1", "ftp://8.8.8.8"):
        with pytest.raises(ValueError):
            byok.check_url(bad)
    byok.check_url("https://8.8.8.8/v1")


def test_headers_to_creds():
    class R:
        def __init__(self, h): self.headers = {k.lower(): v for k, v in h.items()}
    assert byok.from_request(R({})) is None
    c = byok.from_request(R(HDR))
    assert (c.base_url, c.model, c.api_key) == ("https://8.8.8.8/v1", "my-model", KEY)
    with pytest.raises(HTTPException) as e:
        byok.from_request(R({"X-LLM-Key": KEY}))
    assert e.value.status_code == 400
    with pytest.raises(HTTPException):
        byok.from_request(R({**HDR, "X-LLM-Base-URL": "https://192.168.1.1/v1"}))


def test_test_key_endpoint(monkeypatch):
    c = TestClient(main.app)
    fake_ok(monkeypatch)
    assert c.post("/api/llm/test", headers=HDR).json() == {"ok": True, "message": "The key works."}
    assert c.post("/api/llm/test").status_code == 400

    def boom(*a, **k):
        raise AuthenticationError(f"bad key {KEY}")
    monkeypatch.setattr(llm, "ask_json", boom)
    r = c.post("/api/llm/test", headers=HDR)
    assert r.json()["ok"] is False and KEY not in r.text and "rejected" in r.json()["message"]


def test_background_run_gets_the_visitors_key(monkeypatch):
    got = {}

    def fake_run(brief, focus, excluded, progress):
        got["c"] = llmsvc.current()
        return {"flags": [], "bottom_line": {}}
    monkeypatch.setattr(main.engine, "run", fake_run)
    monkeypatch.setattr(main.appdb, "save_run", lambda *a, **k: None)
    rid = main._start_job(None, [], [], None, creds=creds())
    for _ in range(50):
        if main.JOBS[rid]["state"] != "running":
            break
        time.sleep(0.05)
    assert got["c"].api_key == KEY
