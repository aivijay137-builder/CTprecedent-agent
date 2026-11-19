"""What does a pack CHANGE? For the golden designs: route to a pack, run the engine prompt-only and with the pack (AI off, free), and compare.
This describes what changed, not which result is better (that needs the quality eval). Full comparison saved to EVALS/results/.
Run from the Faro folder:  CTG_DB_PATH=<local registry copy> python EVALS/scripts/pack_on_vs_off.py"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
os.environ["LLM_ENABLED"] = "off"
sys.path.insert(0, str(ROOT / "backend" / "golden"))
import make_golden  # noqa: E402
from backend import engine  # noqa: E402
from backend.packlib import compare, loader, merge, router  # noqa: E402

FOCUS = ["population", "endpoints", "size", "sites", "design"]
packs = loader.load_all()
out = {}
for name, brief in make_golden.designs().items():
    cx = engine.Ctx()
    r = router.route(cx, brief, packs)
    eff = merge.merge(packs, r["area"], r["indication"])
    off = engine.run(brief, FOCUS, [])
    off["run_id"] = f"{name}_off"
    on = engine.run(brief, FOCUS, [], pack=eff)
    on["run_id"] = f"{name}_on"
    cmp = compare.compare_runs(off, on)
    out[name] = {"route": {k: r[k] for k in ("indication", "area", "reason")}, "compare": cmp}
    log = on["pack"]
    c = cmp["comparables"]
    print(f"\n=== {name}  ->  {eff['label']}  [{eff['status']}]")
    hf = log["hard_filter"]
    print(f"  hard filter: {'APPLIED, removed ' + str(hf['removed']) if hf['applied'] else ('RELAXED' if hf['relaxed'] else 'not applied')}  ({hf['reason']})")
    g = log["ranking"]
    if g.get("applied"):
        print(f"  ranking hints: design subtypes {g['design_subtypes']}, design endpoint type {g['design_endpoint_type']}; boosted subtype {g['boosted_subtype']}, boosted endpoint type {g['boosted_endpoint_type']}, era-penalised {g['penalised_era']} (of {g['window']} considered)")
    print(f"  comparables: {c['in_both']} in both lists, {c['same_rank']} at the same rank, {len(c['only_a'])} dropped by the pack, {len(c['only_b'])} brought in by the pack")
    for row in c["only_b"][:3]:
        print(f"     + in : #{row['rank_b']:>2} {row['nct_id']} {row['title'][:70]} | {row['why_picked'][-60:]}")
    for row in c["only_a"][:3]:
        print(f"     - out: was #{row['rank_a']:>2} {row['nct_id']} {row['title'][:70]}")
    print(f"  flags: same {cmp['flags']['in_both']}, only prompt-only {cmp['flags']['only_a']}, only with pack {cmp['flags']['only_b']}, n changed {cmp['flags']['n_changed']}")
    print(f"  bottom line: prompt-only '{cmp['a']['sentence']}' | with pack '{cmp['b']['sentence']}'")
(ROOT / "EVALS" / "results").mkdir(exist_ok=True)
(ROOT / "EVALS" / "results" / "pack_on_vs_off_2026-11-09.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
print("\nsaved EVALS/results/pack_on_vs_off_2026-11-09.json")
