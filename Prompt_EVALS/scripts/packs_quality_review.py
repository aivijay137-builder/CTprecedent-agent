"""Quality review across all draft packs: what each pack found, and what looks weak. Prints a table. Read-only.
Run from the Faro folder:  python Prompt_EVALS/scripts/packs_quality_review.py"""
import glob
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
print(f"{'pack':26s} {'trials':>7s} {'ph2/3':>6s} {'era_yr':>6s} {'subs<30':>7s} {'flds<30':>7s} {'norms_lowN':>10s} {'p3_term':>7s} {'p3_enr_med':>10s}")
issues = []
for f in sorted(glob.glob(str(ROOT / "Prompts/packs/*/*.yaml"))):
    p = yaml.safe_load(open(f, encoding="utf-8"))
    cov = p["routing"]["coverage"]
    era = p["era_breakpoints"][0]["proposed_year"]
    ss = sum(1 for s in p["subtypes"] if s["n_trials"] < 30)
    ff = sum(1 for x in p["extraction_fields"] if x["n_trials_mentioning"] < 30)
    nl = f'{sum(1 for n in p["cutoff_norms"] if n["low_n"])}/{len(p["cutoff_norms"])}'
    d = p["design_norms"]["phase3"]
    t = p["outcome_priors"]["phase3"]["termination_rate"]["rate"]
    print(f"{p['id']:26s} {cov['n_interventional']:7d} {cov['n_phase2_or_3']:6d} {str(era):>6s} {ss:7d} {ff:7d} {nl:>10s} {str(t):>7s} {str(d['enrollment_actual'].get('p50')):>10s}")
    if era is None:
        issues.append(f"{p['id']}: no era breakpoint found")
    elif era <= 2006:
        issues.append(f"{p['id']}: era breakpoint {era} looks too early to be a standard-of-care shift")
    if ss or ff:
        issues.append(f"{p['id']}: {ss} subtypes and {ff} fields rest on fewer than 30 trials")
print("\nthings to review:")
for i in issues:
    print(" -", i)
