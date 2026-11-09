"""Rule-based eligibility reader (free, no LLM). Works for any disease; Phase C adds an LLM pass.

It only reports what a sentence literally says: a named measure, a direction (min or max) and a number.
Every result carries the verbatim source sentence, so the user can see (and edit) what it read.
"""
import re

NUM = r"(\d+(?:\.\d+)?)"
UNIT = r"(%|years?|months?|weeks?|days?|kg/m2|kg/m²|mg/dl|mmol/l|ml/min(?:/1\.73\s*m²|/1\.73\s*m2)?|mg|g/dl|pack[- ]years?|cells/µl|cells/ul|mmhg|bpm|%\s*predicted)"
GE = r"(?:≥|>=|at least|no less than|greater than or equal to|above|more than|greater than|over|>)"
LE = r"(?:≤|<=|at most|no more than|up to|less than or equal to|below|under|less than|fewer than|<)"
STOPWORDS = {"of", "the", "a", "an", "and", "or", "in", "with", "patient", "patients", "subject", "subjects", "participants",
             "has", "have", "had", "is", "are", "be", "was", "at", "screening", "baseline", "level", "levels", "value", "values",
             "history", "documented", "diagnosis", "post-bronchodilator", "pre-bronchodilator", "measured", "current", "most", "recent"}
EVENT_WORDS = r"(exacerbations?|hospitali[sz]ations?|episodes?|relapses?|attacks?|seizures?|infections?|fractures?|events?)"


def _name(before: str) -> str:
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9\-/]*", before) if w.lower() not in STOPWORDS]
    return " ".join(words[-2:]) if words else ""


def _key(name: str, suffix: str, unit: str) -> str:
    n = name.lower()
    if re.search(r"fev1\s*/\s*fvc", n) or n in ("fev1/fvc", "fvc ratio"):
        return "fev1_fvc_ratio_max"  # (same keys as the COPD cutoff table, so COPD flags can use them)
    if n.startswith("fev1") or n.endswith("fev1"):
        return f"fev1_pct_predicted_{suffix}"
    if "pack" in unit or "pack" in n:
        return f"smoking_pack_years_{suffix}"
    return re.sub(r"[^a-z0-9]+", "_", n).strip("_") + "_" + suffix


KEY_LABEL = {"min_age": "Minimum age", "max_age": "Maximum age", "fev1_pct_predicted_min": "FEV1 % predicted (min)",
             "fev1_pct_predicted_max": "FEV1 % predicted (max)", "fev1_fvc_ratio_max": "FEV1/FVC ratio (max)",
             "exacerbations_prior_year_min": "Prior exacerbations (min)", "smoking_pack_years_min": "Smoking history (min)",
             "current_smokers_allowed": "Current smokers allowed", "asthma_excluded": "Asthma excluded"}


def _cut(key, label, value, unit, sentence):
    unit = "" if unit in ("x", "and", "or", "to", "the", "with", "of") else unit
    return {"key": key, "field": KEY_LABEL.get(key, label), "value": f"{value:g}" if isinstance(value, float) else str(value), "unit": unit,
            "source_sentence": sentence, "valid": True}


HEADER = re.compile(r"^\W*(?:(?:key|main|major|general|additional|other)\s+)?(inclusion|exclusion)(?:\s+criteria)?\s*:?\s*$", re.I)


def _flip_key(k: str) -> str:
    if k == "min_age":
        return "max_age"
    if k == "max_age":
        return "min_age"
    if k.endswith("_min"):
        return k[:-4] + "_max"
    if k.endswith("_max"):
        return k[:-4] + "_min"
    return k


def _as_exclusion(found: list[dict]) -> list[dict]:
    """A limit under 'Exclusion Criteria' says who is OUT, so the eligibility limit points the other way:
    'excluded if greater than 15 mg' means a ceiling (max 15). A min+max pair from one line ('excluded if between A and B')
    is an excluded BAND, not a single limit, so it is skipped rather than guessed."""
    if len(found) == 2 and _flip_key(found[0]["key"]) == found[1]["key"]:
        return []
    out = []
    for c in found:
        c = dict(c)
        k = _flip_key(c["key"])
        c["key"] = k
        swap = {"(min)": "(max)", "(max)": "(min)", "Minimum": "Maximum", "Maximum": "Minimum"}
        c["field"] = KEY_LABEL.get(k) or re.sub(r"\((?:min|max)\)|Minimum|Maximum", lambda m: swap[m.group(0)], c["field"])
        out.append(c)
    return out


def _parse_line(line: str) -> list[dict]:
    """The limits one line sets, read as an INCLUSION rule."""
    low = line.lower()
    # --- age ---
    m = re.search(rf"\bage[d]?\b[^0-9]{{0,25}}{NUM}\s*(?:to|-|\u2013|and)\s*{NUM}\s*years?", low) or \
        re.search(rf"\b{NUM}\s*(?:to|-|\u2013)\s*{NUM}\s*years?\s*(?:of age|old)", low)
    if m:
        return [_cut("min_age", "Minimum age", float(m.group(1)), "years", line), _cut("max_age", "Maximum age", float(m.group(2)), "years", line)]
    m = re.search(rf"\b(?:age[d]?|older than|at least)\b[^0-9]{{0,25}}{NUM}\s*years?(?:\s*(?:or older|and older|of age or older))", low) or \
        re.search(rf"\b(?:age[d]?)\s*{GE}\s*{NUM}", low)
    if m:
        return [_cut("min_age", "Minimum age", float(m.group(1)), "years", line)]
    # --- counted events in a window: "at least 2 ... exacerbations in the previous 12 months" ---
    m = re.search(rf"{GE}\s*{NUM}\s+(?:[a-z\-]+\s+){{0,5}}?{EVENT_WORDS}", low)
    if m:
        noun = m.group(2).rstrip("s")
        key = "exacerbations_prior_year_min" if noun.startswith("exacerbation") else f"{noun}s_prior_min"
        return [_cut(key, f"Prior {noun}s (min)", float(m.group(1)), "events", line)]
    # --- "<measure> between A and B <unit>" / "<measure> A to B <unit>" ---
    m = re.search(rf"([A-Za-z][A-Za-z0-9\-/ ]{{1,40}}?)\s*(?:between|of|from|:)?\s*{NUM}\s*{UNIT}?\s*(?:and|to|-|\u2013)\s*{NUM}\s*{UNIT}?", low)
    if m and _name(m.group(1)):
        name, lo, hi = _name(m.group(1)), float(m.group(2)), float(m.group(4))
        unit = m.group(5) or m.group(3) or ""
        if hi > lo:
            lab = name.upper() if len(name) < 6 else name.title()
            return [_cut(_key(name, "min", unit), f"{lab} (min)", lo, unit, line), _cut(_key(name, "max", unit), f"{lab} (max)", hi, unit, line)]
    # --- "<measure> >= N <unit>" / "< N" ---
    for op, suffix in ((GE, "min"), (LE, "max")):
        m = re.search(rf"([A-Za-z][A-Za-z0-9\-/ ]{{1,40}}?)\s*(?:is|was|of)?\s*{op}\s*{NUM}\s*(?P<unit>%|years?|kg/m2|kg/m\u00b2|mg/dl|mmol/l|ml/min|pack[- ]years?|mmhg|[a-z/\u00b5]+)?", low)
        if m and _name(m.group(1)):
            name = _name(m.group(1))
            unit = m.groupdict().get("unit") or ""
            if unit in ("and", "or", "to", "the", "with", "of"):
                unit = ""
            if unit == "x" and re.search(r"uln|upper limit", low):  # "creatinine > 2 x ULN" is a multiple of the lab's normal limit
                unit = "x ULN"
            if re.match(r"(month|week|day|year)", unit):  # "psoriasis for at least 6 months" is a duration, not a measure
                name = " ".join(w for w in name.split() if w != "for") + " duration"
            label = (name.upper() if len(name) < 6 else name.title()) + f" ({suffix})"
            return [_cut(_key(name, suffix, unit), label, float(m.group(2)), unit, line)]
    return []


def parse_criteria(text: str) -> list[dict]:
    out, seen = [], set()
    mode = "inclusion"  # switches when an "Inclusion Criteria" / "Exclusion Criteria" heading is read
    for raw in re.split(r"[\n\r]+", text or ""):
        line = re.sub(r"^[\s*\-\u2022\d.)]+", "", raw).strip()
        h = HEADER.match(line)
        if h:
            mode = h.group(1).lower()
            continue
        if len(line) < 6:
            continue
        found = _parse_line(line)
        if mode == "exclusion":
            found = _as_exclusion(found)
        for c in found:
            if (c["key"], c["value"]) not in seen:
                seen.add((c["key"], c["value"]))
                out.append(c)
    return out
