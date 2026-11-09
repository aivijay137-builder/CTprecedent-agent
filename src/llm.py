"""One door to any OpenAI-compatible LLM provider. Settings come from .env only."""
import json, os, re, threading, time
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, BadRequestError

load_dotenv()


def client_for(base_url: str, api_key: str):
    # a hung provider must fail fast (the library default is 10 minutes), so the app can fall back to the free reader
    return OpenAI(base_url=base_url, api_key=api_key, timeout=float(os.environ.get("LLM_TIMEOUT_S", 60)), max_retries=1)


def _client():
    return client_for(os.environ["LLM_BASE_URL"], os.environ["LLM_API_KEY"])


def _parse(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)  # strip ```json fences / chatter
        if not m:
            raise
        return json.loads(m.group(0))


_last_call = 0.0
_lock = threading.Lock()


def _pace():
    """Wait so we never exceed LLM_RPM requests per minute (free tiers are strict)."""
    global _last_call
    with _lock:  # threads take turns, so the spacing holds with parallel calls
        wait = _last_call + 60 / float(os.environ.get("LLM_RPM", 20)) - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()


def _retry_after(msg: str, default: float) -> float:
    """Providers say how long to wait ("try again in 1m3.5s" / "15.8s"); obey it, plus a second."""
    m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", msg)
    return (int(m.group(1) or 0) * 60 + float(m.group(2)) + 1) if m else default


def ask_json(system: str, user: str, model: str = None, client=None, retries: int = 8) -> tuple[dict, dict]:
    """Returns (parsed_json, {"prompt_tokens": n, "completion_tokens": n})."""
    client = client or _client()
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    kw = {"model": model or os.environ["LLM_MODEL"], "messages": msgs, "temperature": 0}
    json_mode = True
    for i in range(retries):
        _pace()
        try:
            r = client.chat.completions.create(
                **kw, **({"response_format": {"type": "json_object"}} if json_mode else {}))
            u = r.usage
            return _parse(r.choices[0].message.content), {
                "prompt_tokens": u.prompt_tokens if u else 0,
                "completion_tokens": u.completion_tokens if u else 0}
        except RateLimitError as e:
            if i == retries - 1:
                raise
            wait = _retry_after(str(e), 2 ** i)
            if wait > 300:  # a daily cap, not a per-minute one: waiting here is pointless, fail fast
                raise
            time.sleep(wait)
        except BadRequestError:
            if not json_mode:
                raise
            json_mode = False  # provider rejects JSON mode -> plain text + parsing
    raise RuntimeError("unreachable")
