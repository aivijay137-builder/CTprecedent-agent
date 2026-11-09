"""The one door to the LLM for the web app (Phase C). Wraps src/llm.py with:
  - a cache keyed by a hash of the input (app.db), so the same input never costs twice,
  - a token + cost log (app.db, table llm_log),
  - hard caps: calls per run and dollars per day,
  - a model chain: LLM_MODEL first, then LLM_MODEL_ALT3 if it fails,
  - clear errors when no key is set, so the caller can fall back to the free rule-based reader.
"""
import hashlib
import json
import os
import contextvars
import time
from contextlib import closing, contextmanager
from datetime import datetime, timezone

import llm  # src/llm.py: retries, rate-limit pacing, JSON parsing

from . import appdb


_creds: contextvars.ContextVar = contextvars.ContextVar("llm_creds", default=None)


@contextmanager
def use(creds):
    """Make a visitor's own key the one every AI call in this block uses (None = the server's settings)."""
    tok = _creds.set(creds)
    try:
        yield
    finally:
        _creds.reset(tok)


def current():
    return _creds.get()


def _scrub(text: str, c) -> str:
    """Remove the visitor's key (and the masked pieces providers echo back, like 'sk-abc****xyz') from any text we store or show."""
    if c and c.api_key:
        for bit in (c.api_key, c.api_key[:8], c.api_key[-4:]):
            if len(bit) >= 4:
                text = text.replace(bit, "[key]")
    return text


class LLMUnavailable(Exception):
    """No key, a cap was hit, or every model failed. The message is safe to show the user."""


def configured() -> bool:
    if current():
        return True
    return bool(os.environ.get("LLM_API_KEY") and os.environ.get("LLM_BASE_URL") and os.environ.get("LLM_MODEL"))


def enabled() -> bool:
    """Master switch. Paid calls happen only when LLM_ENABLED=on in .env AND a key is set. Default: off."""
    if current():
        return True  # the visitor brought their own key: no server switch involved
    return configured() and os.environ.get("LLM_ENABLED", "off").strip().lower() == "on"


def models() -> list[str]:
    """Order tried when a call fails: main model, then ALT, ALT3, and the weakest (ALT2) last. A model name that is
    missing from .env is skipped; a name the provider does not know just fails fast and the next one is tried."""
    if current():
        return [current().model]  # never fall back to the server's own models
    e = os.environ.get
    out = []
    for m in (e("LLM_MODEL"), e("LLM_MODEL_ALT"), e("LLM_MODEL_ALT3"), e("LLM_MODEL_ALT2")):
        if m and m not in out:
            out.append(m)
    return out


def _price(model: str) -> tuple[float, float]:
    """USD per million tokens (in, out). A fallback model with no price of its own is billed at the MAIN model's price:
    an ESTIMATE that errs high (the smaller models cost less), so the daily cap stays safe. Set LLM_PRICE_IN_ALT / _OUT_ALT
    (and _ALT2, _ALT3) in .env when you know the real prices."""
    if current():
        return (0.0, 0.0)  # the visitor pays their provider; nothing counts against the server's daily cap
    e = os.environ.get
    main = (float(e("LLM_PRICE_IN") or 0), float(e("LLM_PRICE_OUT") or 0))
    for suffix, name in (("_ALT3", e("LLM_MODEL_ALT3")), ("_ALT2", e("LLM_MODEL_ALT2")), ("_ALT", e("LLM_MODEL_ALT"))):
        if model == name and model != e("LLM_MODEL"):
            return float(e("LLM_PRICE_IN" + suffix) or main[0]), float(e("LLM_PRICE_OUT" + suffix) or main[1])
    return main


def spent_today() -> float:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with closing(appdb._c()) as c:
        r = c.execute("SELECT coalesce(sum(cost_usd), 0) FROM llm_log WHERE ts LIKE ? AND status = 'ok'", (day + "%",)).fetchone()
    return float(r[0])


class Budget:
    """Calls allowed in ONE run (default 60, env LLM_MAX_CALLS_PER_RUN)."""

    def __init__(self, max_calls: int | None = None):
        self.max = max_calls if max_calls is not None else int(os.environ.get("LLM_MAX_CALLS_PER_RUN") or 60)
        self.used = 0
        self.tokens = 0  # prompt + completion tokens used in this run (shown to the user)

    def use(self):
        if self.used >= self.max:
            raise LLMUnavailable(f"This run reached its limit of {self.max} AI calls.")
        self.used += 1


def _log(task, model, version, tok, cost, secs, status, error=""):
    with closing(appdb._c()) as c, c:
        c.execute("INSERT INTO llm_log(ts,task,model,prompt_version,prompt_tokens,completion_tokens,cost_usd,seconds,status,error) VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (appdb.now(), task, model, version, tok.get("prompt_tokens", 0), tok.get("completion_tokens", 0), cost, secs, status, error[:300]))


def ask(task: str, version: str, system: str, user: str, budget: Budget | None = None) -> dict:
    """Returns the model's JSON. Same (task, version, system, user) is served from the cache for free."""
    key = hashlib.sha256(f"{task}|{version}|{system}|{user}".encode()).hexdigest()
    with closing(appdb._c()) as c:
        hit = c.execute("SELECT response FROM llm_cache WHERE key = ?", (key,)).fetchone()
    if hit:
        return json.loads(hit["response"])
    if not configured():
        raise LLMUnavailable("No AI key is set. Add LLM_BASE_URL, LLM_API_KEY and LLM_MODEL to .env to turn this on.")
    if not enabled():
        raise LLMUnavailable("AI reading is switched off. Set LLM_ENABLED=on in .env to turn it on (it makes paid calls).")
    c = current()
    if c and c.rejected:
        raise LLMUnavailable("Your AI key was not accepted by the provider, so this check used the free reader.")
    cap = float(os.environ.get("LLM_DAILY_BUDGET_USD") or 0.50)
    if not c and spent_today() >= cap:
        raise LLMUnavailable(f"The daily AI budget of ${cap:.2f} is used up. It resets tomorrow (UTC).")
    if budget:
        budget.use()
    last = ""
    for model in models():
        out = None
        for attempt in (1, 2):  # a reply that is not valid JSON (cut off, empty) is worth one more try on the same model
            t0 = time.time()
            try:
                out, tok = llm.ask_json(system, user, model=model, client=llm.client_for(c.base_url, c.api_key) if c else None)
                break
            except Exception as e:  # rate limit that will not clear, bad request, network: try the next model
                last = f"{model}: {type(e).__name__}"
                _log(task, model, version, {}, 0.0, time.time() - t0, "error", _scrub(str(e), c))
                if c and type(e).__name__ in ("AuthenticationError", "PermissionDeniedError"):
                    c.rejected = True
                    raise LLMUnavailable("Your AI key was not accepted by the provider, so this check used the free reader.")
                if not isinstance(e, ValueError):  # JSONDecodeError is a ValueError; anything else goes straight to the next model
                    break
        if out is None:
            continue
        pin, pout = _price(model)
        cost = tok["prompt_tokens"] * pin / 1e6 + tok["completion_tokens"] * pout / 1e6
        _log(task, model, version, tok, cost, time.time() - t0, "ok")
        if budget:
            budget.tokens += tok.get("prompt_tokens", 0) + tok.get("completion_tokens", 0)
        with closing(appdb._c()) as c, c:
            c.execute("INSERT OR REPLACE INTO llm_cache VALUES(?,?,?,?,?,?)", (key, task, version, model, json.dumps(out), appdb.now()))
        return out
    raise LLMUnavailable(f"The AI service did not answer ({last}). Using the simple reader instead.")


def test_key() -> dict:
    """One tiny call with the visitor's key (call inside `use(creds)`). Returns {ok, message}; the message never contains the key."""
    c = current()
    try:
        llm.ask_json('Reply with the JSON object {"ok": true}.', "ping", model=c.model, client=llm.client_for(c.base_url, c.api_key), retries=1)
        return {"ok": True, "message": "The key works."}
    except Exception as e:
        n = type(e).__name__
        msg = {"AuthenticationError": "The provider rejected this key.", "PermissionDeniedError": "This key is not allowed to use that model.",
               "NotFoundError": "The provider does not know that model name.", "APIConnectionError": "Could not reach the provider.",
               "RateLimitError": "The provider says this key is out of quota or going too fast."}.get(n, f"The test call failed ({n}).")
        return {"ok": False, "message": msg}
