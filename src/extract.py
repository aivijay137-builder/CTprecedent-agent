"""Step 2: pull eligibility cutoffs out of free text with an LLM.

Commands (run from the Faro folder):
  python src/extract.py pilot            20 trials x 2 models, comparison table, cost estimate, then STOP
  python src/extract.py sample [N]       random N trials (default 200), then build copd_cutoffs
  python src/extract.py full [--alt]     all rows with the chosen model (resumable; cached results are skipped)
  python src/extract.py build [--alt]    (re)build the copd_cutoffs table from the cache
"""
import csv, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import duckdb
import pandas as pd
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError
from typing import Literal, Optional, Union
import llm

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "precedent.duckdb"
LOG = ROOT / "data" / "extract_log.csv"
PROMPT_VERSION = "v3"
NS = "not stated"

NUM_FIELDS = ["min_age", "max_age", "fev1_pct_predicted_min", "fev1_pct_predicted_max",
              "fev1_fvc_ratio_max", "exacerbations_prior_year_min", "smoking_pack_years_min"]
CAT_FIELDS = ["current_smokers_allowed", "asthma_excluded"]
FIELDS = NUM_FIELDS + CAT_FIELDS

SYSTEM = f"""You extract eligibility cutoffs from a clinical trial's eligibility text (COPD trials).
Return JSON only, with exactly these keys: {", ".join(FIELDS)}.
Each key maps to an object: {{"value": ..., "unit": ..., "source_sentence": ...}}.
Rules:
- If a field is not stated in the text, use {{"value": "{NS}", "unit": null, "source_sentence": null}}. NEVER guess or infer.
- source_sentence must be copied EXACTLY, character for character, from the text (the sentence or bullet that states it).
- Numeric fields: value is a plain number (no symbols). unit is e.g. "years", "% predicted", "ratio", "exacerbations", "pack-years".
  DIRECTION MATTERS for every min/max field: "at least"/">="/"greater than" is a MIN only; "less than"/"<"/"up to" is a MAX only;
  "between A and B" gives min=A and max=B. Never put a "less than" limit in a min field (leave the other bound "{NS}").
  min_age/max_age: age in years. fev1_pct_predicted_min/max: lower/upper bound of FEV1 as % of predicted
  (use the post-bronchodilator value if the text says so). fev1_fvc_ratio_max: upper limit of FEV1/FVC (e.g. 0.70); if given as a percent (70%), write it as a fraction (0.70).
  exacerbations_prior_year_min: minimum number of exacerbations in the prior year required to enter.
  smoking_pack_years_min: minimum smoking history in pack-years required.
- current_smokers_allowed: "yes" if current smokers may enroll, "no" if they are excluded or must be ex-smokers, else "{NS}".
- asthma_excluded: "yes" if a diagnosis of asthma excludes the person, "no" if asthma is explicitly allowed, else "{NS}"."""


# ---------- schema ----------
class Field(BaseModel):
    value: Union[float, str, None] = NS
    unit: Optional[str] = None
    source_sentence: Optional[str] = None


class Extraction(BaseModel):
    min_age: Field
    max_age: Field
    fev1_pct_predicted_min: Field
    fev1_pct_predicted_max: Field
    fev1_fvc_ratio_max: Field
    exacerbations_prior_year_min: Field
    smoking_pack_years_min: Field
    current_smokers_allowed: Field
    asthma_excluded: Field


def norm(t: str) -> str:
    """Collapse all whitespace so line breaks in the source don't break the quote check."""
    t = re.sub(r"\\(?=[^\w\s])", "", t or "")  # CT.gov stores "<" as "\<"; models quote it plain
    return re.sub(r"\s+", " ", t).strip()


def check(ext: Extraction, text: str) -> dict:
    """Judge each field: not_stated / ok / invalid (quote not found, or bad value)."""
    src, out = norm(text), {}
    for f in FIELDS:
        fv: Field = getattr(ext, f)
        v = None if fv.value in (None, "") else fv.value
        if v is None or (isinstance(v, str) and v.strip().lower() == NS):
            out[f] = dict(value=NS, unit=None, source_sentence=None, status="not_stated")
            continue
        ok = bool(fv.source_sentence) and norm(fv.source_sentence) in src
        if f in CAT_FIELDS:
            ok = ok and str(v).lower() in ("yes", "no")
        else:
            try:
                v = float(v)  # model sometimes returns "0.7" as text
            except (TypeError, ValueError):
                ok = False
        out[f] = dict(value=v, unit=fv.unit, source_sentence=fv.source_sentence,
                      status="ok" if ok else "invalid")
    return out


# ---------- one trial ----------
def extract_one(text: str, model: str):
    """Returns (checked_fields or None, tokens, seconds). One retry on bad JSON / bad shape."""
    tok, t0 = {"prompt_tokens": 0, "completion_tokens": 0}, time.time()
    for attempt in range(2):
        try:
            raw, t = llm.ask_json(SYSTEM, "ELIGIBILITY TEXT:\n" + text, model=model)
            for k in tok:
                tok[k] += t[k]
            return check(Extraction.model_validate(raw), text), tok, time.time() - t0
        except (json.JSONDecodeError, ValidationError, TypeError) as e:
            print(f"   bad output (attempt {attempt + 1}): {type(e).__name__}")
    return None, tok, time.time() - t0


def prices(model: str):
    alt = model == os.environ.get("LLM_MODEL_ALT")
    s = "_ALT" if alt else ""
    pi, po = os.environ.get("LLM_PRICE_IN" + s), os.environ.get("LLM_PRICE_OUT" + s)
    return (float(pi), float(po)) if pi and po else None


def log_call(nct, model, tok, secs, status):
    p = prices(model)
    cost = (tok["prompt_tokens"] * p[0] + tok["completion_tokens"] * p[1]) / 1e6 if p else ""
    new = not LOG.exists()
    with open(LOG, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "nct_id", "model", "prompt_version", "prompt_tokens",
                        "completion_tokens", "cost_usd", "seconds", "status"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), nct, model, PROMPT_VERSION,
                    tok["prompt_tokens"], tok["completion_tokens"], cost, round(secs, 2), status])


# ---------- cache ----------
def db():
    con = duckdb.connect(str(DB))
    con.execute("""CREATE TABLE IF NOT EXISTS cutoffs_cache(
        nct_id VARCHAR, model VARCHAR, prompt_version VARCHAR, status VARCHAR, result VARCHAR,
        prompt_tokens INT, completion_tokens INT, seconds DOUBLE, extracted_at TIMESTAMP,
        PRIMARY KEY(nct_id, model, prompt_version))""")
    return con


def run(con, ids, model, label=""):
    """Extract every id not yet cached for this model+prompt. Returns stats."""
    texts = dict(con.execute("SELECT nct_id, eligibility_text FROM copd_trials").fetchall())
    done = {r[0] for r in con.execute(
        "SELECT nct_id FROM cutoffs_cache WHERE model=? AND prompt_version=?", [model, PROMPT_VERSION]).fetchall()}
    todo = [i for i in ids if i not in done]
    print(f"[{label or model}] {len(ids)} requested, {len(ids) - len(todo)} already cached, {len(todo)} to call")
    def work(nct):
        text = texts[nct]
        if not norm(text):
            return nct, None, {"prompt_tokens": 0, "completion_tokens": 0}, 0, "no_text"
        try:
            res, tok, secs = extract_one(text, model)
        except Exception as e:  # e.g. rate limit that outlasted all retries: don't cache, retry on next run
            print(f"   {nct}: API error, not cached ({type(e).__name__})")
            return nct, None, None, 0, "error"
        return nct, res, tok, secs, "ok" if res else "failed"

    # Several requests in flight at once (waiting on the provider is the slow part).
    # Only this main thread writes to the DB and the log; llm._pace() still enforces LLM_RPM.
    workers = int(os.environ.get("LLM_WORKERS", 4))
    pool = ThreadPoolExecutor(max_workers=workers)
    for n, fut in enumerate(as_completed([pool.submit(work, i) for i in todo]), 1):
        nct, res, tok, secs, status = fut.result()
        if status == "error":
            continue
        con.execute("INSERT INTO cutoffs_cache VALUES (?,?,?,?,?,?,?,?,?)",
                    [nct, model, PROMPT_VERSION, status, json.dumps(res) if res else None,
                     tok["prompt_tokens"], tok["completion_tokens"], secs, datetime.now()])
        if status != "no_text":
            log_call(nct, model, tok, secs, status)
        if n % 25 == 0 or n == len(todo):
            print(f"   {n}/{len(todo)} done")


def stats(con, ids, model):
    q = ",".join("'%s'" % i for i in ids)
    r = con.execute(f"""SELECT count(*), sum(prompt_tokens), sum(completion_tokens), sum(seconds),
        count(*) FILTER (WHERE status='ok'), count(*) FILTER (WHERE status='failed'), count(*) FILTER (WHERE status='no_text')
        FROM cutoffs_cache WHERE model=? AND prompt_version=? AND nct_id IN ({q})""",
                      [model, PROMPT_VERSION]).fetchone()
    p = prices(model)
    cost = (r[1] * p[0] + r[2] * p[1]) / 1e6 if p else None
    return dict(n=r[0], pt=r[1] or 0, ct=r[2] or 0, secs=r[3] or 0, ok=r[4], failed=r[5], no_text=r[6], cost=cost)


def results(con, ids, model):
    q = ",".join("'%s'" % i for i in ids)
    return {n: json.loads(r) for n, r in con.execute(
        f"SELECT nct_id, result FROM cutoffs_cache WHERE model=? AND prompt_version=? AND result IS NOT NULL AND nct_id IN ({q})",
        [model, PROMPT_VERSION]).fetchall()}


# ---------- pilot ----------
def pilot():
    con = db()
    main, alt = os.environ["LLM_MODEL"], os.environ["LLM_MODEL_ALT"]
    total = con.execute("SELECT count(*) FROM copd_trials WHERE length(trim(coalesce(eligibility_text,'')))>0").fetchone()[0]
    ids = [r[0] for r in con.execute("""SELECT nct_id FROM copd_trials WHERE length(trim(coalesce(eligibility_text,'')))>0
        ORDER BY hash(nct_id || 'pilot') LIMIT 20""").fetchall()]
    print(f"Trials with eligibility text: {total}. Pilot sample: {len(ids)}")
    for m in (main, alt):
        run(con, ids, m)
    A, B = results(con, ids, main), results(con, ids, alt)

    # per-field comparison
    print(f"\n=== Disagreements per field (A={main}, B={alt}) ===")
    rows, dis = [], []
    for f in FIELDS:
        both = [n for n in ids if n in A and n in B]
        d = [n for n in both if (A[n][f]["value"], A[n][f]["status"]) != (B[n][f]["value"], B[n][f]["status"])]
        found = lambda R: sum(1 for n in R if R[n][f]["status"] == "ok")
        rows.append((f, found(A), found(B), len(d), len(both)))
        dis += [(n, f, A[n][f], B[n][f]) for n in d]
    print(pd.DataFrame(rows, columns=["field", "A found", "B found", "disagree", "compared"]).to_string(index=False))
    print("\nDisagreement detail (value / status):")
    for n, f, a, b in dis:
        print(f"  {n} {f}: A={a['value']} [{a['status']}]  B={b['value']} [{b['status']}]")

    # cost / time
    print("\n=== Cost and time (20 trials) ===")
    full_n = total
    for name, m in (("A", main), ("B", alt)):
        s = stats(con, ids, m)
        n_called = s["n"] - s["no_text"]
        line = f"{name} {m}: ok={s['ok']} failed={s['failed']} no_text={s['no_text']} tokens in/out={s['pt']}/{s['ct']} time={s['secs']:.0f}s"
        if s["cost"] is not None and n_called:
            per = s["cost"] / n_called
            line += f" cost=${s['cost']:.4f} (${per:.5f}/trial) -> FULL RUN est. ${per * full_n:.2f} for {full_n} trials"
        else:
            line += " cost=unknown (set LLM_PRICE_IN/OUT in .env)"
        print(line)
    mins = full_n / float(os.environ.get("LLM_RPM", 20))
    print(f"Pacing at LLM_RPM={os.environ.get('LLM_RPM', 20)}: a full run needs ~{mins:.0f} minutes (~{mins / 60:.1f} h) per model.")
    print("\nSTOP: pick the model, then run: python src/extract.py full [--alt]")


# ---------- build final table ----------
def build(use_alt=False):
    """copd_cutoffs = one row per trial from the cache. Prefers the main model's result
    (or the alt model's with --alt); falls back to the other model. The model column says which."""
    con = db()
    pref = os.environ["LLM_MODEL_ALT" if use_alt else "LLM_MODEL"]
    rows = []
    for nct, status, res, model in con.execute(
            """SELECT nct_id, status, result, model FROM cutoffs_cache WHERE prompt_version=?
               QUALIFY row_number() OVER (PARTITION BY nct_id ORDER BY (model=?) DESC, (status='ok') DESC) = 1""",
            [PROMPT_VERSION, pref]).fetchall():
        r = {"nct_id": nct, "status": status, "model": model, "prompt_version": PROMPT_VERSION}
        for f in FIELDS:
            x = json.loads(res)[f] if res else {}
            r[f + "_value"] = None if not x else str(x["value"])
            r[f + "_unit"] = x.get("unit")
            r[f + "_source"] = x.get("source_sentence")
            r[f + "_status"] = x.get("status")
        rows.append(r)
    df = pd.DataFrame(rows)  # noqa: F841 (used by DuckDB below)
    con.execute("CREATE OR REPLACE TABLE copd_cutoffs AS SELECT * FROM df")
    total = con.execute("SELECT count(*) FROM copd_trials").fetchone()[0]
    print(f"copd_cutoffs: {len(df)} of {total} trials have a status (not all trials were extracted - sample only)")
    print(df.groupby(["model", "status"]).size().to_string())
    for f in FIELDS:
        print(f"  {f}: " + ", ".join(f"{k}={v}" for k, v in df[f + "_status"].value_counts().items()))


def full(use_alt=False):
    con = db()
    model = os.environ["LLM_MODEL_ALT" if use_alt else "LLM_MODEL"]
    ids = [r[0] for r in con.execute("SELECT nct_id FROM copd_trials ORDER BY nct_id").fetchall()]
    run(con, ids, model, "full")
    build(use_alt)


def sample(n=200, use_alt=False):
    """Random n trials with eligibility text (fixed seed), then build copd_cutoffs from the cache.
    With --alt: run only the trials the main model has not already done, using the alt model."""
    con = db()
    main = os.environ["LLM_MODEL"]
    ids = [r[0] for r in con.execute(f"""SELECT nct_id FROM copd_trials
        WHERE length(trim(coalesce(eligibility_text,'')))>0 ORDER BY hash(nct_id || 'sample') LIMIT {n}""").fetchall()]
    model = main
    if use_alt:
        model = os.environ["LLM_MODEL_ALT"]
        done = {r[0] for r in con.execute("SELECT nct_id FROM cutoffs_cache WHERE model=? AND prompt_version=?",
                                          [main, PROMPT_VERSION]).fetchall()}
        ids = [i for i in ids if i not in done]
    run(con, ids, model, f"sample {n}" + (" (alt model, remaining only)" if use_alt else ""))
    con.close()
    build()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    alt = "--alt" in sys.argv
    {"pilot": pilot, "full": lambda: full(alt), "build": lambda: build(alt),
     "sample": lambda: sample(int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 200, alt)}.get(cmd, lambda: print(__doc__))()
