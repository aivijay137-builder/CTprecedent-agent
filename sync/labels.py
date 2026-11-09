"""Derived labels (scope, category, stop cause), recomputed only for new or changed studies.
Same rules as ../derive.py (rules copied to label_rules.py); reads the flat tables instead of the raw JSON."""
import re

import pandas as pd

from .label_rules import CATS, NEG, RULES

LABEL_VERSION = "v1-part7-part3"  # same as derive.py, so labels copied from ctg.duckdb stay valid
GROUP = {c[0]: c[1] for c in CATS}
BRIEF_GROUPS = {"Core lung disease", "Other lung", "Acute and critical", "Upper airway", "Respiratory infection"}
STOPPED = ("TERMINATED", "WITHDRAWN", "SUSPENDED")


def classify_stop(t):
    if not isinstance(t, str) or len(t.strip()) < 4:
        return ("empty_or_blank", "C")
    s = re.sub(NEG, "", t.lower())
    for name, tier, pat in RULES:
        if re.search(pat, s):
            return (name, tier)
    return ("other_unclear", "C")


def categorise(r):
    """r: DataFrame with nct_id, title, conditions, keywords, mesh, overall_status, why_stopped."""
    mesh = r.mesh.fillna("")
    has_mesh = mesh.str.len() > 0
    cond = r.conditions.fillna("").str.lower()
    fb = (r.keywords.fillna("") + " " + r.title.fillna("")).str.lower()
    flags = {}
    for name, grp, mesh_re, anc_re, text_re in CATS:
        flags[name] = mesh.str.contains(mesh_re, regex=True) | cond.str.contains(text_re, regex=True) | ((~has_mesh) & fb.str.contains(text_re, regex=True))
    specific = [c[0] for c in CATS if c[0] != "Other respiratory (residual)"]
    flags["Other respiratory (residual)"] &= ~pd.concat([flags[c] for c in specific], axis=1).any(axis=1)
    names = [c[0] for c in CATS]
    out = pd.DataFrame({"nct_id": r.nct_id.values})
    prim, ment = [], []
    for i in range(len(r)):
        hit = [n for n in names if flags[n].iloc[i]]
        prim.append(hit[0] if hit else None)
        ment.append("|".join(hit))
    out["primary_category"] = prim
    out["mentions"] = ment
    out["category_group"] = out.primary_category.map(GROUP)
    out["in_scope"] = out.category_group.isin(BRIEF_GROUPS)
    out["lung_cancer_mention"] = flags["Lung cancer (adjacent)"].values
    stop = [classify_stop(w) if s in STOPPED else (None, None) for s, w in zip(r.overall_status, r.why_stopped)]
    out["stop_cause"] = [x[0] for x in stop]
    out["stop_tier"] = [x[1] for x in stop]
    out["label_version"] = LABEL_VERSION
    return out


INPUTS = """SELECT s.nct_id, s.brief_title AS title, s.overall_status, s.why_stopped, s.keywords,
  (SELECT string_agg(term, '|') FROM study_conditions c WHERE c.nct_id = s.nct_id AND c.kind = 'text') AS conditions,
  (SELECT string_agg(term, '|') FROM study_conditions c WHERE c.nct_id = s.nct_id AND c.kind = 'mesh') AS mesh
FROM studies_current s WHERE s.nct_id IN (SELECT nct_id FROM _ids)"""


def label_ids(con, ids):
    con.execute("CREATE OR REPLACE TEMP TABLE _ids AS SELECT unnest($1::VARCHAR[]) AS nct_id", [list(ids)])
    out = categorise(con.execute(INPUTS).df())
    con.register("_lab", out)
    con.execute("INSERT OR REPLACE INTO study_labels SELECT nct_id, primary_category, mentions, category_group, in_scope, lung_cancer_mention, stop_cause, stop_tier, label_version, current_timestamp FROM _lab")
    con.unregister("_lab")
    return out


def label_stale(con, chunk=10000):
    """Label every study with no label, an old label_version, or edited since it was labelled. Returns how many."""
    ids = [x[0] for x in con.execute("""SELECT s.nct_id FROM studies_current s LEFT JOIN study_labels l USING (nct_id)
        WHERE l.nct_id IS NULL OR l.label_version <> ? OR s.row_updated_at > l.derived_at ORDER BY 1""", [LABEL_VERSION]).fetchall()]
    for i in range(0, len(ids), chunk):
        label_ids(con, ids[i:i + chunk])
    return len(ids)
