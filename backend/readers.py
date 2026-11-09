"""AI eligibility readers (Phase C), built on ONE common prompt template (version v4, see PROMPTS.md).

Step 1  parse_design:    read the user's own criteria -> a list of limits (name, min/max, number, unit, exact quote).
Step 2  extract_targets: for each comparable trial, read ONLY the fields from step 1 (so every disease works with the same prompt).

The model never decides what is true: every quote is checked against the source text in code, and anything that fails is dropped
or marked invalid. Numbers must be numbers. "not stated" is a normal, stored answer.
"""
import json
import re
import time
from contextlib import closing

from . import appdb, llmsvc
from .criteria import KEY_LABEL

VERSION = "v5"
TEXT_LIMIT = 3500  # characters of one trial's eligibility text sent to the model (long texts are cut; the answer says so)
BATCH = 5  # trials per call
RETRY_BATCH = 2  # trials the model left out of a reply are asked again in smaller calls
NS = "not stated"

RULES = """You are a careful reader of clinical-trial eligibility text. You only copy what the text says. You never decide what is clinically reasonable.

1. NEVER GUESS. If a limit is not written in the text, return {"value": "not stated", "unit": null, "source_sentence": null}. Silence is a normal answer. A wrong number is much worse than "not stated".
2. EXACT QUOTE. source_sentence is copied character for character from the text: the single bullet or sentence that states the limit. Never reword, shorten or join sentences.
3. NUMBERS. value is a plain number: no symbols, no words, no ranges. Keep the unit as written (years, %, mg/dL, mL/min, kg/m2, x ULN, cells/mm3, days, weeks...). Do not convert units. A multiple of the upper limit of normal is a number with the unit "x ULN".
4. DIRECTION IS ABOUT WHO CAN ENTER THE TRIAL.
   - "min" is the lowest value allowed in. "max" is the highest value allowed in.
   - Under INCLUSION (or no heading), the wording gives the limit directly: "at least 18", ">= 18", "older than 18" -> min. "up to 75", "< 75", "no more than 75" -> max.
   - Under EXCLUSION (or wording like "excluded if", "must not have", "ineligible if"), the wording says who is kept OUT, so the limit points the other way: "excluded if eGFR < 30" -> min = 30. "excluded if age > 75" -> max = 75.
   - If a sentence excludes a band ("excluded if between A and B"), it is not one limit: skip it.
   - "between A and B" under inclusion is two items: min = A and max = B.
   - Decide direction from the section the sentence is in AND its wording. If you cannot tell, leave it out.
5. ONE LIMIT, ONE ITEM. Count thresholds ("at least 2 events in the past 12 months") are a limit on the count; put the window in the name (events_prior_12_months). Ignore limits with no number (for example "adequate renal function").
6. NAMES. Use a short lowercase snake_case name for what is measured (age, hba1c, bmi, egfr, lvef, anc, ecog, fev1_pct_predicted, pasi_score ...). The same measure must always get the same name. Age is always "age" in years.
7. EXAMPLES, from different areas (illustrative only, not hints about the text):
   "Inclusion: HbA1c 7.0% to 10.5%" -> hba1c min 7 (%), hba1c max 10.5 (%)
   "Inclusion: ANC >= 1.5 x 10^9/L" -> anc min 1.5 (x10^9/L)
   "Inclusion: LVEF <= 40%" -> lvef max 40 (%)
   "Exclusion: ALT > 3 x ULN" -> alt max 3 (x ULN)
   "Exclusion: eGFR < 30 mL/min/1.73 m2" -> egfr min 30 (mL/min/1.73 m2)
   "Exclusion: pregnant or breast feeding" -> nothing (no number)"""

DESIGN_SYSTEM = RULES + """

TASK: The user message is JSON: {"condition": ..., "text": ...}. List every numeric entry limit in "text".
Return JSON only: {"criteria": [{"name": ..., "direction": "min" or "max", "value": <number>, "unit": ..., "section": "inclusion" or "exclusion", "source_sentence": ...}]}
If the text sets no numeric limit, return {"criteria": []}."""

TARGET_SYSTEM = RULES + """

TASK: The user message is JSON: "fields" (each has a key such as hba1c_min, where _min is the lowest value allowed in and _max the highest) and "trials" (a list; each item has an "id" and its "text").
For each trial, for each field, return the limit that trial sets, using only the text with the same id. Never mix trials.
Return JSON only: {"trials": {"<id>": {"<field key>": {"value": <number or "not stated">, "unit": ..., "source_sentence": ...}, ...}, ...}}
Return an entry for EVERY trial id you were given and EVERY field key asked, even when everything is "not stated". Only the listed keys, spelled exactly.
If the trial states the limit in the other direction only, return "not stated" for the asked key.
Worked example. Text: "Inclusion: HbA1c < 9.5%. Exclusion: HbA1c > 12%." Asked hba1c_min -> "not stated" (the text sets no lowest value; the exclusion line is a ceiling of 12, which is hba1c_max, and the tighter inclusion ceiling 9.5 is the one that applies).
Text: "Exclusion: eGFR < 45" -> egfr_min = 45. Text: "Exclusion: age > 75" -> age_max = 75. If one field has two limits in the same direction, give the one stated first under Inclusion."""


# ---------------------------------------------------------------- guardrails
def _norm(s: str) -> str:
    s = re.sub(r"\\(?=[<>*#_\-^~])", "", s or "")  # CT.gov stores some characters escaped
    s = s.translate(str.maketrans({"\u2267": "\u2265", "\u2266": "\u2264", "\u2a7e": "\u2265", "\u2a7d": "\u2264"}))  # registries write >= and <= with look-alike symbols
    s = re.sub(r"\s*([≥≤<>=])\s*", r"\1", s)  # spacing around a comparison does not change what the sentence says
    return re.sub(r"\s+", " ", s).strip().lower()


def quote_ok(text: str, quote: str | None) -> bool:
    return bool(quote) and len(_norm(quote)) >= 4 and _norm(quote) in _norm(text)


def _num(v):
    try:
        return float(re.sub(r"[^\d.\-]", "", str(v))) if v not in (None, "", NS) and re.search(r"\d", str(v)) else None
    except ValueError:
        return None


def _label(name: str, direction: str) -> str:
    key = f"{name}_{direction}"
    return KEY_LABEL.get(key) or f"{name.replace('_', ' ').capitalize()} ({direction})"


# ---------------------------------------------------------------- step 1: the user's design
def parse_design(text: str, condition: str, budget: llmsvc.Budget | None = None) -> list[dict]:
    """Cutoff dicts in the API shape. valid=False and an empty source_sentence when the model's quote is not in the text."""
    out = llmsvc.ask("parse_design", VERSION, DESIGN_SYSTEM, json.dumps({"condition": condition, "text": text[:8000]}), budget)
    cuts, seen = [], set()
    for it in out.get("criteria") or []:
        name = re.sub(r"[^a-z0-9]+", "_", str(it.get("name", "")).lower()).strip("_")
        d = it.get("direction")
        val = _num(it.get("value"))
        if not name or d not in ("min", "max") or val is None or (name, d, val) in seen:
            continue
        seen.add((name, d, val))
        q = it.get("source_sentence")
        ok = quote_ok(text, q)
        cuts.append({"key": f"{name}_{d}" if name != "age" else f"{d}_age", "field": _label(name, d) if name != "age" else f"{'Minimum' if d == 'min' else 'Maximum'} age",
                     "value": f"{val:g}", "unit": str(it.get("unit") or ""), "source_sentence": q if ok else "", "valid": ok})
    return cuts


# ---------------------------------------------------------------- step 2: the comparables
def _cached(ids: list[str], keys: list[str]) -> dict[tuple[str, str], dict]:
    if not ids or not keys:
        return {}
    with closing(appdb._c()) as c:
        rows = c.execute(f"SELECT nct_id,key,status,value,unit,source FROM cutoff_cache WHERE prompt_version=? AND nct_id IN ({','.join('?' * len(ids))}) AND key IN ({','.join('?' * len(keys))})",
                         [VERSION, *ids, *keys]).fetchall()
    return {(r["nct_id"], r["key"]): dict(r) for r in rows}


def extract_targets(texts: dict[str, str], fields: list[dict], budget: llmsvc.Budget | None = None, deadline: float | None = None) -> dict:
    """texts: nct_id -> eligibility text. fields: [{key, label}]. Returns {(nct, key): {status, value, unit, source}} for everything
    known so far (cache + new calls). Stops starting new calls after `deadline` (time.time() value); returns a summary too."""
    keys = [f["key"] for f in fields]
    known = _cached(list(texts), keys)
    todo = [n for n in texts if any((n, k) not in known for k in keys)]
    done_calls, error = 0, ""
    queue = [(todo[i:i + BATCH], 1) for i in range(0, len(todo), BATCH)]  # (trials, attempt)
    while queue:
        if deadline and time.time() > deadline:
            break
        batch, attempt = queue.pop(0)
        user = json.dumps({"fields": [{"key": f["key"], "label": f.get("label", f["key"])} for f in fields],
                           "trials": [{"id": n, "text": texts[n][:TEXT_LIMIT]} for n in batch]})
        try:
            out = llmsvc.ask("extract_targets", VERSION, TARGET_SYSTEM, user, budget)
        except llmsvc.LLMUnavailable as e:
            error = str(e)
            break
        done_calls += 1
        got = out.get("trials") or {}
        left_out = []
        with closing(appdb._c()) as c, c:
            for n in batch:
                row = got.get(n)
                if not isinstance(row, dict) or any(k not in row for k in keys):
                    left_out.append(n)  # the model skipped this trial (or a field): that is NOT "not stated"
                if not isinstance(row, dict):
                    continue
                for k in keys:
                    if k not in row:
                        continue
                    it = row.get(k) or {}
                    v = _num(it.get("value"))
                    if v is not None and quote_ok(texts[n], it.get("source_sentence")):
                        rec = dict(status="ok", value=f"{v:g}", unit=str(it.get("unit") or ""), source=it["source_sentence"])
                    elif v is None:
                        rec = dict(status="not_stated", value=None, unit=None, source=None)
                    else:  # a number without a real quote: refuse to use it
                        rec = dict(status="invalid", value=None, unit=None, source=None)
                    c.execute("INSERT OR REPLACE INTO cutoff_cache VALUES(?,?,?,?,?,?,?,?,?)",
                              (n, k, VERSION, rec["status"], rec["value"], rec["unit"], rec["source"], "ai", appdb.now()))
                    known[(n, k)] = {"nct_id": n, "key": k, **rec}
        if left_out and attempt == 1:  # ask again, in smaller calls, once
            queue += [(left_out[i:i + RETRY_BATCH], 2) for i in range(0, len(left_out), RETRY_BATCH)]
    left = len([n for n in texts if any((n, k) not in known for k in keys)])
    return {"values": known, "calls": done_calls, "not_yet_read": left, "error": error}
