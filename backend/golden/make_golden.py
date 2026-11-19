"""Captures the CURRENT (prompt-only) results of the engine for a few designs, with AI off, into golden_base_runs.json.
A test (backend/test_packs_off_is_unchanged.py) later proves the prompt-only path still returns exactly these results once packs exist.
Run once from the Faro folder BEFORE changing the engine:  python backend/golden/make_golden.py
It reads the local registry copy (CTG_DB_PATH), which is not synced locally, so the snapshot stays valid."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from backend import criteria, engine  # noqa: E402
from brief import DesignBrief  # noqa: E402

HF_TEXT = """Inclusion Criteria:
* Age 18 to 85 years
* Left ventricular ejection fraction (LVEF) of 40% or less
* NT-proBNP of at least 600 pg/mL
* Systolic blood pressure of at least 100 mmHg
* eGFR of at least 30 mL/min/1.73 m2
Exclusion Criteria:
* Serum potassium above 5.0 mmol/L
* BMI above 45 kg/m2
"""


def designs():
    import adapters
    out = {"bronchiectasis_nct": adapters.brief_from_nct("NCT03460704")}
    out["heart_failure_form"] = DesignBrief(source="form", condition="Heart Failure", mesh_terms=["Heart Failure"], phase=["PHASE3"], intervention_type=["DRUG"],
                                            eligibility_text=HF_TEXT, primary_endpoint="Time to first cardiovascular death or heart failure hospitalization",
                                            primary_endpoint_timeframe="Up to 30 months", target_enrollment=4500, enrollment_type="ESTIMATED",
                                            countries=["United States", "Germany", "Japan", "Brazil"], arm_types=["EXPERIMENTAL", "PLACEBO_COMPARATOR"])
    out["psoriasis_form"] = DesignBrief(source="form", condition="Psoriasis", mesh_terms=["Psoriasis"], phase=["PHASE3"], intervention_type=["BIOLOGICAL"],
                                        eligibility_text="Inclusion Criteria:\n* Age 18 to 70 years\n* PASI score >= 12\n* BSA involvement >= 10%\n\nExclusion Criteria:\n* Body weight above 140 kg",
                                        primary_endpoint="PASI 75 response at Week 16", primary_endpoint_timeframe="16 weeks", target_enrollment=600, enrollment_type="ESTIMATED",
                                        countries=["United States", "Germany"], arm_types=["EXPERIMENTAL", "PLACEBO_COMPARATOR"])
    for b in out.values():
        b.structured_cutoffs = {"cutoffs": criteria.parse_criteria(b.eligibility_text)}  # the free rule-based reader, as in the no-key flow
    return out


def snapshot(brief):
    r = engine.run(brief, ["population", "endpoints", "size", "sites", "design"], [])
    return {"comparables": [c["nct_id"] for c in r["comparables"]],
            "similarity": [c["similarity"] for c in r["comparables"]],
            "flags": [{"id": f["id"], "n": f["n"], "evidence_ids": f["evidence_ids"]} for f in r["flags"]],
            "bottom_line": r["bottom_line"], "rule_notes": r["rule_notes"]}


if __name__ == "__main__":
    os.environ["LLM_ENABLED"] = "off"  # no AI: the snapshot must be repeatable
    snap = {k: snapshot(b) for k, b in designs().items()}
    for k, v in snap.items():
        print(k, len(v["comparables"]), "comparables;", [f["id"] for f in v["flags"]], v["bottom_line"]["sentence"])
    (Path(__file__).parent / "golden_base_runs.json").write_text(json.dumps(snap, indent=1), encoding="utf-8")
    print("saved golden_base_runs.json")
