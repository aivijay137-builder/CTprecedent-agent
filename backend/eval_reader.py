"""Scores the eligibility readers against backend/golden/reader_gold.json (40 real texts, 120 labelled limits).

  python -m backend.eval_reader            # the free rule-based reader (criteria.parse_criteria), no key needed
  python -m backend.eval_reader --llm      # the AI reader (readers.parse_design); needs LLM_* in .env, makes paid calls

Two match levels, one-to-one per text:
  strict  same key AND same value            (naming and number both right)
  loose   same direction (min/max) AND value (number right, name may differ: "fev1_max" vs "fev1_pct_predicted_max")
Source check: of the loose matches, how many quote the sentence the gold label points to.
Precision ignores reader outputs in a time unit (days/weeks/months) other than age: windows are out of the gold scope.
Writes backend/golden/reader_score_<mode>.json with every miss and extra, so the numbers can be audited.
"""
import json
import re
import sys
from pathlib import Path

from . import criteria

GOLD = Path(__file__).resolve().parent / "golden" / "reader_gold.json"
TIME_UNITS = re.compile(r"^(day|week|month|year|hour|minute)s?$", re.I)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\\", "", s or "")).strip().lower()


def _dir(key: str) -> str:
    return "min" if key == "min_age" or key.endswith("_min") else "max" if key == "max_age" or key.endswith("_max") else "?"


def _val(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _in_scope(c: dict) -> bool:
    return c["key"] in ("min_age", "max_age") or not TIME_UNITS.match((c.get("unit") or "").strip())


def _same_src(c: dict, frag: str) -> bool:
    s, f = _norm(c.get("source_sentence")), _norm(frag)
    return bool(s) and (f in s or s in f)


def score_text(item: dict, got: list[dict]) -> dict:
    gold = item["limits"]
    got = [g for g in got if g.get("valid", True) and _in_scope(g)]
    strict = loose = src = 0
    used, missed = set(), []
    for g in gold:
        hit = None
        for level, ok in (("strict", lambda c: c["key"] == g["key"] and _val(c["value"]) == _val(g["value"])),
                          ("loose", lambda c: _dir(c["key"]) == _dir(g["key"]) and _val(c["value"]) == _val(g["value"]))):
            hit = next((i for i, c in enumerate(got) if i not in used and ok(c)), None)
            if hit is not None:
                strict += level == "strict"
                break
        if hit is None:
            missed.append(g)
            continue
        used.add(hit)
        loose += 1
        src += _same_src(got[hit], g["fragment"])
    extras = [c for i, c in enumerate(got) if i not in used]
    return {"gold": len(gold), "got": len(got), "strict": strict, "loose": loose, "source": src, "missed": missed,
            "extras": [{"key": c["key"], "value": c["value"], "unit": c.get("unit", ""), "source_sentence": c.get("source_sentence", "")[:140]} for c in extras]}


def run(reader) -> dict:
    data = json.loads(GOLD.read_text(encoding="utf-8"))
    rows = []
    for it in data["items"]:
        r = score_text(it, reader(it))
        rows.append({"nct_id": it["nct_id"], **r})
    g, o = sum(r["gold"] for r in rows), sum(r["got"] for r in rows)
    st, lo, sr = (sum(r[k] for r in rows) for k in ("strict", "loose", "source"))
    div = lambda a, b: round(a / b, 3) if b else None  # noqa: E731
    return {"texts": len(rows), "gold_limits": g, "reader_outputs": o,
            "strict_recall": div(st, g), "strict_precision": div(st, o), "loose_recall": div(lo, g), "loose_precision": div(lo, o),
            "source_match": div(sr, lo), "rows": rows}


EDGE = GOLD.parent / "reader_edge.json"


def run_edge(reader) -> dict:
    """No-limit and hostile-text cases: a case passes only if every in-scope output matches an `allowed` limit."""
    rows = []
    for it in json.loads(EDGE.read_text(encoding="utf-8"))["items"]:
        got = [g for g in reader(it) if g.get("valid", True) and _in_scope(g)]
        bad = [g for g in got if not any(_dir(g["key"]) == _dir(a["key"]) and _val(g["value"]) == _val(a["value"]) for a in it["allowed"])]
        rows.append({"id": it["id"], "kind": it["kind"], "passed": not bad, "bad": [{"key": g["key"], "value": g["value"]} for g in bad]})
    out = {}
    for k in ("no_limit", "hostile"):
        r = [x for x in rows if x["kind"] == k]
        out[k] = {"cases": len(r), "passed": sum(x["passed"] for x in r)}
    return {**out, "rows": rows}


def rules_reader(item):
    return criteria.parse_criteria(item["text"])


FAILED = []  # texts where every model in the chain failed: scored as "returned nothing", and counted so the failure rate is visible


def llm_reader(item):
    from . import llmsvc, readers
    try:
        return readers.parse_design(item["text"], item["condition"])
    except llmsvc.LLMUnavailable as e:
        FAILED.append({"id": item.get("nct_id") or item.get("id"), "error": str(e)[:200]})
        return []


def main():
    mode = "llm" if "--llm" in sys.argv else "rules"
    if mode == "llm":
        from . import llmsvc
        if not llmsvc.enabled():
            sys.exit("AI reader is off: set LLM_BASE_URL, LLM_API_KEY, LLM_MODEL and LLM_ENABLED=on in .env")
    rd = llm_reader if mode == "llm" else rules_reader
    if "--edge" in sys.argv:  # edge cases only (cheap): does not touch the saved 40-text scores
        e = run_edge(rd)
        print({k: e[k] for k in ("no_limit", "hostile")}, "failed calls:", FAILED)
        for r in e["rows"]:
            print(" ", r["id"], "PASS" if r["passed"] else f"FAIL {r['bad']}")
        (GOLD.parent / f"reader_edge_score_{mode}.json").write_text(json.dumps({**e, "failed_calls": FAILED}, indent=1), encoding="utf-8")
        return
    res = run(rd)
    res["edge"] = run_edge(rd)
    res["failed_calls"] = FAILED
    (GOLD.parent / f"reader_score_{mode}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Reader: {mode}   texts: {res['texts']}   gold limits: {res['gold_limits']}   reader outputs (in scope): {res['reader_outputs']}")
    for k in ("strict_recall", "strict_precision", "loose_recall", "loose_precision", "source_match"):
        print(f"  {k:17} {res[k]:.1%}" if res[k] is not None else f"  {k:17} n/a")
    for k in ("no_limit", "hostile"):
        print(f"  edge {k:9} {res['edge'][k]['passed']}/{res['edge'][k]['cases']} passed")
    print(f"  calls that failed on every model: {len(FAILED)} {[f['id'] for f in FAILED]}")
    print("Texts with most misses:", ", ".join(f"{r['nct_id']}({len(r['missed'])})" for r in sorted(res["rows"], key=lambda r: -len(r["missed"]))[:5]))


if __name__ == "__main__":
    main()
