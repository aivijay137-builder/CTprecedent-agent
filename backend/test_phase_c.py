"""Phase C tests. A FAKE LLM replaces the network, so these cost nothing. Run: python -m pytest backend/test_phase_c.py -q"""
import json

import pytest

from backend import appdb, engine, llmsvc, readers


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(appdb, "DB", tmp_path / "test_app.db")  # never touch the real app.db
    appdb.init()
    for k, v in dict(LLM_API_KEY="k", LLM_BASE_URL="http://fake", LLM_MODEL="main-model", LLM_MODEL_ALT3="alt3-model", LLM_ENABLED="on",
                     LLM_PRICE_IN="1", LLM_PRICE_OUT="2", LLM_DAILY_BUDGET_USD="0.50", CUTOFF_FLAGS="on").items():
        monkeypatch.setenv(k, v)
    for k in ("LLM_MODEL_ALT", "LLM_MODEL_ALT2", "LLM_PRICE_IN_ALT", "LLM_PRICE_IN_ALT2", "LLM_PRICE_IN_ALT3"):
        monkeypatch.delenv(k, raising=False)  # the real .env must not leak into tests
    calls = []

    def fake(system, user, model=None, **kw):
        calls.append((model, user))
        if "main-model" == model and getattr(fake, "main_down", False):
            raise RuntimeError("provider down")
        return fake.reply(system, user), {"prompt_tokens": 100, "completion_tokens": 50}
    fake.reply = lambda system, user: {"criteria": []}
    monkeypatch.setattr(llmsvc.llm, "ask_json", fake)
    return fake, calls


def test_cache_means_same_input_costs_once(sandbox):
    fake, calls = sandbox
    fake.reply = lambda s, u: {"criteria": []}
    llmsvc.ask("t", "v4", "sys", "user")
    llmsvc.ask("t", "v4", "sys", "user")
    assert len(calls) == 1
    llmsvc.ask("t", "v4", "sys", "different user")
    assert len(calls) == 2


def test_switch_off_or_no_key_gives_clear_error_and_no_call(sandbox, monkeypatch):
    _, calls = sandbox
    monkeypatch.setenv("LLM_ENABLED", "off")
    with pytest.raises(llmsvc.LLMUnavailable, match="switched off"):
        llmsvc.ask("t", "v4", "s", "u")
    monkeypatch.setenv("LLM_ENABLED", "on")
    monkeypatch.setenv("LLM_API_KEY", "")
    with pytest.raises(llmsvc.LLMUnavailable, match="No AI key"):
        llmsvc.ask("t", "v4", "s", "u2")
    assert calls == []


def test_caps_per_run_and_per_day(sandbox, monkeypatch):
    b = llmsvc.Budget(1)
    llmsvc.ask("t", "v4", "s", "a", b)
    with pytest.raises(llmsvc.LLMUnavailable, match="limit of 1"):
        llmsvc.ask("t", "v4", "s", "b", b)
    monkeypatch.setenv("LLM_DAILY_BUDGET_USD", "0.0000001")  # one call already cost more than this
    with pytest.raises(llmsvc.LLMUnavailable, match="daily AI budget"):
        llmsvc.ask("t", "v4", "s", "c")


def test_falls_back_to_alt3_and_logs_tokens(sandbox):
    fake, calls = sandbox
    fake.main_down = True
    llmsvc.ask("t", "v4", "s", "u")
    assert [m for m, _ in calls] == ["main-model", "alt3-model"]
    from contextlib import closing
    with closing(appdb._c()) as c:
        rows = c.execute("SELECT model,status,prompt_tokens,cost_usd FROM llm_log ORDER BY id").fetchall()
    assert [(r["model"], r["status"]) for r in rows] == [("main-model", "error"), ("alt3-model", "ok")]
    assert rows[1]["prompt_tokens"] == 100 and rows[1]["cost_usd"] > 0
    fake.main_down = False


def test_all_models_down_is_a_clean_error(sandbox, monkeypatch):
    fake, _ = sandbox
    monkeypatch.setattr(llmsvc.llm, "ask_json", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    with pytest.raises(llmsvc.LLMUnavailable, match="did not answer"):
        llmsvc.ask("t", "v4", "s", "u")


def test_parse_design_checks_every_quote(sandbox):
    fake, _ = sandbox
    text = "Inclusion Criteria:\n* Age 18 to 75 years\n* HbA1c between 7.0% and 10.5%"
    fake.reply = lambda s, u: {"criteria": [
        {"name": "age", "direction": "min", "value": 18, "unit": "years", "source_sentence": "Age 18 to 75 years"},
        {"name": "HbA1c", "direction": "max", "value": "10.5", "unit": "%", "source_sentence": "HbA1c between 7.0% and 10.5%"},
        {"name": "bmi", "direction": "max", "value": 40, "unit": "kg/m2", "source_sentence": "BMI under 40 (INVENTED)"},  # not in the text
        {"name": "egfr", "direction": "sideways", "value": 45, "unit": "", "source_sentence": "x"},  # bad direction: dropped
        {"name": "weight", "direction": "min", "value": "heavy", "unit": "", "source_sentence": "x"}]}  # not a number: dropped
    got = {c["key"]: c for c in readers.parse_design(text, "diabetes")}
    assert set(got) == {"min_age", "hba1c_max", "bmi_max"}
    assert got["min_age"]["valid"] and got["hba1c_max"]["valid"]
    assert got["bmi_max"]["valid"] is False and got["bmi_max"]["source_sentence"] == ""  # invented quote is not shown as evidence


def test_extract_targets_batches_caches_and_refuses_invented_quotes(sandbox):
    fake, calls = sandbox
    texts = {f"NCT0000000{i}": f"Inclusion: HbA1c at least {i + 6}% to enter study number {i}" for i in range(7)}

    def reply(system, user):
        d = json.loads(user)
        out = {}
        for t in d["trials"]:
            n = int(t["id"][-1])
            out[t["id"]] = {"hba1c_min": ({"value": n + 6, "unit": "%", "source_sentence": f"HbA1c at least {n + 6}%"} if n != 3 else
                                          {"value": 99, "unit": "%", "source_sentence": "this sentence is made up"})}
        return {"trials": out}
    fake.reply = reply
    r = readers.extract_targets(texts, [{"key": "hba1c_min", "label": "HbA1c (min)"}])
    assert r["calls"] == 2 and r["not_yet_read"] == 0  # 7 trials, 5 per call
    v = r["values"]
    assert v[("NCT00000001", "hba1c_min")]["value"] == "7"
    assert v[("NCT00000003", "hba1c_min")]["status"] == "invalid"  # made-up quote: refused
    again = readers.extract_targets(texts, [{"key": "hba1c_min", "label": "x"}])
    assert again["calls"] == 0 and len(calls) == 2  # everything came from the cache
    # a deadline in the past starts no new calls
    more = {"NCT00000099": "HbA1c at least 9%"}
    stopped = readers.extract_targets(more, [{"key": "hba1c_min", "label": "x"}], deadline=1.0)
    assert stopped["calls"] == 0 and stopped["not_yet_read"] == 1


def test_full_run_on_real_registry_with_fake_ai_reader(sandbox):
    """Real comparables from ctg.duckdb; a FAKE AI reads their cutoffs; the generic finding and flag appear."""
    fake, calls = sandbox
    from brief import DesignBrief

    def reply(system, user):
        d = json.loads(user)
        return {"trials": {t["id"]: {f["key"]: {"value": 5, "unit": "", "source_sentence": t["text"].strip()[:30]} for f in d["fields"]}
                           for t in d["trials"] if len(t["text"].strip()) > 10}}
    fake.reply = reply
    b = DesignBrief(source="form", condition="psoriasis", mesh_terms=["Psoriasis"], phase=["PHASE3"], intervention_type=["BIOLOGICAL"],
                    eligibility_text="Inclusion:\n* PASI score >= 12", primary_endpoint="PASI 75 response at Week 16",
                    primary_endpoint_timeframe="16 weeks", target_enrollment=600, countries=["United States"],
                    structured_cutoffs={"cutoffs": [{"key": "pasi_score_min", "field": "PASI score (min)", "value": "12", "unit": ""}]})
    res = engine.run(b, ["population"], [])
    f = next(x for x in res["elements"]["population"]["findings"] if "pasi score" in x["text"].lower())
    assert f["n"] > 0 and "looser limit than your 12" in f["text"]
    # The fake AI says EVERY comparable is looser, so there is no stricter group to compare enrollment stops with:
    # the Population rule must not fire (it needs "stricter ones stopped for enrollment more often").
    assert not any(fl["id"].startswith("pop_") for fl in res["flags"]), [x["id"] for x in res["flags"]]
    assert any("read by an AI" in l for l in res["limits"])
    assert any(a["name"].startswith("4k.") for a in res["audit"])
    n_calls = len(calls)
    engine.run(b, ["population"], [])  # second run: all cutoffs are cached, no new AI calls
    assert len(calls) == n_calls


def test_engine_without_ai_still_works_and_says_so(sandbox, monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "off")
    from brief import DesignBrief
    b = DesignBrief(source="form", condition="psoriasis", mesh_terms=["Psoriasis"], phase=["PHASE3"], primary_endpoint="PASI 75",
                    target_enrollment=600, structured_cutoffs={"cutoffs": [{"key": "pasi_score_min", "field": "PASI score (min)", "value": "12", "unit": ""}]})
    res = engine.run(b, ["population"], [])
    assert res["bottom_line"]["n_comparables"] >= 5
    assert any("switched off" in l for l in res["limits"])


def test_a_trial_the_model_leaves_out_is_not_recorded_as_not_stated(sandbox):
    """Found with real trials: the model answered for 1 of 5 and the rest looked like 'no limit stated'."""
    fake, calls = sandbox
    texts = {f"NCT0000001{i}": "Inclusion: HbA1c at least 7%" for i in range(5)}

    def reply(system, user):
        ids = [t["id"] for t in json.loads(user)["trials"]]
        keep = ids if len(ids) <= 2 else ids[:1]  # a big batch loses 4 of 5; a small retry is answered in full
        return {"trials": {n: {"hba1c_min": {"value": 7, "unit": "%", "source_sentence": "HbA1c at least 7%"}} for n in keep}}
    fake.reply = reply
    r = readers.extract_targets(texts, [{"key": "hba1c_min", "label": "x"}])
    assert all(r["values"][(n, "hba1c_min")]["status"] == "ok" for n in texts) and r["not_yet_read"] == 0
    assert r["calls"] == 1 + 2  # the full batch, then the 4 left out re-asked in two calls of 2
    # and if the model keeps skipping them, they stay unread rather than 'not stated'
    fake.reply = lambda s, u: {"trials": {}}
    more = {"NCT00000099": "HbA1c at least 9%"}
    r = readers.extract_targets(more, [{"key": "hba1c_min", "label": "x"}])
    assert ("NCT00000099", "hba1c_min") not in r["values"] and r["not_yet_read"] == 1


def test_quote_check_ignores_lookalike_symbols_and_spacing_but_not_numbers():
    assert readers.quote_ok("* HbA1c \u22677.0 and \u22669.5%", "HbA1c \u2265 7.0 and \u2264 9.5%")
    assert not readers.quote_ok("HbA1c >= 7", "HbA1c >= 8")


def test_all_four_models_are_tried_in_order_and_unpriced_ones_use_the_main_price(sandbox, monkeypatch):
    fake, calls = sandbox
    monkeypatch.setenv("LLM_MODEL_ALT", "alt-model")
    monkeypatch.setenv("LLM_MODEL_ALT2", "alt2-model")
    assert llmsvc.models() == ["main-model", "alt-model", "alt3-model", "alt2-model"]  # the weakest is last
    monkeypatch.setattr(llmsvc.llm, "ask_json", lambda s, u, model=None, **k: (_ for _ in ()).throw(RuntimeError("down")) if model != "alt2-model" else ({"ok": 1}, {"prompt_tokens": 1000000, "completion_tokens": 0}))
    assert llmsvc.ask("t", "v5", "s", "all but the last are down") == {"ok": 1}
    assert llmsvc._price("alt2-model") == llmsvc._price("main-model") == (1.0, 2.0)  # no own price -> the main model's (an estimate)
    monkeypatch.setenv("LLM_PRICE_IN_ALT2", "0.05")
    assert llmsvc._price("alt2-model")[0] == 0.05


# ------------------------------------------------------------ flag sentence writer (evidence bundle only)
from backend import writer  # noqa: E402


def _flag(fid="sites_competing_trials"):
    return {"id": fid, "element": "sites", "title": "224 trials recruiting in your 3 countries", "n": 224, "confidence": "stated",
            "body": "224 other Diabetes Mellitus, Type 2 trials are recruiting with a site in United States, Germany and Japan. Only trials verified in the last 12 months are counted.",
            "question": "Which of your planned sites overlap with these trials?", "evidence_ids": ["NCT00000001"]}


def test_writer_accepts_a_sentence_that_uses_only_the_bundle(sandbox):
    fake, calls = sandbox
    fake.reply = lambda s, u: {"sentences": {"sites_competing_trials": "224 other type 2 diabetes trials are recruiting in the United States, Germany and Japan, counting only trials verified in the last 12 months."}}
    f = _flag()
    r = writer.reword([f])
    assert r == {"used": 1, "refused": {}} and f["written_by"] == "ai" and f["body"].startswith("224 other type 2")
    assert f["n"] == 224 and f["evidence_ids"] == ["NCT00000001"] and f["confidence"] == "stated"  # nothing but the text can change


@pytest.mark.parametrize("bad,why", [
    ("About 230 trials are recruiting in your three countries.", "new number"),          # invented count (and a number word)
    ("224 trials are recruiting, roughly 40% in Germany.", "new number"),                 # invented percentage
    ("224 trials recruit; see NCT01234567 for one example.", "trial ID"),                 # invented NCT ID
    ("Two hundred twenty four trials recruit in United States, Germany and Japan now.", "number word"),
    ("Too short", "length"),
])
def test_writer_refuses_anything_not_in_the_bundle_and_keeps_the_template(sandbox, bad, why):
    fake, calls = sandbox
    fake.reply = lambda s, u: {"sentences": {"sites_competing_trials": bad}}
    f = _flag()
    template = f["body"]
    r = writer.reword([f])
    assert r["used"] == 0 and "sites_competing_trials" in r["refused"]
    assert f["body"] == template and "written_by" not in f


def test_writer_is_cached_and_raises_a_clear_error_when_ai_is_off(sandbox, monkeypatch):
    fake, calls = sandbox
    fake.reply = lambda s, u: {"sentences": {"sites_competing_trials": "224 other type 2 diabetes trials are recruiting in the United States, Germany and Japan."}}
    writer.reword([_flag()])
    writer.reword([_flag()])
    assert len(calls) == 1  # same bundle, same answer from the cache
    monkeypatch.setenv("LLM_ENABLED", "off")
    with pytest.raises(llmsvc.LLMUnavailable):
        writer.reword([_flag("another_flag")])


def test_a_broken_json_reply_is_retried_once_on_the_same_model(sandbox, monkeypatch):
    fake, calls = sandbox
    seen = []

    def flaky(system, user, model=None, **kw):
        seen.append(model)
        if len(seen) == 1:
            raise json.JSONDecodeError("cut off", "{", 1)
        return {"ok": 1}, {"prompt_tokens": 1, "completion_tokens": 1}
    monkeypatch.setattr(llmsvc.llm, "ask_json", flaky)
    assert llmsvc.ask("t", "v5", "s", "flaky json") == {"ok": 1}
    assert seen == ["main-model", "main-model"]  # same model twice, no fallback needed
