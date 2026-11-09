"""Generates backend/fixtures/*.json (illustrative data, NOT real trials). Run: python backend/make_fixtures.py"""
import json
import random
from pathlib import Path

OUT = Path(__file__).parent / "fixtures"
DRUGS = ["Zelvarotide", "Brenvalimab", "Tiotex-2", "Orlavent", "Pulmaris", "Nebuvir-5", "Axilumab",
         "Revoterol", "Glycoquin", "Inhalar-9", "Dupexil", "Ventrolan", "Mepolex", "Airvanta"]
SPONSORS = ["Northgate Pharma", "Helio Biosciences", "Meridian Therapeutics", "Altura Health", "Quill Respiratory"]


def F(text, ids):
    return {"text": text, "n": len(ids), "evidence_ids": ids}


def bucket(c):
    s = c["status"]
    if s == "COMPLETED":
        return "completed_results" if c["has_results"] else "completed_no_results"
    return {"TERMINATED": "terminated", "WITHDRAWN": "withdrawn", "UNKNOWN": "unknown"}.get(s, "running")


def build(cfg):
    r = random.Random(cfg["seed"])
    comps, k = [], 0
    why = cfg["why"]

    def add(status, has_results):
        nonlocal k
        k += 1
        comps.append(dict(
            nct_id=f"NCT{cfg['nct0'] + k:08d}",
            title=f"{DRUGS[(k * 5) % len(DRUGS)]} versus placebo in {cfg['title_cond']}",
            why_picked=why[(k * 3) % len(why)], similarity=round(r.uniform(0.62, 0.96), 2),
            status=status, stop_reason=None, stop_tier=None, enrollment=None, has_results=has_results))

    c = cfg["counts"]
    for _ in range(c["completed_results"]): add("COMPLETED", True)
    for _ in range(c["completed_no_results"]): add("COMPLETED", False)
    for _ in range(c["terminated"]): add("TERMINATED", False)
    for _ in range(c["withdrawn"]): add("WITHDRAWN", False)
    for _ in range(c["unknown"]): add("UNKNOWN", False)
    for _ in range(c["running"]): add("RECRUITING", False)
    comps.sort(key=lambda x: -x["similarity"])

    done = [x for x in comps if x["status"] == "COMPLETED"]
    small = r.sample(done, cfg["small"])
    for x in done: x["enrollment"] = r.randint(40, 190) if x in small else r.randint(210, 620)
    term = [x for x in comps if x["status"] == "TERMINATED"]
    for x, (reason, tier, _cause) in zip(term, cfg["terms"]):
        x["stop_reason"], x["stop_tier"], x["enrollment"] = reason, tier, r.randint(8, 90)
    for x in comps:
        if x["enrollment"] is None:
            x["enrollment"] = 0 if x["status"] == "WITHDRAWN" else r.randint(100, 400)

    enr_stop = [x["nct_id"] for x, t in zip(term, cfg["terms"]) if t[2] == "Slow enrollment"]
    small_ids = [x["nct_id"] for x in small]
    others = [x["nct_id"] for x in comps if x["nct_id"] not in enr_stop]
    extras = [f"NCT{cfg['nct0'] + 500 + i:08d}" for i in range(cfg["n_extras"])]

    causes = {}
    for x, (reason, tier, cause) in zip(term, cfg["terms"]):
        d = causes.setdefault(cause, {"cause": cause, "count": 0, "tier": tier, "quotes": []})
        d["count"] += 1
        d["quotes"].append({"nct_id": x["nct_id"], "quote": reason})

    n_term, n_te = len(term), len(enr_stop)
    sentence = f"{len(comps)} comparable trials; {n_term} terminated" + (f", {n_te} for slow enrollment." if n_te else ".")
    ctx = dict(comps=comps, enr_stop=enr_stop, small=small_ids, others=others, extras=extras,
               done=[x["nct_id"] for x in done])
    flags = cfg["flags"](ctx)
    for f in flags:
        f.setdefault("status", "open")
    elements = cfg["elements"](ctx)
    for e in elements.values():
        for fd in e["findings"]:
            assert fd["n"] == len(fd["evidence_ids"]), fd
    result = dict(
        run_id="", brief_echo=cfg["brief"], data_as_of=cfg["data_as_of"], condition_support=cfg["support"],
        bottom_line=dict(risk=cfg["risk"], n_comparables=len(comps), n_terminated=n_term,
                         n_terminated_enrollment=n_te, sentence=sentence),
        comparables=comps,
        outcomes=dict(comparables={b: sum(1 for x in comps if bucket(x) == b) for b in cfg["baseline"]},
                      baseline=cfg["baseline"]),
        stop_causes=list(causes.values()), elements=elements, flags=flags,
        no_flags_reason=cfg.get("no_flags_reason"), limits=cfg["limits"], diff=None, package_id=None)

    trials = {}
    for x in comps:
        trials[x["nct_id"]] = dict(
            nct_id=x["nct_id"], title=x["title"], status=x["status"], stop_reason=x["stop_reason"],
            stop_tier=x["stop_tier"], enrollment=x["enrollment"], has_results=x["has_results"],
            sponsor=r.choice(SPONSORS), phase=cfg["phase_label"], start_date=f"{r.randint(2016, 2024)}-{r.randint(1, 12):02d}",
            countries=r.sample(["United States", "Germany", "Poland", "Japan", "Spain", "Canada"], 3))
    for i, n in enumerate(extras):
        trials[n] = dict(nct_id=n, title=f"{DRUGS[(i * 3 + 1) % len(DRUGS)]} in {cfg['title_cond']} (recruiting)",
                         status="RECRUITING", stop_reason=None, stop_tier=None, enrollment=r.randint(120, 500),
                         has_results=False, sponsor=r.choice(SPONSORS), phase=cfg["phase_label"],
                         start_date="2026-0" + str(r.randint(1, 9)), countries=["United States", "Germany", "Poland"])
    return result, trials


ELIG = """Inclusion Criteria:
* Age 40 to 80 years
* Physician-diagnosed COPD, post-bronchodilator FEV1/FVC < 0.70
* Post-bronchodilator FEV1 between 30% and 60% of predicted
* At least 2 moderate or severe COPD exacerbations in the previous 12 months
* Current or former smoker with at least 10 pack-years

Exclusion Criteria:
* Current diagnosis of asthma
* COPD exacerbation within 4 weeks before screening
* Lung volume reduction surgery within the previous 12 months"""

COPD_BRIEF = dict(
    source="nct", nct_id="NCT03460704", condition="Chronic Obstructive Pulmonary Disease",
    mesh_terms=["Pulmonary Disease, Chronic Obstructive"], phase=["PHASE2"], intervention_type=["DRUG"],
    eligibility_text=ELIG, structured_cutoffs=None,
    primary_endpoint="Change from baseline in trough FEV1 at Week 12", primary_endpoint_timeframe="12 weeks",
    target_enrollment=240, enrollment_type="ESTIMATED", countries=["United States", "Germany", "Poland"],
    arm_types=["EXPERIMENTAL", "PLACEBO_COMPARATOR"])

T2D_BRIEF = dict(
    source="nct", nct_id="NCT05000001", condition="Type 2 Diabetes Mellitus", mesh_terms=["Diabetes Mellitus, Type 2"],
    phase=["PHASE3"], intervention_type=["DRUG"],
    eligibility_text="Inclusion Criteria:\n* Age 18 to 75 years\n* HbA1c between 7.0% and 10.5%\n* BMI 25 to 40 kg/m2\n\nExclusion Criteria:\n* Type 1 diabetes\n* eGFR below 45 mL/min/1.73 m2",
    primary_endpoint="Change in HbA1c from baseline at Week 26", primary_endpoint_timeframe="26 weeks",
    target_enrollment=420, enrollment_type="ESTIMATED", countries=["United States", "Mexico", "Poland"],
    arm_types=["EXPERIMENTAL", "PLACEBO_COMPARATOR"])

AATD_BRIEF = dict(
    source="nct", nct_id="NCT05000002", condition="Alpha-1 Antitrypsin Deficiency with Emphysema",
    mesh_terms=["alpha 1-Antitrypsin Deficiency"], phase=["PHASE2"], intervention_type=["BIOLOGICAL"],
    eligibility_text="Inclusion Criteria:\n* Age 18 to 65 years\n* Serum AAT below 11 uM\n* FEV1 between 35% and 70% of predicted\n\nExclusion Criteria:\n* IgA deficiency",
    primary_endpoint="Change in CT lung density at Week 52", primary_endpoint_timeframe="52 weeks",
    target_enrollment=60, enrollment_type="ESTIMATED", countries=["United States", "Spain"],
    arm_types=["EXPERIMENTAL"])

COPD_BASE = dict(completed_results=520, completed_no_results=301, terminated=262, withdrawn=71, unknown=150, running=108)
T2D_BASE = dict(completed_results=1180, completed_no_results=640, terminated=410, withdrawn=120, unknown=330, running=260)
AATD_BASE = dict(completed_results=22, completed_no_results=9, terminated=8, withdrawn=3, unknown=4, running=6)

COPD = dict(
    seed=11, nct0=5100000, title_cond="moderate-to-severe COPD", phase_label="Phase 2", brief=COPD_BRIEF,
    data_as_of="2026-11-02", support="full", risk="medium", baseline=COPD_BASE, small=15, n_extras=11,
    counts=dict(completed_results=14, completed_no_results=7, terminated=7, withdrawn=0, unknown=0, running=0),
    why=["Phase 2 COPD, FEV1 range overlaps 90%", "Phase 2 COPD, same endpoint", "Phase 2b COPD, similar population",
         "Phase 2 COPD, inhaled, same timeframe", "Phase 2 COPD, FEV1 range overlaps 75%"],
    terms=[("Slow recruitment", "stated", "Slow enrollment"), ("Enrollment below target", "stated", "Slow enrollment"),
           ("Low enrollment after strict exacerbation rule", "stated", "Slow enrollment"),
           ("Recruitment difficulties", "stated", "Slow enrollment"),
           ("Lack of efficacy at interim analysis", "stated", "Lack of efficacy"),
           ("Sponsor portfolio reprioritisation (company announcement)", "outside", "Business decision"),
           (None, "unknown", "Reason not stated")],
    flags=lambda c: [
        dict(id="pop_exacerbation_stricter", element="population", title="Exacerbation rule stricter than most comparables",
             body="21 of 28 comparable trials required fewer prior exacerbations. 3 of the 4 trials that stopped for slow enrollment used the same rule.",
             question="Is one prior exacerbation enough for this mechanism?", confidence="stated",
             evidence_ids=c["enr_stop"], n=len(c["enr_stop"]), action_label="Edit eligibility"),
        dict(id="sites_competing_trials", element="sites", title="11 COPD trials recruiting in your 3 countries",
             body="11 other COPD trials are recruiting in the United States, Germany and Poland now; 6 list sites in the same cities as your likely sites.",
             question="Which of your planned sites overlap with these trials?", confidence="stated",
             evidence_ids=c["extras"], n=len(c["extras"]), action_label="Review sites"),
        dict(id="size_above_actual", element="size", title="Target of 240 is above what most comparables enrolled",
             body="15 of 21 completed comparables enrolled fewer than 200 patients. Original targets are not kept by the registry, so this compares against actual enrollment.",
             question="Is 240 driven by power, or carried over from an earlier design?", confidence="stated",
             evidence_ids=c["small"], n=len(c["small"]), action_label="Review sample size")],
    elements=lambda c: dict(
        population={"findings": [
            F("21 of 28 comparables required fewer prior exacerbations than this design (2 or more in 12 months).", c["others"][:21]),
            F("FEV1 30 to 60% of predicted matches the range used in 17 of 28 comparables.", c["done"][:17]),
            F("No comparable reported a blood eosinophil cutoff in its eligibility text.", [])]},
        endpoints={"findings": [
            F("Trough FEV1 is the primary endpoint in 17 of 28 comparables.", c["done"][:17]),
            F("Week 12 timeframe appears in 9 comparables; 8 of those completed.", c["done"][:9])]},
        size={"findings": [F("15 of 21 completed comparables enrolled fewer than 200 patients (actual enrollment).", c["small"])]},
        sites={"findings": [F("11 other COPD trials are recruiting in the United States, Germany and Poland.", c["extras"])]},
        design={"findings": [F("24 of 28 comparables were randomised, double-blind and parallel-group.", c["others"][:24]),
                             F("Add-on to background therapy: not found in the registry fields.", [])]}),
    limits=["The registry has no schedule of activities, so visit burden cannot be compared.",
            "Original enrollment targets are replaced by actual enrollment once a trial finishes.",
            "No per-site enrollment is published, so site performance cannot be measured.",
            "Protocol amendment reasons are not recorded.",
            "1 of 7 terminated comparables gave no stop reason (shown as 'reason not stated')."])

T2D = dict(
    seed=23, nct0=5200000, title_cond="type 2 diabetes", phase_label="Phase 3", brief=T2D_BRIEF,
    data_as_of="2026-08-20", support="basic", risk="low", baseline=T2D_BASE, small=5, n_extras=7,
    counts=dict(completed_results=8, completed_no_results=4, terminated=3, withdrawn=1, unknown=1, running=2),
    why=["Phase 3 type 2 diabetes, same endpoint", "Phase 3 type 2 diabetes, similar population",
         "Phase 3 type 2 diabetes, HbA1c range overlaps"],
    terms=[("Slow recruitment", "stated", "Slow enrollment"), ("Safety signal in extension study", "stated", "Safety"),
           (None, "unknown", "Reason not stated")],
    flags=lambda c: [
        dict(id="sites_competing_trials", element="sites", title="7 diabetes trials recruiting in your 3 countries",
             body="7 other type 2 diabetes trials are recruiting in the United States, Mexico and Poland now.",
             question="Which of your planned sites overlap with these trials?", confidence="stated",
             evidence_ids=c["extras"], n=len(c["extras"]), action_label="Review sites"),
        dict(id="size_above_actual", element="size", title="Target of 420 is above what most comparables enrolled",
             body="5 of 12 completed comparables enrolled fewer than 200 patients. Original targets are not kept by the registry, so this compares against actual enrollment.",
             question="Is 420 driven by power, or carried over from an earlier design?", confidence="stated",
             evidence_ids=c["small"], n=len(c["small"]), action_label="Review sample size")],
    elements=lambda c: dict(
        population={"findings": [F("Eligibility cutoffs for this condition are not parsed yet (basic support); text match only.", [])]},
        endpoints={"findings": [F("HbA1c change is the primary endpoint in 10 of 19 comparables.", c["done"][:10])]},
        size={"findings": [F("5 of 12 completed comparables enrolled fewer than 200 patients.", c["small"])]},
        sites={"findings": [F("7 other type 2 diabetes trials are recruiting in your countries.", c["extras"])]},
        design={"findings": [F("Add-on design: not found in the registry fields.", [])]}),
    limits=["Basic condition support: comparables and outcomes are real, eligibility cutoffs are not parsed for this condition.",
            "Original enrollment targets are replaced by actual enrollment once a trial finishes.",
            "No per-site enrollment is published.", "1 of 3 terminated comparables gave no stop reason."])

AATD = dict(
    seed=37, nct0=5300000, title_cond="alpha-1 antitrypsin deficiency", phase_label="Phase 2", brief=AATD_BRIEF,
    data_as_of="2026-11-02", support="basic", risk="insufficient", baseline=AATD_BASE, small=1, n_extras=0,
    counts=dict(completed_results=1, completed_no_results=1, terminated=1, withdrawn=0, unknown=0, running=0),
    why=["Phase 2 AATD, same endpoint", "Phase 2 AATD, similar population"],
    terms=[(None, "unknown", "Reason not stated")],
    flags=lambda c: [],
    no_flags_reason="Only 3 comparable trials were found. At least 5 are needed before a flag can be raised, so none are shown rather than guessing from too little evidence.",
    elements=lambda c: dict(
        population={"findings": [F("No comparable eligibility cutoffs could be compared with fewer than 5 trials.", [])]},
        endpoints={"findings": [F("CT lung density is the primary endpoint in 2 of 3 comparables.", c["done"][:2])]},
        size={"findings": [F("Enrollment of the 3 comparables ranged widely; too few to compare.", c["done"][:2])]},
        sites={"findings": [F("Competing trials: not found.", [])]},
        design={"findings": [F("Design details: not found in the registry fields.", [])]}),
    limits=["Fewer than 5 comparable trials: no flags are raised.", "Basic condition support.",
            "Original enrollment targets are replaced by actual enrollment once a trial finishes."])

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    trials = {}
    for name, cfg in [("copd", COPD), ("basic", T2D), ("few", AATD)]:
        res, t = build(cfg)
        trials.update(t)
        (OUT / f"{name}.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    briefs = {"NCT03460704": COPD_BRIEF, "NCT05000003": {**COPD_BRIEF, "nct_id": "NCT05000003"},
              "NCT05000001": T2D_BRIEF, "NCT05000002": AATD_BRIEF,
              "NCT05000004": {**T2D_BRIEF, "nct_id": "NCT05000004", "primary_endpoint": "",
                              "primary_endpoint_timeframe": "", "target_enrollment": None}}
    (OUT / "briefs.json").write_text(json.dumps(briefs, indent=2), encoding="utf-8")
    (OUT / "trials.json").write_text(json.dumps(trials, indent=2), encoding="utf-8")
    print("wrote", [p.name for p in OUT.iterdir()])
