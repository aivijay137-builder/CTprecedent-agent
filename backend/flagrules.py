"""The five flag rules, as small pure functions: numbers in -> (flag or None, note or None).

No database and no AI in here, so every rule can be tested on its own. All thresholds come from flag_config.py.
`note` is set only when a rule COULD NOT be evaluated (missing input); it is shown to the user as "why this was not checked".

Confidence labels (the only three that exist):
  stated   = "Stated in record": computed from registry fields (counts, enrollment, sites, stop reasons, arm types).
  outside  = "Supported by outside source": ONLY when a source_url is attached. No rule attaches one today, so none uses it.
  unknown  = "Not stated": the record is silent. Rules skip (with a note) instead of firing on silence, so none uses it today.
"""
from . import flag_config as cfg

CAP = 50  # evidence NCT IDs kept per flag; n is always the true count


def make_flag(fid, element, title, body, question, action_label, n, strength, evidence_ids, source_url=None, silent=False):
    """Every flag carries n, evidence NCT IDs and a confidence label. 'outside' needs a real link; otherwise it is 'stated'."""
    confidence = "unknown" if silent else ("outside" if source_url else "stated")
    ids = list(dict.fromkeys(evidence_ids))[:CAP]
    return {"id": fid, "element": element, "title": title, "body": body, "question": question, "confidence": confidence,
            "evidence_ids": ids, "n": n, "source_url": source_url, "action_label": action_label,
            "status": "open", "decision": None, "_strength": strength}


def _join(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def pct(x):
    return f"{round(x * 100)}%"


# ---------------------------------------------------------------- 1. population
def population(cu: dict, enr_ids: set):
    """cu: {key, label, value, unit, direction ('min'|'max'), got: {nct_id: number}} (only comparables that state the cutoff)."""
    got, v, label = cu["got"], cu["value"], cu["label"]
    n = len(got)
    if n < cfg.MIN_N:
        return None, (f"Population ({label}): not checked. Only {n} comparables have this cutoff parsed; at least {cfg.MIN_N} are needed.")
    looser = [t for t, x in got.items() if (x < v if cu["direction"] == "min" else x > v)]
    strict = [t for t in got if t not in set(looser)]  # as strict as the design, or stricter
    if len(looser) / n < cfg.POPULATION_STRICTER_SHARE or not strict or not looser:
        return None, None
    rate_s = sum(1 for t in strict if t in enr_ids) / len(strict)
    rate_l = sum(1 for t in looser if t in enr_ids) / len(looser)
    if not rate_s > rate_l:
        return None, None
    unit = cu["unit"]
    exac = cu["key"] == "exacerbations_prior_year_min"
    return make_flag(
        "pop_exacerbation_stricter" if exac else f"pop_{cu['key']}_stricter", "population",
        "Exacerbation rule stricter than most comparables" if exac else f"{label} stricter than most comparables",
        f"Your {label.lower()} of {v:g}{unit} is stricter than {len(looser)} of {n} comparables that state one ({pct(len(looser) / n)}). "
        f"The {len(strict)} that were as strict or stricter stopped for slow enrollment {pct(rate_s)} of the time, against {pct(rate_l)} for the {len(looser)} looser ones.",
        f"Is {v:g}{unit} needed for this mechanism?", "Edit eligibility", n, len(looser), list(got)), None


# ---------------------------------------------------------------- 2. sites
def sites(info, countries: list, label: str):
    """info: {n: trials found, ids: NCT IDs (capped)} or None when not evaluated."""
    if not countries:
        return None, "Sites: not checked. The design lists no countries."
    need = max(cfg.SITES_MIN_TRIALS, cfg.MIN_N)
    if not info or info["n"] < need:
        return None, None
    return make_flag(
        "sites_competing_trials", "sites", f"{info['n']} {label} trials recruiting in your {len(countries)} countr{'y' if len(countries) == 1 else 'ies'}",
        f"{info['n']} other {label} trials are recruiting or not yet recruiting with a site in {_join(countries)}. "
        f"Only trials whose status was verified in the last {cfg.SITES_STATUS_VERIFIED_MONTHS} months are counted.",
        "Which of your planned sites overlap with these trials?", "Review sites", info["n"], info["n"], info["ids"]), None


# ---------------------------------------------------------------- 3. endpoint
def endpoint(ep):
    """ep: {terms, m (comparables), similar_ids, done_n (completed, similar endpoint), done_with_results, done_no_results_ids, all_ids} or None."""
    if not ep:
        return None, "Endpoint: not checked. The draft endpoint has no distinctive words to compare."
    m, sim = ep["m"], len(ep["similar_ids"])
    uncommon = m >= cfg.MIN_N and sim / m < cfg.ENDPOINT_SIMILAR_MAX_SHARE
    quiet = ep["done_n"] >= cfg.MIN_N and ep["done_with_results"] / ep["done_n"] < cfg.ENDPOINT_RESULTS_MIN_SHARE
    if not (uncommon or quiet):
        return None, None
    terms = _join(ep["terms"])
    parts, evidence, n, strength = [], [], 0, 0
    if uncommon:
        parts.append(f"Only {sim} of {m} comparables list a primary outcome mentioning {terms} (under {pct(cfg.ENDPOINT_SIMILAR_MAX_SHARE)}).")
        evidence += ep["all_ids"]
        n, strength = max(n, m), max(strength, m - sim)
    if quiet:
        parts.append(f"Of {ep['done_n']} completed comparables with a similar endpoint, only {ep['done_with_results']} posted results "
                     f"({pct(ep['done_with_results'] / ep['done_n'])}, under {pct(cfg.ENDPOINT_RESULTS_MIN_SHARE)}).")
        evidence += ep["done_no_results_ids"]
        n, strength = max(n, ep["done_n"]), max(strength, ep["done_n"] - ep["done_with_results"])
    title = ("Your primary endpoint is uncommon, and comparables with it rarely posted results" if uncommon and quiet else
             "Your primary endpoint is uncommon among comparables" if uncommon else "Comparables with a similar endpoint rarely posted results")
    return make_flag("endpoint_precedent", "endpoints", title, " ".join(parts),
                     "Is there a reason to depart from the endpoint most comparables used, or to plan results reporting differently?",
                     "Review endpoint", n, strength, evidence), None


# ---------------------------------------------------------------- 4. design
def design(des):
    """des: {m (comparables), control: None (unknown) | bool, stopped: [{nct_id, text}]}."""
    if des["control"] is None:
        return None, "Design: not checked. The design does not say whether it has a control arm."
    if not des["control"]:
        return None, "Design: not checked. The design has no placebo or control arm."
    stopped = des["stopped"]
    if des["m"] < cfg.MIN_N or len(stopped) < cfg.DESIGN_MIN_STOPPED:
        return None, None
    ids = [s["nct_id"] for s in stopped]
    return make_flag(
        "design_control_arm_stops", "design", "Comparables stopped over placebo, ethics or control-arm concerns",
        f"{len(ids)} of {des['m']} comparables stopped with a reason mentioning {cfg.DESIGN_TERMS_LABEL}. "
        "Your design has a control arm.",
        "How will your control arm be justified to ethics committees and to patients?", "Review design", des["m"], len(ids), ids), None


# ---------------------------------------------------------------- 5. sample size (demoted)
def size(sz, target):
    """sz: {c (completed comparables with an enrollment number), max, ids} or None."""
    if not target or not sz:
        return None, None
    if sz["c"] < cfg.MIN_N or target < cfg.SIZE_TARGET_VS_MAX_RATIO * sz["max"]:
        return None, None
    return make_flag(
        "size_above_actual", "size", f"Target of {target} is far above any comparable's actual enrollment",
        f"Your target is {target / sz['max']:.1f} times the largest actual enrollment ({sz['max']}) among {sz['c']} completed comparables. "
        "Original targets are not kept by the registry, so this compares against actual enrollment.",
        f"Is {target} driven by power, or carried over from an earlier design?", "Review sample size", sz["c"], sz["c"], sz["ids"]), None


# ---------------------------------------------------------------- ranking
def rank(flags: list) -> list:
    """Strongest first (most supporting trials); ties follow cfg.TIE_ORDER. At most cfg.MAX_FLAGS. Internal strength is removed."""
    order = {e: i for i, e in enumerate(cfg.TIE_ORDER)}
    top = sorted(flags, key=lambda f: (-f["_strength"], order.get(f["element"], 99)))[:cfg.MAX_FLAGS]
    return [{k: v for k, v in f.items() if k != "_strength"} for f in top]  # copies: the input list is left untouched
