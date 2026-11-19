"""How many comparables would a design have if one filter were loosened? Read-only SQL on the registry; the engine is not touched.

The count mirrors the engine's candidate query in engine.find_comparables (same condition pool, interventional, phase overlap,
not the draft itself), which is what decides "insufficient" (fewer than flag_config.MIN_N). backend/test_relax.py checks the two agree.

Relaxations (the enum in docs/agent_design.md):
  phase            drop the phase filter
  condition_level  widen the condition to its closest MeSH parent (smallest parent pool; parents use the router's 60% rule)
intervention_class is not here: with no pack there is no such hard filter, so there is nothing to loosen.
"""
from . import engine
from .packlib import router

RELAX = ("phase", "condition_level")


def parent_term(cx, brief) -> str | None:
    """The closest parent of the design's own MeSH terms: the parent with the smallest interventional pool. None if there is no parent."""
    own = {t for t in (brief.mesh_terms or []) if t}
    parents = [t for t in router.design_terms(cx, brief) if t not in own]
    if not parents:
        return None
    ids = ",".join(engine.lit(t) for t in parents)
    rows = cx.con.execute(f"""
SELECT c.term, count(DISTINCT c.nct_id) FROM study_conditions c JOIN studies_current s USING (nct_id)
WHERE c.kind IN ('mesh','ancestor') AND c.term IN ({ids}) AND s.study_type='INTERVENTIONAL' GROUP BY 1 ORDER BY 2, 1""").fetchall()
    return rows[0][0] if rows else None


def count(cx, brief, relax=(), parent: str | None = None) -> int:
    """Candidate trials under the given relaxations. `parent` is the term from parent_term(); needed for condition_level."""
    pool = engine.pool_sql(brief)
    if "condition_level" in relax:
        if not parent:
            return -1  # not available for this design
        pool = f"{pool} UNION SELECT DISTINCT nct_id FROM study_conditions WHERE kind IN ('mesh','ancestor') AND term = {engine.lit(parent)}"
    phase = "TRUE" if "phase" in relax else engine.phase_pred(brief)
    return cx.con.execute(f"""SELECT count(DISTINCT s.nct_id) FROM studies_current s
WHERE s.nct_id IN ({pool}) AND s.study_type = 'INTERVENTIONAL' AND {phase} AND s.nct_id <> {engine.lit(brief.nct_id or '')}""").fetchone()[0]
