"""Builds backend/golden/agent_cases.json: 30 real registry trials used as drafts, each one "insufficient" (fewer than 5 comparables)
with brute-force ground truth: how many comparables it would have under every relaxation.  Reads the registry; needs no AI.
Run from the Faro folder:  python -m backend.golden.make_agent_cases      (about a minute; seeded, so repeatable on the same registry)

Selection: draft = a real interventional trial that has MeSH terms; the pool is the real registry minus that trial.
Strata (fixed counts, then lowest nct_id first within each): solved by phase only, by condition_level only, by either alone, only by both together, unsolvable.
"""
import json
import os
import sys
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from backend import engine, relax  # noqa: E402
import adapters  # noqa: E402

OUT = Path(__file__).parent / "agent_cases.json"
SAMPLE = 3000
WANT = {"phase": 8, "condition_level": 7, "either": 5, "both": 2, "unsolvable": 8}  # 30 cases; "both" = only the two together reach 5
MIN_N = 5


def subsets():
    return [()] + [c for n in (1, 2) for c in combinations(relax.RELAX, n)]


def main():
    os.environ["LLM_ENABLED"] = "off"
    cx = engine.Ctx()
    # draft pool: interventional trials with MeSH terms whose condition has a small pool (so insufficiency is common), seeded sample
    ids = [r[0] for r in cx.con.execute(f"""
WITH pool AS (SELECT c.term, count(DISTINCT s.nct_id) n FROM study_conditions c JOIN studies_current s USING (nct_id)
              WHERE c.kind='mesh' AND s.study_type='INTERVENTIONAL' GROUP BY 1),
     small AS (SELECT c.nct_id, min(p.n) m FROM study_conditions c JOIN pool p ON p.term=c.term WHERE c.kind='mesh' GROUP BY 1 HAVING min(p.n) BETWEEN 1 AND 80)
SELECT s.nct_id FROM studies_current s JOIN small USING (nct_id) WHERE s.study_type='INTERVENTIONAL' AND s.phases IS NOT NULL
ORDER BY hash(s.nct_id) LIMIT {SAMPLE}""").fetchall()]
    found = {k: [] for k in WANT}
    seen = 0
    for nct in sorted(ids):
        b = adapters.brief_from_nct(nct, cx.con)
        if not b.mesh_terms:
            continue
        seen += 1
        base = relax.count(cx, b)
        if base >= MIN_N:
            continue
        parent = relax.parent_term(cx, b)
        counts = {"+".join(s) or "none": relax.count(cx, b, s, parent) for s in subsets()}
        solved = {k for k, v in counts.items() if k != "none" and v >= MIN_N}
        key = ("unsolvable" if not solved else "phase" if "phase" in solved and "condition_level" not in solved else
               "condition_level" if "condition_level" in solved and "phase" not in solved else "both" if "phase+condition_level" in solved and not ({"phase", "condition_level"} & solved) else "either")
        if key in found:
            found[key].append({"nct_id": nct, "condition": b.condition, "mesh_terms": b.mesh_terms, "phase": b.phase, "parent_term": parent,
                               "counts": counts, "solvable_by": sorted(solved)})
    print("trials examined:", seen, "| strata available:", {k: len(v) for k, v in found.items()})
    cases = [c for k, n in WANT.items() for c in sorted(found[k], key=lambda c: c["nct_id"])[:n]]
    OUT.write_text(json.dumps({"min_n": MIN_N, "relaxations": list(relax.RELAX), "registry_note": "counts are as of the registry copy used to build this file; they drift with each sync",
                               "cases": cases}, indent=1, ensure_ascii=False), encoding="utf-8")
    print("wrote", OUT.name, len(cases), "cases")


if __name__ == "__main__":
    main()
