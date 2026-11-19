"""Chooses the pack(s) for a design. A pack matches when one of its MeSH terms is among the design's condition terms or their parents,
and none of its excluded terms is. Indication packs beat area packs. Several matches: highest priority, then most matched terms, then id."""


def _q(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def design_terms(cx, brief) -> list[str]:
    """The design's own MeSH terms plus their parents. A parent counts only if at least 60% of a random sample (200) of trials carrying that
    condition have it. Trials often carry several conditions, so a parent of one of THOSE would otherwise leak in (EVALS R09: bronchiectasis went to COPD).
    The sample is random, not the oldest trials: old records often lack parent terms (R10: only 42% of the 50 oldest heart failure trials had one, 95% overall)."""
    own = [t for t in (brief.mesh_terms or []) if t]
    if not own:
        return []
    terms = ",".join(_q(t) for t in own)
    rows = cx.q("P1. Parent MeSH terms of the design's condition (used to route to a pack)", f"""
WITH smp AS (SELECT own, nct_id FROM (SELECT term AS own, nct_id, row_number() OVER (PARTITION BY term ORDER BY hash(nct_id)) AS rn
                                      FROM study_conditions WHERE kind = 'mesh' AND term IN ({terms})) WHERE rn <= 200),
     tot AS (SELECT own, count(*) AS n FROM smp GROUP BY own)
SELECT DISTINCT a.term FROM smp JOIN study_conditions a ON a.nct_id = smp.nct_id AND a.kind = 'ancestor' JOIN tot USING (own)
GROUP BY smp.own, a.term, tot.n HAVING count(DISTINCT smp.nct_id) >= 0.6 * tot.n""")
    return sorted(set(own) | {r[0] for r in rows})


def matches(packs: dict, terms: list[str]) -> list[dict]:
    have = set(terms)
    out = []
    for p in packs.values():
        if p["level"] == "base":
            continue
        r = p["routing"]
        hit = sorted(have & set(r.get("mesh_terms", [])))
        blocked = sorted(have & set(r.get("exclude_mesh_terms", [])))
        if hit and not blocked:
            out.append({"id": p["id"], "level": p["level"], "label": p.get("label", p["id"]), "priority": r.get("priority", 0),
                        "matched_terms": hit, "version": p["version"], "status": p["status"], "parent": r.get("parent")})
    out.sort(key=lambda m: (-m["priority"], -len(m["matched_terms"]), m["id"]))
    return out


def route(cx, brief, packs: dict) -> dict:
    """{indication, area, matches, design_terms, reason}. indication and area are pack ids or None (None for both = the base prompt only)."""
    terms = design_terms(cx, brief)
    if not terms:
        return {"indication": None, "area": None, "matches": [], "design_terms": [],
                "reason": "The design has no MeSH condition term, so no pack could be chosen. The base prompt is used."}
    ms = matches(packs, terms)
    ind = next((m for m in ms if m["level"] == "indication"), None)
    areas = [m for m in ms if m["level"] == "area"]
    area = None
    if ind and ind["parent"] and ind["parent"] in packs:
        area = ind["parent"]          # the indication's own area, so the pair always belongs together
    elif areas:
        area = areas[0]["id"]
    if not ind and not area:
        return {"indication": None, "area": None, "matches": ms, "design_terms": terms,
                "reason": "No pack matches this condition. The base prompt is used."}
    names = " > ".join(packs[x].get("label", x) for x in (area, ind["id"] if ind else None) if x)
    return {"indication": ind["id"] if ind else None, "area": area, "matches": ms, "design_terms": terms,
            "reason": f"Matched {names} through the condition's MeSH terms."}
