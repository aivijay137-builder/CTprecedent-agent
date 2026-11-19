"""Re-ranks the engine's candidate list with a pack: first the hard filter (with its fallback), then small boosts and penalties.
Rank, don't over-filter: only the hard filter can remove a trial, and it is relaxed when fewer than MIN_COMPARABLES would remain.
The boost and penalty sizes are STARTING VALUES, untuned (see EVALS/DECISIONS.md D15); the eval should tune them.
The similarity score shown to the user stays the engine's own score: the pack only changes the ORDER, and says why in `why`."""
import re

MIN_COMPARABLES = 5          # same minimum as the flag rules
WINDOW = 500                 # candidates (after the filter) that the hints may reorder; the rest keep their order below them
BOOST_SUBTYPE = 0.04         # comparable shares a subtype with the design
BOOST_ARCHETYPE = 0.04       # comparable has the same kind of primary endpoint as the design
PENALTY_ERA = 0.04           # comparable started before the drug-class breakpoint (the design is assumed to start now)
ARCH_ORDER = ["safety_or_pk", "survival_or_events", "response_or_remission", "symptom_or_pro_score", "lab_or_physiologic_change"]  # first match wins, as when mined

DRUG, DEVICE, BEHAV = {"DRUG", "BIOLOGICAL", "GENETIC", "COMBINATION_PRODUCT"}, {"DEVICE", "PROCEDURE", "RADIATION"}, {"BEHAVIORAL", "DIETARY_SUPPLEMENT"}


def klass(types) -> str | None:
    """Intervention class, or None when the trial lists no intervention type (such a trial is never filtered out)."""
    ts = set(types or [])
    if not ts:
        return None
    return "drug_biologic" if ts & DRUG else "device_procedure_radiation" if ts & DEVICE else "behavioural_supplement" if ts & BEHAV else "other"


def _rx(pattern: str):
    try:
        return re.compile(pattern, re.I)
    except re.error:
        return None


def classify_endpoint(text: str, archetypes: list[dict]) -> str | None:
    rules = sorted(archetypes, key=lambda a: ARCH_ORDER.index(a["name"]) if a["name"] in ARCH_ORDER else 99)
    for a in rules:
        r = _rx(a.get("regex", ""))
        if r and r.search(text or ""):
            return a["name"]
    return None


def hard_filter(cand: list[dict], eff: dict, brief, log: dict) -> list[dict]:
    rule = eff.get("intervention_split")
    log["hard_filter"] = {"applied": False, "relaxed": False, "removed": 0, "reason": ""}
    h = log["hard_filter"]
    if not eff["parts"].get("hard_filter") or not rule:
        h["reason"] = "switched off" if rule else "this pack has no hard filter"
        return cand
    h["name"] = rule["name"]
    dc = klass(brief.intervention_type)
    if dc is None:
        h["reason"] = "the design names no intervention type"
        return cand
    kept = [c for c in cand if klass(c.get("types")) in (None, dc)]
    removed = len(cand) - len(kept)
    if not removed:
        h["reason"] = f"every candidate is already {dc}"
        return cand
    if len(cand) < MIN_COMPARABLES:
        h["reason"] = f"the pool has only {len(cand)} trials, so nothing was filtered"
        return cand
    if len(kept) < MIN_COMPARABLES:   # fallback ladder: the only hard filter today, so relaxing it is the whole ladder
        h.update(relaxed=True, removed=0, reason=f"only {len(kept)} {dc} trials would remain (fewer than {MIN_COMPARABLES}), so the filter was relaxed and all {len(cand)} kept", would_remove=removed)
        return cand
    h.update(applied=True, removed=removed, reason=f"removed {removed} trials that are not {dc}")
    return cand if not removed else kept


def _extras(cx, ids: list[str]) -> dict[str, tuple]:
    lst = ",".join("'" + i.replace("'", "''") + "'" for i in ids) or "''"
    rows = cx.q("P2. Start year and condition words of the leading candidates (pack ranking hints)", f"""
SELECT s.nct_id, try_cast(substr(s.start_date, 1, 4) AS INTEGER),
       lower(coalesce((SELECT string_agg(term, ' | ') FROM study_conditions c WHERE c.nct_id = s.nct_id AND c.kind = 'text'), ''))
FROM studies_current s WHERE s.nct_id IN ({lst})""")
    return {r[0]: (r[1], r[2]) for r in rows}


def hints(cx, cand: list[dict], eff: dict, brief, log: dict) -> list[dict]:
    log["ranking"] = {"applied": False, "reason": ""}
    g = log["ranking"]
    if not eff["parts"].get("ranking"):
        g["reason"] = "switched off"
        return cand
    window, rest = cand[:WINDOW], cand[WINDOW:]
    if not window:
        g["reason"] = "no candidates"
        return cand
    ex = _extras(cx, [c["nct_id"] for c in window])
    dtext = " ".join([brief.condition or "", " ".join(brief.mesh_terms or []), brief.primary_endpoint or ""]).lower()
    subs = [(s["name"], _rx(s["regex"])) for s in eff["subtypes"]]
    d_subs = [n for n, r in subs if r and r.search(dtext)]
    d_arch = classify_endpoint((brief.primary_endpoint or "").lower(), eff["archetypes"])
    eras = [(e["name"], e["proposed_year"]) for e in eff["eras"] if e.get("proposed_year")] if eff["parts"].get("era") else []  # own switch, off by default
    n_sub = n_arch = n_era = 0
    for c in window:
        c["base_score"] = c["score"]
        year, ctext = ex.get(c["nct_id"], (None, ""))
        text = f"{ctext} {(c.get('title') or '').lower()}"
        delta, why = 0.0, []
        shared = [n for n, r in subs if n in d_subs and r and r.search(text)]
        if shared:
            delta += BOOST_SUBTYPE; n_sub += 1; why.append(f"pack boost: same subtype ({shared[0]})")
        if d_arch and classify_endpoint((c.get("pm") or "").lower(), eff["archetypes"]) == d_arch:
            delta += BOOST_ARCHETYPE; n_arch += 1; why.append(f"pack boost: same endpoint type ({d_arch})")
        for name, y in eras:
            if year and year < y:
                delta -= PENALTY_ERA; n_era += 1; why.append(f"pack penalty: started before {y} ({name})")
                break
        c["score"] = c["base_score"] + delta
        if why:
            c["why"] = (c.get("why") or "") + ", " + "; ".join(why)
    window.sort(key=lambda c: (-c["score"], c["nct_id"]))
    for c in window:
        c["score"] = c.pop("base_score")      # the similarity shown to the user is still the engine's own
    g.update(applied=True, window=len(window), design_subtypes=d_subs, design_endpoint_type=d_arch,
             boosted_subtype=n_sub, boosted_endpoint_type=n_arch, penalised_era=n_era,
             era_applied=bool(eras), sizes={"subtype": BOOST_SUBTYPE, "endpoint_type": BOOST_ARCHETYPE, "era": -PENALTY_ERA})
    return window + rest


def apply(cx, cand: list[dict], brief, eff: dict) -> tuple[list[dict], dict]:
    """(new candidate list, log). The log is stored with the run and shown to the user: what was filtered, relaxed, boosted."""
    log = {"pack": eff["label"], "ids": eff["ids"], "versions": eff["versions"], "status": eff["status"], "parts": eff["parts"]}
    cand = hard_filter(cand, eff, brief, log)
    cand = hints(cx, cand, eff, brief, log)
    return cand, log
