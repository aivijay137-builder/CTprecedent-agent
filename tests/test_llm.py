import sys, pathlib, types
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
import os; os.environ["LLM_MODEL"] = "m"; os.environ["LLM_RPM"] = "100000"
import httpx, llm
from openai import RateLimitError, BadRequestError


def _resp(txt):
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=txt))],
                                 usage=types.SimpleNamespace(prompt_tokens=3, completion_tokens=2))


def _err(cls, code):
    return cls("x", response=httpx.Response(code, request=httpx.Request("POST", "http://x")), body=None)


def _fake(*outcomes):
    calls = []
    def create(**kw):
        calls.append(kw); o = outcomes[len(calls) - 1]
        if isinstance(o, Exception): raise o
        return o
    return types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create))), calls


def test_retry_429_then_ok(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    c, calls = _fake(_err(RateLimitError, 429), _resp('{"a":1}'))
    out, tok = llm.ask_json("s", "u", client=c)
    assert out == {"a": 1} and tok == {"prompt_tokens": 3, "completion_tokens": 2} and len(calls) == 2


def test_fallback_when_json_mode_rejected():
    c, calls = _fake(_err(BadRequestError, 400), _resp('```json\n{"a":2}\n```'))
    out, _ = llm.ask_json("s", "u", client=c)
    assert out == {"a": 2} and "response_format" in calls[0] and "response_format" not in calls[1]


def test_retry_after_parsing():
    assert llm._retry_after("Please try again in 15.8625s. Need", 1) == 15.8625 + 1
    assert llm._retry_after("try again in 1m3.5s", 1) == 64.5
    assert llm._retry_after("no hint", 3) == 3
