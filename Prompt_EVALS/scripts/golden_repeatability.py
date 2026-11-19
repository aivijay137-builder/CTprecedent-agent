"""Is the golden snapshot repeatable? Re-runs the prompt-only engine (AI off) on the three golden designs and compares with the saved
snapshot (backend/golden/golden_base_runs.json). Does NOT overwrite it. Exit status 1 if anything differs.
Run from the Faro folder:  CTG_DB_PATH=<local registry copy> python EVALS/scripts/golden_repeatability.py"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend" / "golden"))
import os  # noqa: E402

os.environ["LLM_ENABLED"] = "off"  # no AI: the snapshot must be repeatable
import make_golden  # noqa: E402  (sets up the import paths)

saved = json.loads((ROOT / "backend" / "golden" / "golden_base_runs.json").read_text(encoding="utf-8"))
bad = 0
for name, brief in make_golden.designs().items():
    now = make_golden.snapshot(brief)
    old = saved[name]
    same = json.dumps(now, sort_keys=True) == json.dumps(old, sort_keys=True)
    print(f"{name}: {'IDENTICAL' if same else 'DIFFERENT'}  ({len(now['comparables'])} comparables, flags {[f['id'] for f in now['flags']]})")
    if not same:
        bad += 1
        for k in now:
            if now[k] != old[k]:
                print("   differs in:", k)
print("golden snapshot is repeatable" if not bad else f"{bad} design(s) differ")
sys.exit(1 if bad else 0)
