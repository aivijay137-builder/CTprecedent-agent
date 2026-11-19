"""Mines the registry (serving.duckdb, SQL only: no Groq or other paid call) and writes the draft pack files into Prompts/packs/.
Every number comes from SQL and carries its n. The draft words come from words.py and are labelled unreviewed.
Run from the Faro folder:   python src/packs/mine.py [pack_id ...]          (no ids = all packs)
Output:  Prompts/packs/_base.yaml, areas/*.yaml, indications/*.yaml, _coverage.csv, _coverage_top_indications.csv, _mined/<id>.json, _mined/_queries.sql"""
import csv
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import yaml

HERE = Path(__file__).resolve().parent
FARO = HERE.parent.parent
sys.path.insert(0, str(FARO))
sys.path.insert(0, str(FARO / "src"))
from backend import criteria  # noqa: E402  (the same rule-based reader the app uses without a key)
from packs.words import W  # noqa: E402

OUT = FARO / "Prompts" / "packs"
DB = os.environ.get("CTG_DB_PATH") or str(FARO / "data" / "serving_full" / "serving.duckdb")
TODAY = dt.date.today().isoformat()
PHASES = {"phase2": "PHASE2", "phase2_3": "PHASE2,PHASE3", "phase3": "PHASE3"}
QUERIES: dict[str, str] = {}   # id -> SQL text, written to _mined/_queries.sql so every number can be re-run


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def Q(con, qid, sql, params=None):
    QUERIES.setdefault(qid, " ".join(sql.split()))
    return con.execute(sql, params or []).fetchall()


def r2(x):
    return None if x is None else round(float(x), 2)


def quant(con, qid, col, where, name):
    """n and p10, p25, p50, p75, p90 of a column among trials in t that satisfy `where`."""
    n, qs = Q(con, qid, f"SELECT count({col}), quantile_cont({col}, [0.1, 0.25, 0.5, 0.75, 0.9]) FROM t WHERE {where}")[0]
    out = {"n": n}
    if n:
        out.update(dict(zip(["p10", "p25", "p50", "p75", "p90"], [r2(x) for x in qs])))
    return out


# ------------------------------------------------------------------ the per-trial table (all interventional trials, built once)
def build_g(con):
    log("building the per-trial table")
    con.execute(f"ATTACH '{(FARO / 'precedent.duckdb').as_posix()}' AS prec (READ_ONLY)")
    con.execute("""CREATE TEMP TABLE g AS SELECT s.nct_id, s.phases, s.overall_status AS status, s.start_date, s.enrollment, s.enrollment_type,
      s.allocation, s.masking, s.arm_types, s.has_results, s.brief_title AS title,
      CASE s.phases WHEN 'PHASE2' THEN 'phase2' WHEN 'PHASE2,PHASE3' THEN 'phase2_3' WHEN 'PHASE3' THEN 'phase3' END AS pg,
      try_cast(substr(s.start_date, 1, 4) AS INTEGER) AS start_year,
      try_cast(CASE WHEN length(s.start_date) = 7 THEN s.start_date || '-01' ELSE s.start_date END AS DATE) AS sd,
      try_cast(CASE WHEN length(s.primary_completion_date) = 7 THEN s.primary_completion_date || '-01' ELSE s.primary_completion_date END AS DATE) AS pd,
      lower(coalesce(po.pm, '')) AS pm, coalesce(si.ns, 0) AS n_sites, coalesce(si.nc, 0) AS n_countries,
      lower(coalesce(ct.ctext, '')) AS ctext, lower(coalesce(iv.inames, '')) AS inames, coalesce(iv.types, []::VARCHAR[]) AS types,
      l.stop_cause, l.stop_tier
    FROM studies_current s
    LEFT JOIN (SELECT nct_id, string_agg(measure, ' | ') AS pm FROM study_outcomes WHERE kind = 'primary' GROUP BY 1) po USING (nct_id)
    LEFT JOIN (SELECT nct_id, count(*) AS ns, count(DISTINCT country) AS nc FROM study_sites GROUP BY 1) si USING (nct_id)
    LEFT JOIN (SELECT nct_id, string_agg(term, ' | ') AS ctext FROM study_conditions WHERE kind = 'text' GROUP BY 1) ct USING (nct_id)
    LEFT JOIN (SELECT nct_id, string_agg(name, ' | ') AS inames, list(DISTINCT type) AS types FROM study_interventions GROUP BY 1) iv USING (nct_id)
    LEFT JOIN study_labels l USING (nct_id)
    WHERE s.study_type = 'INTERVENTIONAL'""")
    log("  trials:", con.execute("SELECT count(*) FROM g").fetchone()[0])


def membership(con, pid, w):
    inc = ",".join("'" + t.replace("'", "''") + "'" for t in w["mesh"])
    exc = ",".join("'" + t.replace("'", "''") + "'" for t in w["exclude"])
    con.execute(f"CREATE OR REPLACE TEMP TABLE m AS SELECT DISTINCT nct_id FROM study_conditions WHERE kind IN ('mesh','ancestor') AND term IN ({inc})")
    if exc:
        con.execute(f"DELETE FROM m WHERE nct_id IN (SELECT nct_id FROM study_conditions WHERE kind IN ('mesh','ancestor') AND term IN ({exc}))")
    con.execute("CREATE OR REPLACE TEMP TABLE t AS SELECT g.* FROM g JOIN m USING (nct_id)")
    QUERIES.setdefault("membership", f"area trials = interventional trials with a MeSH term (own or ancestor) in the pack's mesh list, minus those with a term in its exclude list. Example for '{pid}': include [{inc}] exclude [{exc}]")


# ------------------------------------------------------------------ norms
ENR = "enrollment_type = 'ACTUAL' AND enrollment > 0 AND status IN ('COMPLETED','TERMINATED')"
DUR = "status = 'COMPLETED' AND sd IS NOT NULL AND pd IS NOT NULL AND date_diff('month', sd, pd) BETWEEN 1 AND 240"


def design_norms(con):
    out = {}
    for pg in PHASES:
        W_ = f"pg = '{pg}'"
        n = Q(con, "design_n", "SELECT count(*) FROM t WHERE pg = ?", [pg])[0][0]
        d = {"n_trials": n}
        if n:
            d["enrollment_actual"] = quant(con, "design_enrollment", "enrollment", f"{W_} AND {ENR}", "enrollment")
            d["duration_months_completed"] = quant(con, "design_duration", "date_diff('month', sd, pd)", f"{W_} AND {DUR}", "duration")
            d["sites_per_trial"] = quant(con, "design_sites", "n_sites", f"{W_} AND n_sites > 0", "sites")
            d["countries_per_trial"] = quant(con, "design_countries", "n_countries", f"{W_} AND n_countries > 0", "countries")
            den, k = Q(con, "design_randomized", f"SELECT count(*) FILTER (WHERE allocation IS NOT NULL AND allocation <> ''), count(*) FILTER (WHERE allocation = 'RANDOMIZED') FROM t WHERE {W_}")[0]
            d["randomized"] = {"n": den, "k": k, "share": r2(k / den) if den else None}
            den, k = Q(con, "design_placebo", f"SELECT count(*) FILTER (WHERE arm_types IS NOT NULL AND arm_types <> ''), count(*) FILTER (WHERE arm_types LIKE '%PLACEBO_COMPARATOR%') FROM t WHERE {W_}")[0]
            d["placebo_arm"] = {"n": den, "k": k, "share": r2(k / den) if den else None}
            den, k = Q(con, "design_masked", f"SELECT count(*) FILTER (WHERE masking IS NOT NULL AND masking <> ''), count(*) FILTER (WHERE masking IN ('DOUBLE','TRIPLE','QUADRUPLE')) FROM t WHERE {W_}")[0]
            d["double_blind_or_more"] = {"n": den, "k": k, "share": r2(k / den) if den else None}
        out[pg] = d
    return out


def outcome_priors(con):
    out = {}
    for pg in PHASES:
        n_end, k_stop = Q(con, "prior_termination", "SELECT count(*), count(*) FILTER (WHERE status IN ('TERMINATED','WITHDRAWN')) FROM t WHERE pg = ? AND status IN ('COMPLETED','TERMINATED','WITHDRAWN')", [pg])[0]
        d = {"n_ended": n_end, "termination_rate": {"n": n_end, "k": k_stop, "rate": r2(k_stop / n_end) if n_end else None}}
        rows = Q(con, "prior_stop_causes", """SELECT coalesce(stop_cause, 'unlabelled') c, count(*) n, mode(stop_tier) tier FROM t
            WHERE pg = ? AND status IN ('TERMINATED','WITHDRAWN','SUSPENDED') GROUP BY 1 ORDER BY 2 DESC""", [pg])
        tot = sum(r[1] for r in rows)
        d["n_stopped"] = tot
        d["top_stop_causes"] = [{"cause": c, "n": n, "share": r2(n / tot), "tier": tier} for c, n, tier in rows[:6]]
        out[pg] = d
    return out


# ------------------------------------------------------------------ endpoint vocabulary and archetypes (draft word lists: regexes are DRAFT WORDS)
VOCAB_STOP = set("change from baseline in at of the and to with for an on by after week weeks day days month months year years versus vs or number percentage participants "
                 "patients subjects measured using during time first any all per percent rate score primary study end that this were than into which have been will "
                 "evaluate assessed proportion mean total overall least between within group groups treatment".split())
ARCH = [  # first match wins
    ("safety_or_pk", r"adverse event|safety|tolerab|pharmacokinetic|\bauc\b|cmax|bioavailab|immunogenic", "safety, tolerability or drug-level"),
    ("survival_or_events", r"death|mortality|surviv|hospitali[sz]|major adverse|\bmace\b|time to (first|death|event|progression|relapse|recurrence)|event[- ]free|progression[- ]free|relapse|recurrence|incidence of", "survival or clinical-event"),
    ("response_or_remission", r"response|remission|responder|clearance|cure|eradication|sustained virologic|success|\bpasi\b|\bacr ?(20|50|70)\b|achiev", "response or remission"),
    ("symptom_or_pro_score", r"score|scale|questionnaire|index|symptom|pain|quality of life|diary|rating", "symptom or patient-reported score"),
    ("lab_or_physiologic_change", r"change from baseline|level|concentration|hba1c|ldl|blood pressure|fev1|pressure|volume|density|titer|titre|viral load|\bmg\b", "lab or physiologic measurement"),
]


def vocab_and_archetypes(con, n_pg):
    tok = Q(con, "endpoint_vocabulary", """SELECT token, count(DISTINCT nct_id) n FROM (
        SELECT nct_id, unnest(regexp_split_to_array(regexp_replace(pm, '[^a-z0-9 ]', ' ', 'g'), '\\s+')) AS token FROM t WHERE pg IS NOT NULL AND pm <> '')
        WHERE length(token) > 3 GROUP BY 1 ORDER BY 2 DESC LIMIT 60""")
    vocab = [{"term": a, "n": b} for a, b in tok if a not in VOCAB_STOP][:15]
    case = "CASE " + " ".join(f"WHEN regexp_matches(pm, '{rx}') THEN '{nm}'" for nm, rx, _ in ARCH) + " ELSE 'other' END"
    rows = Q(con, "archetype_stats", f"""SELECT arch, count(*) n, count(*) FILTER (WHERE {ENR}) n_enr, quantile_cont(enrollment, 0.5) FILTER (WHERE {ENR}) enr_med,
        count(*) FILTER (WHERE {DUR}) n_dur, quantile_cont(date_diff('month', sd, pd), 0.5) FILTER (WHERE {DUR}) dur_med
        FROM (SELECT *, {case} AS arch FROM t WHERE pg IS NOT NULL) GROUP BY 1 ORDER BY 2 DESC""")
    desc = {nm: d for nm, _, d in ARCH}
    desc["other"] = "other or unstated"
    arch = []
    for nm, n, n_enr, enr_med, n_dur, dur_med in rows:
        if n < 30 or nm == "other":
            continue
        arch.append({"name": nm, "mode": "boost", "n_trials": n, "share_of_area_phase2_3": r2(n / n_pg),
                     "enrollment_median": {"n": n_enr, "p50": r2(enr_med)}, "duration_months_median": {"n": n_dur, "p50": r2(dur_med)},
                     "regex": next(rx for a, rx, _ in ARCH if a == nm),
                     "rationale": f"Trials with a {desc[nm]} primary endpoint differ in size and length from other endpoint types in this area (median enrollment {r2(enr_med)}, n={n_enr}; median duration {r2(dur_med)} months, n={n_dur}). A new design is better compared with trials of its own type, so same-type trials are boosted, never required.",
                     "evidence": {"n": n, "query": "archetype_stats"}})
    return vocab, arch


# ------------------------------------------------------------------ counts per draft word list
def field_counts(con, fields):
    sel = ", ".join(f"count(*) FILTER (WHERE regexp_matches(c, '{rx}'))" for _, _, _, _, rx in fields)
    rows = Q(con, "field_mention_count", f"SELECT count(*), {sel} FROM (SELECT lower(e.criteria) c FROM study_eligibility e JOIN t USING (nct_id) WHERE t.pg IS NOT NULL AND e.criteria IS NOT NULL)")[0]
    return rows[0], rows[1:]


def subtype_counts(con, subtypes, n_pg):
    out = []
    for name, rx, why in subtypes:
        n, n_enr, med_in = Q(con, "subtype_count", f"""SELECT count(*), count(*) FILTER (WHERE {ENR}), quantile_cont(enrollment, 0.5) FILTER (WHERE {ENR})
            FROM t WHERE pg IS NOT NULL AND regexp_matches(ctext || ' ' || lower(title), '{rx}')""")[0]
        med_out = Q(con, "subtype_count_other", f"""SELECT quantile_cont(enrollment, 0.5) FILTER (WHERE {ENR}) FROM t
            WHERE pg IS NOT NULL AND NOT regexp_matches(ctext || ' ' || lower(title), '{rx}')""")[0][0]
        out.append({"name": name, "mode": "boost", "regex": rx, "n_trials": n, "share_of_area_phase2_3": r2(n / n_pg) if n_pg else None,
                    "enrollment_median_in_subtype": {"n": n_enr, "p50": r2(med_in)}, "enrollment_median_others": r2(med_out),
                    "rationale": f"{why} Registry data: {n} of {n_pg} Phase 2/3 trials in this area match ({r2(100 * n / n_pg) if n_pg else 0}%). Kept as a boost: it becomes a hard filter only after a clinician confirms these trials are not comparable.",
                    "evidence": {"n": n, "query": "subtype_count"}, "review_note": "boost only; hard filter needs clinician review"})
    return out


def era_series(con, era):
    name, rx, why = era
    rows = Q(con, "era_series", f"""SELECT start_year, count(*) n_total, count(*) FILTER (WHERE regexp_matches(inames, '{rx}')) n_match
        FROM t WHERE pg IS NOT NULL AND start_year BETWEEN 2000 AND 2025 GROUP BY 1 ORDER BY 1""")
    series = [{"year": y, "n_total": nt, "n_match": nm, "share": r2(nm / nt) if nt else None} for y, nt, nm in rows]
    total = sum(s["n_match"] for s in series)
    year = next((s["year"] for s in series if s["n_match"] >= 10 and (s["share"] or 0) >= 0.03), None)
    why2 = (f"{why} In the registry, trials naming this drug class first reach 3% of Phase 2/3 starts in {year} "
            f"({next(s['n_match'] for s in series if s['year'] == year)} of {next(s['n_total'] for s in series if s['year'] == year)} that year). Trials started before then are penalised, never removed."
            if year else f"{why} No year reached 3% of Phase 2/3 starts with at least 10 trials, so no breakpoint is proposed.")
    return {"name": name, "mode": "penalty", "regex": rx, "proposed_year": year, "rationale": why2, "evidence": {"n": total, "query": "era_series"},
            "series": series, "review_note": "words are a draft; confirm the drug class and the year with a domain expert"}


def intervention_split(con, n_pg):
    cls = """CASE WHEN list_has_any(types, ['DRUG','BIOLOGICAL','GENETIC','COMBINATION_PRODUCT']) THEN 'drug_biologic'
                  WHEN list_has_any(types, ['DEVICE','PROCEDURE','RADIATION']) THEN 'device_procedure_radiation'
                  WHEN list_has_any(types, ['BEHAVIORAL','DIETARY_SUPPLEMENT']) THEN 'behavioural_supplement' ELSE 'other' END"""
    rows = Q(con, "intervention_split", f"""SELECT c, count(*) n, count(*) FILTER (WHERE {ENR}) n_enr, quantile_cont(enrollment, 0.5) FILTER (WHERE {ENR}) med
        FROM (SELECT *, {cls} AS c FROM t WHERE pg IS NOT NULL) GROUP BY 1 ORDER BY 2 DESC""")
    groups = [{"type": c, "n": n, "share": r2(n / n_pg), "enrollment_median": {"n": ne, "p50": r2(m)}} for c, n, ne, m in rows]
    meds = {g["type"]: g["enrollment_median"]["p50"] for g in groups}
    d, o = meds.get("drug_biologic"), meds.get("device_procedure_radiation")
    why = ("Drug or biologic trials and device, procedure or radiation trials are different kinds of study: blinding, size and endpoints differ"
           + (f" (median enrollment {d} vs {o} in this area)" if d is not None and o is not None else "") +
           ". The design's own class is matched first. If that leaves fewer than 5 comparables, this filter is relaxed first and the user is told.")
    return {"name": "intervention_class", "mode": "hard_filter", "relax_rank": 1, "groups": groups, "rationale": why,
            "evidence": {"n": n_pg, "query": "intervention_split"}, "review_note": "hard filter proposed: confirm with a domain expert"}


# ------------------------------------------------------------------ cutoff norms (rule parser over a random sample; no AI)
def parse_sample(con, k=2000):  # the rule-based reader costs nothing, so a bigger sample than the 500 an AI read would allow
    rows = Q(con, "cutoff_sample", """SELECT e.nct_id, e.criteria FROM study_eligibility e JOIN t USING (nct_id)
        WHERE t.pg IS NOT NULL AND length(e.criteria) > 100 ORDER BY hash(e.nct_id) LIMIT ?""", [k])
    per_key: dict[str, dict] = {}
    for nct, text in rows:
        seen = set()
        for c in criteria.parse_criteria(text):
            key = c.get("key")
            if not key or key in ("min_age", "max_age") or key in seen:
                continue
            try:
                v = float(str(c["value"]).replace(",", ""))
            except (TypeError, ValueError):
                continue
            seen.add(key)
            d = per_key.setdefault(key, {"label": c.get("field") or key, "unit": c.get("unit") or "", "values": []})
            d["values"].append(v)
    return len(rows), per_key


GENERIC = {"between", "score", "duration", "male_female_duration", "time", "and", "or", "the", "of", "with"}


def cutoff_norms(con, sample_n, per_key, field_names):
    norms = []
    for nm, col in (("min_age_years", "min_age"), ("max_age_years", "max_age")):
        n, qs = Q(con, "age_norms", f"""SELECT count(a), quantile_cont(a, [0.1, 0.25, 0.5, 0.75, 0.9]) FROM (
            SELECT try_cast(regexp_extract(e.{col}, '(\\d+)', 1) AS INTEGER) a FROM study_eligibility e JOIN t USING (nct_id)
            WHERE t.pg IS NOT NULL AND e.{col} ILIKE '%year%')""")[0]
        if n:
            norms.append({"field": nm, "label": "Minimum age" if "min" in nm else "Maximum age", "unit": "years", "phase_group": "phase2_3_combined", "n": n, "low_n": n < 30,
                          **dict(zip(["p10", "p25", "p50", "p75", "p90"], [r2(x) for x in qs])), "source": "registry structured age field (SQL, all Phase 2/3 trials in the area)"})
    keep = []
    for key, d in sorted(per_key.items(), key=lambda kv: -len(kv[1]["values"])):
        base = key.rsplit("_", 1)[0]
        matches_field = any(base.startswith(f.split("_")[0]) or f.startswith(base.split("_")[0]) for f in field_names)
        if base in GENERIC or len(base) < 3 or "male_female" in base or "between" in base:
            continue
        if matches_field or len(d["values"]) >= 30:
            keep.append((key, d))
    for key, d in keep[:12]:
        v = np.array(d["values"])
        n = len(v)
        norms.append({"field": key, "label": d["label"], "unit": d["unit"], "phase_group": "phase2_3_combined", "n": n, "low_n": n < 30,
                      **dict(zip(["p10", "p25", "p50", "p75", "p90"], [r2(x) for x in np.percentile(v, [10, 25, 50, 75, 90])])),
                      "source": f"rule-based reader over a random sample of {sample_n} Phase 2/3 trials; unchecked"})
    return norms


def copd_registry_norms(con):
    """COPD only: the cutoffs already parsed into precedent.duckdb (the app's own source for COPD)."""
    cols = [r[0] for r in con.execute("SELECT column_name FROM information_schema.columns WHERE table_catalog = 'prec' AND table_name = 'copd_cutoffs'").fetchall()]
    out = []
    for c in cols:
        if not c.endswith("_value"):
            continue
        base = c[:-6]
        if base + "_status" not in cols:
            continue
        n, qs = Q(con, "copd_parsed_norms", f"SELECT count(v), quantile_cont(v, [0.1,0.25,0.5,0.75,0.9]) FROM (SELECT try_cast({c} AS DOUBLE) v FROM prec.copd_cutoffs WHERE status = 'ok' AND {base}_status = 'ok')")[0]
        if n:
            out.append({"field": base, "label": base.replace("_", " "), "unit": "", "phase_group": "all", "n": n, "low_n": n < 30,
                        **dict(zip(["p10", "p25", "p50", "p75", "p90"], [r2(x) for x in qs])), "source": "precedent.duckdb copd_cutoffs (parsed earlier for the app)"})
    return out


def few_shots(con, pid, k=3):
    rows = Q(con, "few_shot_candidates", """SELECT e.nct_id, e.criteria FROM study_eligibility e JOIN t USING (nct_id)
        WHERE t.pg = 'phase3' AND length(e.criteria) BETWEEN 600 AND 2000 ORDER BY hash(e.nct_id || ?) LIMIT 60""", [pid])
    out = []
    for nct, text in rows:
        cuts = [c for c in criteria.parse_criteria(text) if c.get("key")]
        if len(cuts) >= 4:
            out.append({"nct_id": nct, "criteria_excerpt": text[:900].strip(),
                        "rule_parse_candidate": [{"field": c["field"], "value": c["value"], "unit": c["unit"], "source_sentence": c.get("source_sentence", "")} for c in cuts],
                        "status": "UNCHECKED candidate: the rule-based reader's output, which can be wrong. A person must correct it before it is used as a few-shot example."})
        if len(out) == k:
            break
    return out


# ------------------------------------------------------------------ assemble one pack
def build_pack(con, pid, w):
    t0 = time.time()
    membership(con, pid, w)
    n_all, n23, n_pg = Q(con, "coverage", "SELECT count(*), count(*) FILTER (WHERE phases LIKE '%PHASE2%' OR phases LIKE '%PHASE3%'), count(*) FILTER (WHERE pg IS NOT NULL) FROM t")[0]
    n_parsed = Q(con, "coverage_parsed", "SELECT count(*) FROM t WHERE nct_id IN (SELECT nct_id FROM prec.copd_cutoffs WHERE status = 'ok')")[0][0]
    dn, pri = design_norms(con), outcome_priors(con)
    vocab, arch = vocab_and_archetypes(con, n_pg)
    n_el, counts = field_counts(con, w["fields"])
    sample_n, per_key = parse_sample(con)
    cn = cutoff_norms(con, sample_n, per_key, [f[0] for f in w["fields"]])
    if pid == "copd":
        cn += copd_registry_norms(con)
    fields = []
    for (name, label, unit, syn, rx), n in zip(w["fields"], counts):
        entry = {"name": name, "label": label, "unit": unit, "synonyms": syn, "regex": rx, "n_trials_mentioning": n,
                 "rationale": f"Named in the eligibility text of {n} of {n_el} Phase 2/3 trials in this area ({r2(100 * n / n_el) if n_el else 0}%), so the reader should look for it and keep its unit.",
                 "evidence": {"n": n, "query": "field_mention_count"}, "valid_range": None,
                 "synonyms_source": "drafted by Claude, unreviewed"}
        for key, d in per_key.items():
            if (key.startswith(name + "_") or key.startswith(name.split("_")[0] + "_")) and len(d["values"]) >= 30:
                v = np.array(d["values"])
                entry["valid_range"] = {"n": len(v), "p1": r2(np.percentile(v, 1)), "p99": r2(np.percentile(v, 99)), "source": f"rule-based reader sample, key {key}"}
                break
        fields.append(entry)
    subs = subtype_counts(con, w["subtypes"], n_pg)
    era = era_series(con, w["era"])
    isplit = intervention_split(con, n_pg)
    shots = few_shots(con, pid)
    # what the registry cannot tell you: the numbers
    hr = Q(con, "limit_results_posted", "SELECT count(*), count(*) FILTER (WHERE has_results) FROM t WHERE pg IS NOT NULL AND status = 'COMPLETED'")[0]
    bl = Q(con, "limit_blank_reason", "SELECT count(*), count(*) FILTER (WHERE stop_cause IN ('empty_or_blank','other_unclear','generic_decision')) FROM t WHERE pg IS NOT NULL AND status IN ('TERMINATED','WITHDRAWN','SUSPENDED')")[0]
    limits = [{"text": f"{r2(100 * hr[1] / hr[0]) if hr[0] else 0}% of completed Phase 2/3 trials in this area have posted results, so outcome data are missing for the rest.", "evidence": {"n": hr[0], "query": "limit_results_posted"}},
              {"text": f"{r2(100 * bl[1] / bl[0]) if bl[0] else 0}% of stopped Phase 2/3 trials give no usable stop reason (blank, unclear or generic), so stop causes are understated.", "evidence": {"n": bl[0], "query": "limit_blank_reason"}}]
    limits += [{"text": s, "source": "drafted by Claude, unreviewed"} for s in w["limits"]]
    level = w["level"]
    routing = {"mesh_terms": w["mesh"], "exclude_mesh_terms": w["exclude"], "priority": w["priority"],
               "parent": w.get("parent"), "coverage": {"n_interventional": n_all, "n_phase2_or_3": n23, "n_phase2_3_pure": n_pg, "n_with_parsed_cutoffs_in_precedent_db": n_parsed},
               "rationale": ("A design is routed to this pack when its condition's MeSH terms (or their parents) include one of the listed terms and none of the excluded ones. "
                             "When several packs match, the highest priority wins; an indication pack beats its area pack, and the area pack beats the base. "
                             f"Cancer trials are routed to the oncology packs, so this pack excludes them." if "Neoplasms" in w["exclude"] else
                             "A design is routed to this pack when its condition's MeSH terms (or their parents) include one of the listed terms and none of the excluded ones. When several packs match, the highest priority wins.")}
    pack = {"id": pid, "level": level, "label": w["label"], "version": "0.1.0", "status": "draft", "generated": TODAY,
            "provenance": {"mined_by": "src/packs/mine.py: SQL only on serving.duckdb, no Groq or other paid call", "words_by": "Claude, from general knowledge: unreviewed",
                           "data_as_of": con.execute("SELECT max(last_update_post_date) FROM studies_current").fetchone()[0], "queries": "_mined/_queries.sql"},
            "routing": routing,
            "prompt_addon": w["addon"], "prompt_addon_review": {"status": "draft, unreviewed", "words": len(w["addon"].split())},
            "extraction_fields": fields, "few_shot_examples": shots,
            "subtypes": subs, "trial_archetypes": arch, "endpoint_groups": [],
            "endpoint_groups_note": "Not drafted: needs the LLM clustering step (needs your approval and a cost estimate).",
            "background_therapy": [], "background_therapy_note": "Not drafted: needs eligibility-phrase mining, not run yet.",
            "era_breakpoints": [era], "intervention_split": isplit, "ranking_weights": None,
            "ranking_weights_note": "Inherited from _base.yaml. An override is allowed only if the eval shows a gain.",
            "fallback_order": ["intervention_class"],
            "endpoint_vocabulary": vocab,
            "cutoff_norms": cn, "design_norms": dn, "outcome_priors": pri, "known_limits": limits,
            "eval": {"status": "not_run", "reason": "The eval harness is not built. Pending: retrieval precision@10 base vs pack, pool-size guardrail, parsing accuracy, back-test hit rate.", "base_vs_pack": None}}
    mined = {"id": pid, "n_interventional": n_all, "n_phase2_or_3": n23, "n_phase2_3_pure": n_pg, "parse_sample_n": sample_n, "per_key_counts": {k: len(v["values"]) for k, v in per_key.items()},
             "era_series": era["series"], "endpoint_vocabulary": vocab, "archetypes": arch, "subtypes": subs}
    (OUT / "_mined").mkdir(parents=True, exist_ok=True)
    (OUT / "_mined" / f"{pid}.json").write_text(json.dumps(mined, indent=1, ensure_ascii=False), encoding="utf-8")
    sub = "indications" if level == "indication" else "areas"
    (OUT / sub).mkdir(parents=True, exist_ok=True)
    (OUT / sub / f"{pid}.yaml").write_text(
        "# DRAFT pack (status: draft). Numbers: SQL on the registry, each with its n (queries in _mined/_queries.sql). Words: drafted by Claude, unreviewed.\n"
        + yaml.safe_dump(pack, sort_keys=False, allow_unicode=True, width=140), encoding="utf-8")
    log(f"{pid}: {n_all} trials, {n23} Phase 2/3, fields {len(fields)}, subtypes {len(subs)}, archetypes {len(arch)}, norms {len(cn)}, few-shots {len(shots)} ({time.time() - t0:.0f}s)")
    return {"id": pid, "level": level, "n_all": n_all, "n23": n23, "n_pg": n_pg, "n_parsed": n_parsed}


def write_base():
    base = {"id": "_base", "level": "base", "label": "Base (generic fallback)", "version": "0.1.0", "status": "draft", "generated": TODAY,
            "provenance": {"note": "Describes what the code does today. Nothing here changes behaviour until a router is built."},
            "routing": {"default": True, "rationale": "Used when no area or indication pack matches the design's condition."},
            "prompt_addon": "(none) The base prompt lives in backend/readers.py (version v5: shared RULES, DESIGN_SYSTEM and TARGET_SYSTEM). A pack's add-on is appended after it.",
            "ranking_weights": {
                "note": "Actual values in backend/engine.py find_comparables. The packs prompt document assumed endpoint 35 / cutoff 30 / eligibility 20 / timeframe 10 / recency 5 and a pool of 25: the code does not use those.",
                "pool_size": 30, "recency_weight": None, "timeframe_weight": None,
                "stage1_all_candidates": {"primary_outcome_and_title_text": 0.7, "cutoff_overlap_or_text": 0.2, "intervention_type_match": 0.1},
                "stage2_top200_when_eligibility_text_given": {"primary_outcome_and_title_text": 0.5, "eligibility_wording": 0.25, "cutoff_overlap_or_blend": 0.15, "intervention_type_match": 0.1},
                "cutoff_overlap_available_for": "FEV1 % predicted range only (COPD); other cutoffs fall back to text similarity"},
            "hard_filters_today": ["same condition (MeSH pool)", "interventional", "phase overlap", "not the draft itself"],
            "fallback": "No fallback ladder today: fewer than 5 comparables means no flags, with an explanation.",
            "min_comparables_for_flags": 5, "extraction_fields": [], "subtypes": [], "trial_archetypes": [], "era_breakpoints": [], "cutoff_norms": [],
            "eval": {"status": "not_run", "reason": "Eval harness is not built; the base is the reference the packs will be compared against."}}
    (OUT / "_base.yaml").write_text("# Base pack: documents the current behaviour (draft).\n" + yaml.safe_dump(base, sort_keys=False, allow_unicode=True, width=140), encoding="utf-8")


def main():
    ids = sys.argv[1:] or list(W)
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(DB, read_only=True)
    con.execute("SET memory_limit='3GB'; SET threads=4")
    build_g(con)
    write_base()
    rows = [build_pack(con, pid, W[pid]) for pid in ids]
    if not sys.argv[1:]:
        with open(OUT / "_coverage.csv", "w", newline="", encoding="utf-8") as f:
            wr = csv.writer(f)
            wr.writerow(["pack", "level", "interventional_trials", "phase2_or_3_trials", "phase2_3_pure_trials", "trials_with_parsed_cutoffs_in_precedent_db", "threshold", "meets_threshold"])
            for r in rows:
                thr = 300 if r["level"] == "indication" else 2000
                have = r["n23"] if r["level"] == "indication" else r["n_all"]
                wr.writerow([r["id"], r["level"], r["n_all"], r["n23"], r["n_pg"], r["n_parsed"], f"{thr} {'Phase 2/3' if r['level'] == 'indication' else 'interventional'}", have >= thr])
        top = Q(con, "top_indications", """SELECT c.term, count(DISTINCT c.nct_id) FROM study_conditions c JOIN g USING (nct_id)
            WHERE c.kind = 'mesh' AND (g.phases LIKE '%PHASE2%' OR g.phases LIKE '%PHASE3%') GROUP BY 1 ORDER BY 2 DESC LIMIT 30""")
        own = {"Pulmonary Disease, Chronic Obstructive": "copd", "Asthma": "asthma", "Psoriasis": "psoriasis"}
        with open(OUT / "_coverage_top_indications.csv", "w", newline="", encoding="utf-8") as f:
            wr = csv.writer(f)
            wr.writerow(["rank", "mesh_term", "phase2_or_3_interventional_trials", "has_own_pack"])
            for i, (t, n) in enumerate(top, 1):
                wr.writerow([i, t, n, own.get(t, "")])
    (OUT / "_mined").mkdir(parents=True, exist_ok=True)
    qfile = OUT / "_mined" / "_queries.sql"
    old = {}
    if qfile.exists() and sys.argv[1:]:
        for blk in qfile.read_text(encoding="utf-8").split("\n\n"):
            if blk.startswith("-- "):
                old[blk.split("\n")[0][3:]] = blk.split("\n", 1)[1]
    old.update(QUERIES)
    qfile.write_text("-- Queries behind every number in the packs. `t` = the pack's trials (interventional trials in the area), `g` = all interventional trials. Parameters (?) and regexes come from words.py.\n\n"
                     + "\n\n".join(f"-- {k}\n{v}" for k, v in old.items()) + "\n", encoding="utf-8")
    log("done")


if __name__ == "__main__":
    main()
