"""Proves the pack validator can FAIL: six deliberately broken copies of a good pack must each be rejected.
Run from the Faro folder:  python EVALS/scripts/packs_negative_tests.py   (exit status 1 if any broken pack slips through)"""
import copy
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
from packs.schema import Pack  # noqa: E402

good = yaml.safe_load((ROOT / "Prompts/packs/areas/cardiovascular.yaml").read_text(encoding="utf-8"))
Pack(**good)  # the original must pass
print("original cardiovascular pack: valid")
tests = {
    "number without an n in design_norms": lambda d: d["design_norms"]["phase3"].update({"mystery": {"p50": 5.0}}),
    "rule without a rationale": lambda d: d["subtypes"][0].update({"rationale": ""}),
    "rule without evidence": lambda d: d["subtypes"][0].pop("evidence"),
    "hard filter without a fallback rank": lambda d: d["intervention_split"].pop("relax_rank"),
    "prompt add-on over 150 words": lambda d: d.update({"prompt_addon": "word " * 160}),
    "wrong low_n flag (n=5 but low_n false)": lambda d: d["cutoff_norms"][-1].update({"low_n": False, "n": 5}),
}
missed = 0
for name, mutate in tests.items():
    d = copy.deepcopy(good)
    mutate(d)
    try:
        Pack(**d)
        print(f"NOT CAUGHT: {name}")
        missed += 1
    except Exception as e:
        print(f"caught: {name}  ->  {str(e).splitlines()[1].strip()[:80] if len(str(e).splitlines()) > 1 else str(e)[:80]}")
print(f"{len(tests) - missed} of {len(tests)} broken packs rejected")
sys.exit(1 if missed else 0)
