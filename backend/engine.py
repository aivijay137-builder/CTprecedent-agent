"""Real engine (Phase B). Reads ctg.duckdb (read-only) and precedent.duckdb (read-only).

Rule of the house: every number that reaches the screen comes from a SQL string run by `Ctx.q`,
and that exact string is returned in `audit` so it can be re-run by hand. Python only ranks,
formats, and applies the flag rules to the numbers SQL returned. No LLM is used here.
"""
import math
import os
import re
import threading
import time
from pathlib import Path

import duckdb

from . import flag_config as cfg, flagrules
import adapters  # src/adapters.py: CTG path (CTG_DB_PATH) + NCT -> DesignBrief

PREC = (Path(os.environ["DATA_DIR"]) if os.environ.get("DATA_DIR") else Path(__file__).resolve().parent.parent).joinpath("precedent.duckdb").as_posix()
MAX_COMPARABLES = 30
MIN_N = cfg.MIN_N  # thresholds live in flag_config.py
EVIDENCE_CAP = 50
COPD_MESH = "Pulmonary Disease, Chronic Obstructive"

BUCKETS = ["completed_results", "completed_no_results", "terminated", "withdrawn", "unknown", "running"]
BUCKET_SQL = """CASE WHEN s.overall_status='COMPLETED' AND s.has_results THEN 'completed_results'
  WHEN s.overall_status='COMPLETED' THEN 'completed_no_results'
  WHEN s.overall_status='TERMINATED' THEN 'terminated'
  WHEN s.overall_status='WITHDRAWN' THEN 'withdrawn'
  WHEN s.overall_status='UNKNOWN' THEN 'unknown' ELSE 'running' END"""
CAUSE_LABEL = {
    "enrollment": "Slow enrollment", "business": "Business decision", "funding": "Funding", "covid": "COVID-19",
    "safety": "Safety", "futility_efficacy": "Futility or lack of efficacy", "drug_supply": "Drug or device supply",
    "regulatory": "Regulatory", "pi_site": "Investigator or site", "design_protocol": "Protocol or design change",
    "completed_goal": "Goal reached early", "generic_decision": "Sponsor decision (reason not stated)",
    "empty_or_blank": "Reason not stated", "other_unclear": "Reason unclear"}
TIER = {"A": "stated", "B": "outside", "C": "unknown"}  # classifier tiers -> UI tiers
STOP = set("change from baseline in at of the and to with for an on by after week weeks day days month months year "
           "years versus vs or number percentage participants patients subjects measured using during time first "
           "first-line any all per percent rate score".split())


class RegistryBusy(Exception):
    """The registry file is locked (a sync is probably writing to it)."""


_attach_lock = threading.Lock()


def connect():
    # DuckDB shares one database instance per file inside this process, so the attach below must happen only once,
    # even when several runs / lookups are in flight at the same time.
    try:
        c = duckdb.connect(adapters.CTG, read_only=True)
    except duckdb.IOException as e:
        raise RegistryBusy("The registry database is being updated right now. Try again in a minute.") from e
    c.execute("SET memory_limit='2GB'; SET threads=2")
    with _attach_lock:
        if not c.execute("SELECT 1 FROM duckdb_databases() WHERE database_name = 'prec'").fetchone():
            c.execute(f"ATTACH '{PREC}' AS prec (READ_ONLY)")
    return c


def lit(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def ids_sql(ids) -> str:
    ids = [i for i in ids if re.fullmatch(r"NCT\d{8}", i)]
    return ",".join(lit(i) for i in ids) or "''"


class Ctx:
    def __init__(self):
        self.con = connect()
        self.audit: list[dict] = []

    def q(self, name: str, sql: str):
        sql = sql.strip()
        rows = self.con.execute(sql).fetchall()
        self.audit.append({"name": name, "sql": sql})
        return rows


# ------------------------------------------------------------------ helpers
def is_copd(brief) -> bool:
    return COPD_MESH in brief.mesh_terms or bool(re.search(r"\bCOPD\b|chronic obstructive", brief.condition, re.I))


def cond_label(brief) -> str:
    if is_copd(brief):
        return "COPD"
    t = (brief.mesh_terms[:1] or [brief.condition.split(";")[0].strip()])[0]
    return t or "this condition"


def pool_sql(brief) -> str:
    if is_copd(brief):
        return "SELECT nct_id FROM prec.copd_trials"
    if brief.mesh_terms:
        terms = ",".join(lit(t) for t in brief.mesh_terms)
        return f"SELECT DISTINCT nct_id FROM study_conditions WHERE kind='mesh' AND term IN ({terms})"
    parts = [c.strip() for c in brief.condition.split(";") if c.strip()]
    cond = " OR ".join(f"term ILIKE {lit('%' + c + '%')}" for c in parts) or "FALSE"
    return f"SELECT DISTINCT nct_id FROM study_conditions WHERE kind='text' AND ({cond})"


def phase_pred(brief) -> str:
    if not brief.phase:
        return "TRUE"
    return f"list_has_any(string_split(s.phases, ','), [{','.join(lit(p) for p in brief.phase)}])"


def phase_label(p: str | None) -> str:
    if not p or p == "NA":
        return "Phase not applicable"
    return "Phase " + "/".join(x.replace("EARLY_PHASE", "early ").replace("PHASE", "") for x in p.split(","))


def toks(s: str | None) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9][a-z0-9\-]+", (s or "").lower()) if t not in STOP and len(t) > 2]


def join_and(xs: list[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def brief_cutoff_meta(brief) -> dict:
    """The user's numeric cutoffs keyed by machine name: {key: {value, unit, label}}."""
    out = {}
    for c in (brief.structured_cutoffs or {}).get("cutoffs", []):
        v = None
        try:
            if c.get("key") and re.search(r"\d", str(c.get("value"))):
                v = float(re.sub(r"[^\d.\-]", "", str(c.get("value"))))
        except ValueError:
            pass
        if v is not None:
            out[c["key"]] = {"value": v, "unit": c.get("unit") or "", "label": c.get("field") or c["key"]}
    return out


SEED_KEYS = {"min_age", "max_age", "fev1_pct_predicted_min", "fev1_pct_predicted_max", "fev1_fvc_ratio_max",
             "exacerbations_prior_year_min", "smoking_pack_years_min"}  # columns already parsed in precedent.duckdb (COPD)


def comparable_cutoffs(cx, ids, keys, meta, budget):
    """{key: {nct_id: number or None}} for the comparables read so far, plus a summary.
    Source 1 (SQL): cutoffs already parsed in precedent.duckdb. Source 2: the AI reader, cached in app.db, with a time limit
    so a run never waits minutes; whatever is not read yet is picked up on the next Re-run."""
    IN = ids_sql(ids)
    vals = {k: {} for k in keys}
    for k in keys:
        if k in SEED_KEYS:
            for n, v in cx.q(f"4c. Already-parsed cutoff {k} for the comparables (precedent.duckdb copd_cutoffs)", f"""
SELECT nct_id, try_cast({k}_value AS DOUBLE) FROM prec.copd_cutoffs
WHERE status='ok' AND {k}_status IN ('ok','not_stated') AND nct_id IN ({IN})"""):
                vals[k][n] = v
    info = {"ai": False, "calls": 0, "not_yet_read": 0, "error": ""}
    need = {k: [n for n in ids if n not in vals[k]] for k in keys}
    pending = sorted({n for v in need.values() for n in v})
    if pending:
        if not llmsvc.enabled():
            info["error"] = "AI reading is switched off, so only cutoffs already parsed are used."
        else:
            texts = dict(cx.q("4k. Eligibility text of comparables whose cutoffs are read by the AI (answers are cached in app.db with their quoted sentence)", f"""
SELECT nct_id, criteria FROM study_eligibility WHERE nct_id IN ({ids_sql(pending)})"""))
            fields = [{"key": k, "label": meta[k]["label"]} for k in keys if need[k]]
            deadline = time.time() + float(os.environ.get("LLM_TIME_BUDGET_S") or 40)
            r = readers.extract_targets({n: texts.get(n) or "" for n in pending}, fields, budget, deadline)
            info.update(ai=True, calls=r["calls"], not_yet_read=r["not_yet_read"], error=r["error"])
            for (n, k), rec in r["values"].items():
                if k in vals and n not in vals[k]:
                    vals[k][n] = float(rec["value"]) if rec["status"] == "ok" else None
    return vals, info


def brief_cutoffs(brief) -> dict[str, float]:
    out = {}
    for c in (brief.structured_cutoffs or {}).get("cutoffs", []):
        try:
            if c.get("key") and c.get("value") not in (None, "", "not stated"):
                out[c["key"]] = float(re.sub(r"[^\d.\-]", "", str(c["value"])))
        except ValueError:
            pass
    return out


def F(text: str, ids: list[str], n: int | None = None) -> dict:
    ids = list(dict.fromkeys(ids))
    return {"text": text, "n": len(ids) if n is None else n, "evidence_ids": ids[:EVIDENCE_CAP]}


# ------------------------------------------------------------------ step 1: comparables
def find_comparables(cx: Ctx, brief, excluded: list[str]):
    pool = pool_sql(brief)
    self_id = brief.nct_id or ""
    rows = cx.q("1. Candidate trials (hard filters: same condition, interventional, phase overlap, not the draft itself)", f"""
SELECT s.nct_id, s.brief_title AS title, s.phases, s.overall_status AS status, s.why_stopped, s.enrollment,
       s.has_results, o.pm, it.types,
       try_cast(c.fev1_pct_predicted_min_value AS DOUBLE) AS fev1_min, try_cast(c.fev1_pct_predicted_max_value AS DOUBLE) AS fev1_max
FROM studies_current s
LEFT JOIN (SELECT nct_id, string_agg(measure, ' | ') AS pm FROM study_outcomes
           WHERE kind='primary' AND nct_id IN ({pool}) GROUP BY nct_id) o USING (nct_id)
LEFT JOIN (SELECT nct_id, list(DISTINCT type) AS types FROM study_interventions
           WHERE nct_id IN ({pool}) GROUP BY nct_id) it USING (nct_id)
LEFT JOIN prec.copd_cutoffs c ON c.nct_id = s.nct_id AND c.status = 'ok'
WHERE s.nct_id IN ({pool}) AND s.study_type = 'INTERVENTIONAL' AND {phase_pred(brief)}
  AND s.nct_id <> {lit(self_id)}""")
    cand = [dict(zip(["nct_id", "title", "phases", "status", "why_stopped", "enrollment", "has_results", "pm", "types",
                      "fev1_min", "fev1_max"], r)) for r in rows]
    # --- text similarity (TF-IDF cosine on primary outcome + title) ---
    docs = [toks((c["pm"] or "") + " " + (c["title"] or "")) for c in cand]
    df: dict[str, int] = {}
    for d in docs:
        for t in set(d):
            df[t] = df.get(t, 0) + 1
    pm_df: dict[str, int] = {}  # how many candidates use each word in their PRIMARY OUTCOME (used for the endpoint check)
    for c in cand:
        for t in set(toks(c['pm'])):
            pm_df[t] = pm_df.get(t, 0) + 1
    N = len(docs)
    idf = lambda t: math.log((N + 1) / (df.get(t, 0) + 1)) + 1
    vec = lambda ts: {t: ts.count(t) * idf(t) for t in set(ts)}
    qv = vec(toks(brief.primary_endpoint))
    norm = lambda v: math.sqrt(sum(x * x for x in v.values())) or 1.0
    qn = norm(qv)
    cut = brief_cutoffs(brief)
    want_types = set(brief.intervention_type)
    for c, d in zip(cand, docs):
        dv = vec(d)
        text = sum(qv[t] * dv.get(t, 0) for t in qv) / (qn * norm(dv)) if qv and dv else 0.0
        shared = sorted((t for t in qv if t in dv), key=lambda t: -idf(t))[:2]
        lo, hi = cut.get("fev1_pct_predicted_min"), cut.get("fev1_pct_predicted_max")
        overlap = None
        if lo is not None and hi is not None and hi > lo and (c["fev1_min"] is not None or c["fev1_max"] is not None):
            a, b = c["fev1_min"] if c["fev1_min"] is not None else 0, c["fev1_max"] if c["fev1_max"] is not None else 100
            overlap = max(0.0, min(hi, b) - max(lo, a)) / (hi - lo)
        type_hit = bool(want_types & set(c["types"] or [])) if want_types else None
        # missing cutoff data must not penalise a trial: it falls back to its text score
        cut_eff = overlap if overlap is not None else text
        tscore = 0.5 if type_hit is None else float(type_hit)
        c["score"] = 0.7 * text + 0.2 * cut_eff + 0.1 * tscore
        c["parts"] = (text, overlap, tscore)
        bits = [phase_label(c["phases"]) + " " + cond_label(brief)]
        if overlap is not None:
            bits.append(f"FEV1 range overlaps {round(overlap * 100)}%")
        if shared:
            bits.append("primary outcome mentions " + join_and(shared))
        if type_hit:
            bits.append("same intervention type")
        c["why"] = ", ".join(bits)
    cand.sort(key=lambda c: (-c["score"], c["nct_id"]))
    if (brief.eligibility_text or "").strip() and cand:
        # Stage 2: compare eligibility WORDING for the best 200 candidates (works for any disease, no LLM).
        short = cand[:200]
        crit = dict(cx.q("1b. Eligibility text of the 200 best candidates (compared with your criteria)",
                         f"SELECT nct_id, criteria FROM study_eligibility WHERE nct_id IN ({ids_sql([c['nct_id'] for c in short])})"))
        edocs = [toks(crit.get(c["nct_id"])) for c in short]
        edf: dict[str, int] = {}
        for d in edocs:
            for t in set(d):
                edf[t] = edf.get(t, 0) + 1
        eidf = lambda t: math.log((len(short) + 1) / (edf.get(t, 0) + 1)) + 1
        evec = lambda ts: {t: ts.count(t) * eidf(t) for t in set(ts)}
        qe = evec(toks(brief.eligibility_text))
        qen = norm(qe)
        for c, d in zip(short, edocs):
            dv = evec(d)
            elig = sum(qe[t] * dv.get(t, 0) for t in qe) / (qen * norm(dv)) if qe and dv else 0.0
            text, overlap, tscore = c["parts"]
            cut_eff = overlap if overlap is not None else (text + elig) / 2
            c["score"] = 0.5 * text + 0.25 * elig + 0.15 * cut_eff + 0.1 * tscore
            if elig >= 0.25:
                c["why"] += f", eligibility wording overlaps {round(elig * 100)}%"
        short.sort(key=lambda c: (-c["score"], c["nct_id"]))
        cand = short + cand[200:]
    top = cand[:MAX_COMPARABLES]
    drop = set(excluded)  # removed AFTER ranking, so a removal lowers the count instead of pulling in a replacement
    top = [c for c in top if c["nct_id"] not in drop]
    return top, len(cand), pm_df


# ------------------------------------------------------------------ the whole run
WRITER_START_BY_S = 90  # the AI sentence writer (one ~4 s call) starts only if the run is younger than this


def run(brief, focus: list[str], excluded: list[str], progress=lambda step, status: None) -> dict:
    t_run = time.time()
    cx = Ctx()
    budget = llmsvc.Budget()
    notes: list[str] = []  # why a rule could not be checked (shown in the result)
    as_of = cx.q("0. Data as-of date (latest registry update in the database)", "SELECT max(last_update_post_date) FROM studies_current")[0][0]
    y, m_ = int(as_of[:4]), int(as_of[5:7])
    vy, vm = divmod(y * 12 + (m_ - 1) - cfg.SITES_STATUS_VERIFIED_MONTHS, 12)
    verified_from = f"{vy:04d}-{vm + 1:02d}"  # status must have been verified in this month or later
    pool = pool_sql(brief)
    copd = is_copd(brief)
    label = cond_label(brief)

    progress(1, "running")
    top, n_candidates, df = find_comparables(cx, brief, excluded)
    ids = [c["nct_id"] for c in top]
    IN = ids_sql(ids)
    progress(1, "done")

    # ---- step 2: how they ended, against the all-trials baseline for the condition
    progress(2, "running")
    comp_b = dict(cx.q("2a. Outcome buckets, comparables", f"""
SELECT {BUCKET_SQL} AS bucket, count(*) FROM studies_current s WHERE s.nct_id IN ({IN}) GROUP BY 1"""))
    base_b = dict(cx.q("2b. Outcome buckets, baseline (every interventional trial for the condition, any phase)", f"""
SELECT {BUCKET_SQL} AS bucket, count(*) FROM studies_current s
WHERE s.nct_id IN ({pool}) AND s.study_type='INTERVENTIONAL' GROUP BY 1"""))
    outcomes = {"comparables": {b: comp_b.get(b, 0) for b in BUCKETS}, "baseline": {b: base_b.get(b, 0) for b in BUCKETS}}
    # statuses and labels come back from SQL for the exact comparable ids
    st = {r[0]: r for r in cx.q("2c. Status, stop reason and stop label for each comparable", f"""
SELECT s.nct_id, s.overall_status, s.why_stopped, l.stop_cause, l.stop_tier, s.enrollment, s.has_results
FROM studies_current s LEFT JOIN study_labels l USING (nct_id) WHERE s.nct_id IN ({IN})""")}
    progress(2, "done")

    # ---- step 3: why they stopped (classifier labels already stored in study_labels)
    progress(3, "running")
    cause_rows = cx.q("3a. Stop causes among terminated comparables", f"""
SELECT l.stop_cause, l.stop_tier, count(*) AS n, list(s.nct_id ORDER BY s.nct_id) AS ids
FROM studies_current s LEFT JOIN study_labels l USING (nct_id)
WHERE s.nct_id IN ({IN}) AND s.overall_status='TERMINATED' GROUP BY 1, 2 ORDER BY n DESC""")
    stop_causes, enr_ids, term_ids = [], [], []
    for cause, tier, n, cids in cause_rows:
        term_ids += cids
        if cause == "enrollment":
            enr_ids = cids
        stop_causes.append({
            "cause": CAUSE_LABEL.get(cause, cause or "Reason unclear"), "count": n, "tier": TIER.get(tier, "unknown"),
            "quotes": [{"nct_id": i, "quote": (st[i][2] or "").strip()[:200] or None} for i in cids[:3]]})
    base_term = cx.q("3b. Baseline enrollment-stop share among all terminated trials for the condition", f"""
SELECT count(*), count(*) FILTER (WHERE l.stop_cause='enrollment')
FROM studies_current s LEFT JOIN study_labels l USING (nct_id)
WHERE s.nct_id IN ({pool}) AND s.study_type='INTERVENTIONAL' AND s.overall_status='TERMINATED'""")[0]
    progress(3, "done")

    # ---- step 4: element by element
    progress(4, "running")
    el: dict[str, dict] = {e: {"findings": []} for e in ["population", "endpoints", "size", "sites", "design"]}
    D: dict = {"n": len(ids)}
    cut = brief_cutoffs(brief)
    target = brief.target_enrollment
    want = set(focus)

    if "population" in want:
        # age floor (registry field, any condition)
        amin = cut.get("min_age")
        r = cx.q("4a. Minimum age of comparables (registry field)", f"""
SELECT count(*) FILTER (WHERE a IS NOT NULL), median(a), {'count(*) FILTER (WHERE a < ' + str(amin) + ')' if amin else 'NULL'},
       {'list(nct_id) FILTER (WHERE a < ' + str(amin) + ')' if amin else 'NULL'}, list(nct_id) FILTER (WHERE a IS NOT NULL)
FROM (SELECT e.nct_id, try_cast(regexp_extract(e.min_age, '(\\d+)', 1) AS INTEGER) AS a
      FROM study_eligibility e WHERE e.nct_id IN ({IN}) AND e.min_age ILIKE '%year%')""")[0]
        if r[0]:
            txt = f"Median minimum age across {r[0]} comparables with a stated age floor is {r[1]:g} years."
            el["population"]["findings"].append(F(txt, r[4] or [], r[0]))
            if amin and r[2]:
                el["population"]["findings"].append(F(f"{r[2]} of {r[0]} comparables accept patients younger than your minimum age of {amin:g}.", r[3] or []))
        if copd:
            cov = cx.q("4b. Comparables that have parsed eligibility cutoffs (precedent.duckdb copd_cutoffs)", f"""
SELECT list(nct_id ORDER BY nct_id) FROM prec.copd_cutoffs WHERE status='ok' AND nct_id IN ({IN})""")[0][0] or []
            D["cutoff_cov"] = len(cov)
            el["population"]["findings"].append(F(
                f"Parsed eligibility cutoffs exist for {len(cov)} of {len(ids)} comparables; the rest have not been parsed yet.", cov)
                if cov else F(f"Not found: none of the {len(ids)} comparables has parsed eligibility cutoffs yet.", []))

        # --- numeric cutoffs of the user's own criteria vs each comparable (any disease) ---
        D["cuts"] = []
        meta = brief_cutoff_meta(brief)
        cut_keys = [k for k in meta if k not in ("min_age", "max_age")]
        if cut_keys and ids:
            vals, info = comparable_cutoffs(cx, ids, cut_keys, meta, budget)
            D["cut_info"] = info
            for k in cut_keys:
                m, direction = meta[k], ("min" if k.endswith("_min") else "max")
                got = {n: v for n, v in vals[k].items() if v is not None}
                v0 = m["value"]
                looser = [n for n, x in got.items() if (x < v0 if direction == "min" else x > v0)]
                unit = f" {m['unit']}" if m["unit"] else ""
                D["cuts"].append(dict(key=k, label=m["label"], value=v0, unit=unit, direction=direction, got=got))
                el["population"]["findings"].append(
                    F(f"{len(looser)} of {len(got)} comparables with a stated {m['label'].lower()} used a looser limit than your {v0:g}{unit} "
                      f"(stated in {len(got)} of {len(ids)}).", looser, len(looser)) if got
                    else F(f"Not found: no comparable has a stated {m['label'].lower()} yet (read for {len(vals[k])} of {len(ids)}).", []))
        elif not cut_keys:
            el["population"]["findings"].append(F("No numeric cutoffs from your criteria to compare yet. Your eligibility wording was still used to rank comparables.", []))
            notes.append("Population: not checked. Your criteria contain no numeric cutoff to compare (age is compared separately), so there is nothing to parse.")

    if "endpoints" in want:
        # key words = the endpoint's words that real candidate trials also use (rare one-off words would flag everything)
        skip = set(toks(brief.condition + " " + " ".join(brief.mesh_terms)))  # the condition's own words say nothing about the endpoint
        ts = sorted((t for t in set(toks(brief.primary_endpoint)) if t not in skip and 2 <= df.get(t, 0) < n_candidates),
                    key=lambda t: (-df[t], t))[:cfg.ENDPOINT_KEYWORDS]
        if ts:
            need = min(cfg.ENDPOINT_MIN_SHARED, len(ts))
            hits = " + ".join(f"CASE WHEN regexp_matches(lower(p), {lit(re.escape(t))}) THEN 1 ELSE 0 END" for t in ts)
            r = cx.q("4d. Comparables with a similar primary endpoint, and whether the completed ones posted results", f"""
WITH pm AS (SELECT s.nct_id, s.overall_status AS st, coalesce(s.has_results, false) AS hr,
                   (SELECT string_agg(measure, ' | ') FROM study_outcomes o WHERE o.nct_id = s.nct_id AND o.kind = 'primary') AS p
            FROM studies_current s WHERE s.nct_id IN ({IN})),
     sim AS (SELECT *, {hits} AS hits FROM pm)
SELECT count(*), list(nct_id) FILTER (WHERE hits >= {need}),
       count(*) FILTER (WHERE hits >= {need} AND st = 'COMPLETED'),
       count(*) FILTER (WHERE hits >= {need} AND st = 'COMPLETED' AND hr),
       list(nct_id) FILTER (WHERE hits >= {need} AND st = 'COMPLETED' AND NOT hr)
FROM sim""")[0]
            hit = r[1] or []
            D["endpoint"] = dict(terms=ts, m=r[0], similar_ids=hit, done_n=r[2], done_with_results=r[3], done_no_results_ids=r[4] or [], all_ids=ids)
            el["endpoints"]["findings"].append(
                F(f"{len(hit)} of {r[0]} comparables list a primary outcome mentioning at least {need} of: {join_and(ts)}.", hit) if hit
                else F(f"Not found: none of the {r[0]} comparables mention at least {need} of: {join_and(ts)}.", []))
            if r[2]:
                el["endpoints"]["findings"].append(F(f"{r[3]} of {r[2]} completed comparables with a similar endpoint posted results.", r[4] or []) if r[4]
                                                   else F(f"All {r[2]} completed comparables with a similar endpoint posted results.", []))
        m = re.search(r"(\d+)\s*(week|month|day|year)", brief.primary_endpoint_timeframe or "", re.I)
        if m:
            pat = rf"\b{m.group(1)}\s*{m.group(2).lower()}"
            r = cx.q("4e. Comparables with the same primary timeframe", f"""
SELECT count(*), list(nct_id) FILTER (WHERE regexp_matches(lower(tf), {lit(pat)}))
FROM (SELECT s.nct_id, (SELECT string_agg(time_frame, ' | ') FROM study_outcomes o WHERE o.nct_id=s.nct_id AND o.kind='primary') AS tf
      FROM studies_current s WHERE s.nct_id IN ({IN}))""")[0]
            hit = r[1] or []
            el["endpoints"]["findings"].append(F(f"{len(hit)} of {r[0]} comparables use a primary timeframe of {m.group(1)} {m.group(2).lower()}s.", hit) if hit
                                               else F(f"Not found: no comparable lists a {m.group(1)} {m.group(2).lower()} primary timeframe.", []))

    if "size" in want and target:
        r = cx.q("4f. Actual enrollment of completed comparables vs your target", f"""
SELECT count(*), count(*) FILTER (WHERE enrollment < {int(target)}), median(enrollment),
       list(nct_id) FILTER (WHERE enrollment < {int(target)}), max(enrollment), list(nct_id ORDER BY nct_id)
FROM studies_current WHERE nct_id IN ({IN}) AND overall_status='COMPLETED' AND enrollment IS NOT NULL""")[0]
        D["size"] = dict(c=r[0], k=r[1], med=r[2], max=r[4], ids=r[5] or [], target=int(target))
        el["size"]["findings"].append(
            F(f"{r[1]} of {r[0]} completed comparables enrolled fewer than {int(target)} patients (median {r[2]:g}).", r[3] or [])
            if r[0] else F("Not found: no completed comparable reports an enrollment number.", []))
        if term_ids:
            el["size"]["findings"].append(F(f"{len(enr_ids)} of {len(term_ids)} terminated comparables stopped for slow enrollment "
                                            f"(baseline for the condition: {base_term[1]} of {base_term[0]}).", enr_ids))

    if "sites" in want and brief.countries:
        cs = ",".join(lit(c) for c in brief.countries)
        cand_ = cx.q("4h. Competing trials, step 1: same condition, recruiting or not yet recruiting, with a site in your countries", f"""
SELECT s.nct_id, s.last_update_post_date FROM studies_current s
WHERE s.nct_id IN ({pool}) AND s.study_type = 'INTERVENTIONAL' AND s.nct_id <> {lit(brief.nct_id or '')}
  AND s.overall_status IN ({",".join(lit(x) for x in cfg.SITES_STATUSES)})
  AND EXISTS (SELECT 1 FROM study_sites t WHERE t.nct_id = s.nct_id AND t.country IN ({cs}))""")
        # step 2 looks the candidates up by ID (index lookups). Joining back to the big table instead scans every record: ~16 s.
        fresh = {r[0] for r in cx.q("4i. Competing trials, step 2: keep those whose status was verified in the last 12 months", f"""
SELECT nct_id FROM studies_current WHERE nct_id IN ({ids_sql([r[0] for r in cand_])})
  AND substr(status_verified_date, 1, 7) >= {lit(verified_from)}""")}
        kept = sorted((r for r in cand_ if r[0] in fresh), key=lambda r: (str(r[1]) , r[0]), reverse=True)  # newest update first
        total, cids = len(kept), [r[0] for r in kept][:EVIDENCE_CAP]
        D["sites"] = dict(n=total, ids=cids)
        el["sites"]["findings"].append(F(f"{total} other {label} trials are recruiting or not yet recruiting (status verified since {verified_from}) with sites in {join_and(brief.countries)}.", cids, total)
                                       if total else F(f"Not found: no other {label} trials are recruiting in your countries.", []))

    if "design" in want:
        r = cx.q("4j. Design of comparables (allocation and masking from the record)", f"""
SELECT count(*), list(nct_id) FILTER (WHERE alloc='RANDOMIZED'), list(nct_id) FILTER (WHERE mask IN ('DOUBLE','TRIPLE','QUADRUPLE'))
FROM (SELECT nct_id, allocation AS alloc, masking AS mask
      FROM studies_current WHERE nct_id IN ({IN}))""")[0]
        el["design"]["findings"] += [
            F(f"{len(r[1] or [])} of {r[0]} comparables were randomised.", r[1] or []) if r[1] else F("Not found: no comparable states randomised allocation.", []),
            F(f"{len(r[2] or [])} of {r[0]} comparables were double-blind or more.", r[2] or []) if r[2] else F("Not found: no comparable states double-blind masking.", [])]
        arms = brief.arm_types
        control = None if not arms else any(a in cfg.DESIGN_CONTROL_ARMS for a in arms)
        stopped = cx.q("4l. Comparables that stopped with a reason mentioning placebo, ethics or a control arm", f"""
SELECT nct_id, why_stopped FROM studies_current
WHERE nct_id IN ({IN}) AND overall_status IN ({",".join(lit(x) for x in cfg.DESIGN_STOP_STATUSES)})
  AND regexp_matches(lower(coalesce(why_stopped, '')), {lit("|".join(re.escape(t) for t in cfg.DESIGN_TERMS))})""")
        D["design"] = dict(m=len(ids), control=control, stopped=[{"nct_id": n, "text": t} for n, t in stopped])
        el["design"]["findings"].append(
            F(f"{len(stopped)} of {len(ids)} comparables stopped with a reason mentioning {cfg.DESIGN_TERMS_LABEL}.", [n for n, _ in stopped]) if stopped
            else F(f"Not found: no comparable stopped with a reason mentioning {cfg.DESIGN_TERMS_LABEL}.", []))
    progress(4, "done")

    # ---- step 5: flag rules, then deterministic wording from the numbers above
    progress(5, "running")
    comps = []
    for c in top:
        s_ = st[c["nct_id"]]
        reason = (s_[2] or "").strip()
        comps.append({
            "nct_id": c["nct_id"], "title": c["title"] or "", "why_picked": c["why"], "similarity": round(min(1.0, c["score"]), 2),
            "status": s_[1], "stop_reason": reason if len(reason) >= 4 else None,
            "stop_tier": (TIER.get(s_[4], "unknown") if s_[1] in ("TERMINATED", "WITHDRAWN") else None),
            "enrollment": s_[5], "has_results": bool(s_[6])})
    flags, no_flags_reason = [], None
    if len(ids) < MIN_N:
        no_flags_reason = (f"Only {len(ids)} comparable trials were found. At least {MIN_N} are needed before a flag can be raised, "
                           "so none are shown rather than guessing from too little evidence.")
    else:
        found = []

        def take(result):
            f, note = result
            if f:
                found.append(f)
            if note:
                notes.append(note)

        if "population" in want:
            ci = D.get("cut_info", {})
            for cu in D.get("cuts", []):
                f, note = flagrules.population(cu, set(enr_ids))
                if note and ci.get("error"):
                    note += " " + ci["error"]
                take((f, note))
        if "sites" in want:
            take(flagrules.sites(D.get("sites"), brief.countries, label))
        if "endpoints" in want:
            take(flagrules.endpoint(D.get("endpoint")))
        if "design" in want:
            take(flagrules.design(D["design"]))
        if "size" in want:
            take(flagrules.size(D.get("size"), int(target) if target else None))
        flags = flagrules.rank(found)
        if flags and llmsvc.enabled() and time.time() - t_run >= WRITER_START_BY_S:
            notes.append(f"Flag sentences use the standard wording: the run had already taken over {WRITER_START_BY_S} seconds, so the AI writer was skipped.")
        elif flags and llmsvc.enabled():
            try:  # the AI only rewords each flag's finished sentence; code refuses anything not in the evidence
                w = writer.reword(flags, budget)
                if w["refused"]:
                    notes.append("Standard wording kept for: " + "; ".join(f"{k} ({v})" for k, v in w["refused"].items()) + ".")
            except llmsvc.LLMUnavailable as e:
                notes.append(f"Flag sentences use the standard wording. {e}")
        if not flags:
            no_flags_reason = "No rule found enough evidence to flag a risk against these comparables. That is a finding, not an error."
    progress(5, "done")

    # ---- bottom line
    n_term = outcomes["comparables"]["terminated"]
    n_te = len(enr_ids)
    bt, bb = sum(outcomes["baseline"].values()) or 1, outcomes["baseline"]["terminated"]
    excess = len(ids) > 0 and (n_term / len(ids)) > cfg.RISK_TERMINATION_EXCESS * (bb / bt)
    # risk = non-site flags + 1 if more comparables ended in termination than the baseline rate (+25%): 0 low, 1-2 medium, 3+ high
    score = sum(1 for f in flags if f["element"] != "sites") + (1 if excess else 0)
    risk = "insufficient" if len(ids) < MIN_N else "low" if score == 0 else "medium" if score <= cfg.RISK_MEDIUM_MAX else "high"
    sentence = f"{len(ids)} comparable trials; {n_term} terminated" + (f", {n_te} for slow enrollment." if n_te else ".")
    blank = sum(1 for i in term_ids if not (st[i][2] or "").strip())
    limits = [
        "The registry has no schedule of activities, so visit burden cannot be compared.",
        "Original enrollment targets are replaced by actual enrollment once a trial finishes, so size is compared against actual enrollment.",
        "No per-site enrollment is published, so site performance cannot be measured.",
        "Protocol amendment reasons are not recorded.",
        f"{blank} of {len(term_ids)} terminated comparables gave no stop reason (shown as 'reason not stated')." if term_ids else "No terminated comparables.",
        f"Comparables were ranked from {n_candidates} candidate trials that share the condition and phase; the search matches on text, not meaning.",
        "There is no recency filter: older trials can be comparables if their design and endpoint match.",
        "Stop reasons use a rule-based classifier on the registry's free text; 'outside source' means the text alone cannot explain the stop."]
    ci = D.get("cut_info")
    if ci:
        if ci["error"]:
            limits.append(ci["error"])
        if ci["ai"]:
            limits.append(f"Comparable cutoffs were read by an AI ({ci['calls']} calls this run) and each is kept only if its quoted sentence is in the trial text."
                          + (f" {ci['not_yet_read']} comparables are not read yet: Re-run to continue." if ci["not_yet_read"] else ""))
    if copd:
        limits.append(f"{D.get('cutoff_cov', 0)} of {len(ids)} comparables have COPD cutoffs parsed in advance; the rest are read on demand when an AI key is set.")
    else:
        limits.insert(0, "Basic condition support: comparables and outcomes come from the registry and eligibility is compared by wording. Numeric cutoffs of comparables are read by an AI when a key is set.")
    return {
        "run_id": "", "brief_echo": brief.model_dump(), "data_as_of": as_of, "condition_support": "full" if copd else "basic",
        "bottom_line": {"risk": risk, "n_comparables": len(ids), "n_terminated": n_term, "n_terminated_enrollment": n_te, "sentence": sentence},
        "comparables": comps, "outcomes": outcomes, "stop_causes": stop_causes, "elements": el, "flags": flags,
        "no_flags_reason": no_flags_reason, "rule_notes": notes, "ai_usage": {"calls": budget.used, "tokens": budget.tokens, "own_key": bool(llmsvc.current())}, "limits": limits, "diff": None, "package_id": None, "audit": cx.audit}


def apply_diff(parent: dict, res: dict) -> dict:
    """Diff by flag rule id. Kept/deferred decisions carry over; an accepted flag that still fires re-opens."""
    old = {f["id"]: f for f in parent["flags"]}
    new = {f["id"]: f for f in res["flags"]}
    d = {"resolved": [], "still_open": [], "new": []}
    for fid, f in new.items():
        o = old.get(fid)
        if not o:
            d["new"].append({"id": fid, "title": f["title"]})
            continue
        if o["status"] in ("kept", "deferred"):
            f["status"], f["decision"] = o["status"], o["decision"]
        d["still_open"].append({"id": fid, "title": f["title"]})
    for fid, o in old.items():
        if fid not in new:
            d["resolved"].append({"id": fid, "title": o["title"]})
    res["diff"] = d
    return res


# ------------------------------------------------------------------ small lookups
def trial_summary(nct: str) -> dict | None:
    cx = Ctx()
    r = cx.q("trial", f"""
SELECT s.nct_id, s.brief_title, s.overall_status, s.why_stopped, l.stop_tier, s.enrollment, s.has_results,
       s.lead_sponsor, s.phases, s.start_date,
       (SELECT list(DISTINCT country ORDER BY country) FROM study_sites t WHERE t.nct_id = s.nct_id)
FROM studies_current s LEFT JOIN study_labels l USING (nct_id) WHERE s.nct_id = {lit(nct)}""")
    if not r:
        return None
    n, title, status, why, tier, enr, hr, sp, ph, sd, ctry = r[0]
    return {"nct_id": n, "title": title or "", "status": status, "stop_reason": (why or "").strip() or None,
            "stop_tier": TIER.get(tier) if status in ("TERMINATED", "WITHDRAWN") else None, "enrollment": enr,
            "has_results": bool(hr), "sponsor": sp or "", "phase": phase_label(ph), "start_date": sd or "", "countries": (ctry or [])[:12]}


from .criteria import KEY_LABEL  # noqa: E402
from . import llmsvc, readers, writer  # noqa: E402


def cached_cutoffs(eligibility_text: str) -> list[dict] | None:
    """Cutoffs already parsed earlier (precedent.duckdb) for a trial whose eligibility text is identical. Free, no LLM."""
    cx = Ctx()
    hit = cx.q("cutoff lookup", f"SELECT nct_id FROM prec.copd_trials WHERE eligibility_text = {lit(eligibility_text)} LIMIT 1")
    if not hit:
        return None
    cols = cx.con.execute("SELECT * FROM prec.copd_cutoffs WHERE nct_id = ? AND status = 'ok'", [hit[0][0]]).fetchall()
    if not cols:
        return None
    names = [d[0] for d in cx.con.description]
    row = dict(zip(names, cols[0]))
    out = []
    for k, lab in KEY_LABEL.items():
        if row.get(f"{k}_status") in ("ok", "invalid"):
            out.append({"key": k, "field": lab, "value": row.get(f"{k}_value"), "unit": row.get(f"{k}_unit") or "",
                        "source_sentence": row.get(f"{k}_source") or "", "valid": row.get(f"{k}_status") == "ok"})
    return out


def health() -> dict:
    cx = Ctx()
    as_of = cx.q("as of", "SELECT max(last_update_post_date) FROM studies_current")[0][0]
    return {"data_as_of": as_of, "row_counts": {
        "studies_current": cx.q("n", "SELECT count(*) FROM studies_current")[0][0],
        "copd_trials": cx.q("n", "SELECT count(*) FROM prec.copd_trials")[0][0],
        "copd_cutoffs_parsed": cx.q("n", "SELECT count(*) FROM prec.copd_cutoffs WHERE status='ok'")[0][0]}}


def suggest_conditions(q: str) -> list[dict]:
    """Registry conditions (MeSH terms) that match what the user typed, with how many interventional trials each has."""
    q = q.strip()
    if len(q) < 2:
        return []
    cx = Ctx()
    words = " AND ".join(f"c.term ILIKE {lit('%' + w + '%')}" for w in q.split())  # every typed word, any order
    rows = cx.q("condition suggestions", f"""
SELECT c.term, count(DISTINCT c.nct_id) AS n FROM study_conditions c JOIN studies_current s USING (nct_id)
WHERE c.kind = 'mesh' AND {words} AND s.study_type = 'INTERVENTIONAL'
GROUP BY c.term ORDER BY n DESC, c.term LIMIT 8""")
    return [{"term": t, "n_trials": n} for t, n in rows]
