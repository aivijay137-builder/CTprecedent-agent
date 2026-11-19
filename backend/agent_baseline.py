"""The baseline an "Investigate" agent has to beat (docs/agent_design.md): a fixed ladder, no AI, no cost.
Try, in order: loosen the phase; widen the condition; do both. Suggest the first that gives at least 5 comparables, else say nothing works.
Scores itself on backend/golden/agent_cases.json (30 real insufficient designs with brute-force ground truth).
  python -m backend.agent_baseline
"""
import json
import os
import sys
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
import adapters  # noqa: E402
from backend import engine, relax  # noqa: E402

CASES = Path(__file__).parent / "golden" / "agent_cases.json"
LADDER = [("phase",), ("condition_level",), ("phase", "condition_level")]
BIG = 100  # a suggestion that pulls in more than this many trials has become a different cohort; a flag for review, not a verdict


def ladder(cx, brief, min_n=5):
    """(relaxations, n_after) for the first rung that reaches min_n, or (None, n_without_relaxing)."""
    parent = relax.parent_term(cx, brief)
    for rung in LADDER:
        n = relax.count(cx, brief, rung, parent)
        if n >= min_n:
            return rung, n
    return None, relax.count(cx, brief)


def smallest(cx, brief, min_n=5):
    """Reference only: of every rung that reaches min_n, the one with the fewest trials (the least departure from the draft)."""
    parent = relax.parent_term(cx, brief)
    ok = [(relax.count(cx, brief, r, parent), r) for r in LADDER]
    ok = [x for x in ok if x[0] >= min_n]
    return (min(ok)[1], min(ok)[0]) if ok else (None, 0)


def main():
    os.environ["LLM_ENABLED"] = "off"
    data = json.loads(CASES.read_text(encoding="utf-8"))
    cx, rows = engine.Ctx(), []
    for c in data["cases"]:
        b = adapters.brief_from_nct(c["nct_id"], cx.con)
        got, n = ladder(cx, b, data["min_n"])
        ref, ref_n = smallest(cx, b, data["min_n"])
        rows.append({"nct_id": c["nct_id"], "solvable": bool(c["solvable_by"]), "baseline": "+".join(got) if got else None, "n_after": n,
                     "smallest": "+".join(ref) if ref else None, "smallest_n": ref_n})
    solv = [r for r in rows if r["solvable"]]
    uns = [r for r in rows if not r["solvable"]]
    res = {"cases": len(rows), "solvable": len(solv), "unsolvable": len(uns),
           "success_on_solvable": sum(r["baseline"] is not None for r in solv) / len(solv),
           "honest_on_unsolvable": sum(r["baseline"] is None for r in uns) / len(uns),
           "n_after_median": median(r["n_after"] for r in solv if r["baseline"]), "n_after_max": max(r["n_after"] for r in solv if r["baseline"]),
           "share_over_BIG": sum(r["n_after"] > BIG for r in solv if r["baseline"]) / len(solv),
           "same_rung_as_smallest": sum(r["baseline"] == r["smallest"] for r in solv) / len(solv),
           "median_smallest_n": median(r["smallest_n"] for r in solv), "rows": rows}
    (CASES.parent / "agent_baseline_score.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    for k, v in res.items():
        if k != "rows":
            print(f"{k:26} {v if not isinstance(v, float) else round(v, 3)}")


if __name__ == "__main__":
    main()
