"""Unit tests for the five flag rules: pure functions, no database, no AI. Run: python -m pytest backend/test_flagrules.py -q"""
import pytest

from backend import flag_config as cfg, flagrules as fr

LABELS = {"stated", "outside", "unknown"}


def ids(n, prefix="NCT0000"):
    return [f"{prefix}{i:04d}" for i in range(n)]


def check_flag(f):
    """Rules every flag must satisfy."""
    assert f["n"] >= cfg.MIN_N and f["evidence_ids"] and f["confidence"] in LABELS
    assert f["status"] == "open" and f["title"] and f["question"]


# ------------------------------------------------------------ 1. population
def cu(values, v=2.0, direction="min"):
    return {"key": "exacerbations_prior_year_min", "label": "Prior exacerbations (min)", "value": v, "unit": " events",
            "direction": direction, "got": dict(zip(ids(len(values)), values))}


def test_population_fires_at_75_percent_when_stricter_ones_stop_more_for_enrollment():
    c = cu([1] * 6 + [3] * 2)  # design = 2: six comparables looser (75%), two as strict or stricter
    strict_ids = ids(8)[6:]
    f, note = fr.population(c, {strict_ids[0]})  # one strict trial stopped for enrollment, no looser one did
    assert note is None and f["id"] == "pop_exacerbation_stricter" and f["n"] == 8 and f["confidence"] == "stated"
    check_flag(f)
    assert "75%" in f["body"] and "50%" in f["body"] and "0%" in f["body"]


def test_population_below_75_percent_or_no_enrollment_gap_does_not_fire():
    assert fr.population(cu([1] * 5 + [3] * 3), {ids(8)[7]})[0] is None  # 62.5% looser
    assert fr.population(cu([1] * 6 + [3] * 2), {ids(8)[0]})[0] is None  # the enrollment stop was in a LOOSER trial
    assert fr.population(cu([1] * 6 + [3] * 2), set())[0] is None  # nobody stopped for enrollment
    assert fr.population(cu([1] * 8), {ids(8)[0]})[0] is None  # no stricter group to compare with


def test_population_needs_min_n_and_says_why_it_skipped():
    f, note = fr.population(cu([1, 1, 1, 3]), {ids(4)[3]})
    assert f is None and "Only 4 comparables" in note and "at least 5" in note


def test_population_max_direction_and_any_condition_key():
    c = {"key": "hba1c_max", "label": "HbA1c (max)", "value": 9.0, "unit": " %", "direction": "max",
         "got": dict(zip(ids(8), [10, 10, 10, 10, 10, 10, 8, 8]))}  # comparables allowing up to 10 are LOOSER than a 9 ceiling
    f, _ = fr.population(c, {ids(8)[6]})
    assert f["id"] == "pop_hba1c_max_stricter" and f["n"] == 8


# ------------------------------------------------------------ 2. sites
def test_sites_default_threshold_is_10():
    assert cfg.SITES_MIN_TRIALS == 10
    assert fr.sites({"n": 9, "ids": ids(9)}, ["Germany"], "COPD") == (None, None)
    f, _ = fr.sites({"n": 10, "ids": ids(10)}, ["Germany", "Poland"], "COPD")
    check_flag(f)
    assert f["id"] == "sites_competing_trials" and f["n"] == 10 and "12 months" in f["body"]


def test_sites_threshold_comes_from_config_and_never_goes_below_min_n(monkeypatch):
    monkeypatch.setattr(cfg, "SITES_MIN_TRIALS", 15)
    assert fr.sites({"n": 12, "ids": ids(12)}, ["Germany"], "x")[0] is None
    monkeypatch.setattr(cfg, "SITES_MIN_TRIALS", 2)  # below MIN_N: the floor of 5 still applies
    assert fr.sites({"n": 4, "ids": ids(4)}, ["Germany"], "x")[0] is None
    assert fr.sites({"n": 5, "ids": ids(5)}, ["Germany"], "x")[0] is not None


def test_sites_without_countries_says_why():
    f, note = fr.sites({"n": 50, "ids": ids(50)}, [], "x")
    assert f is None and "no countries" in note


# ------------------------------------------------------------ 3. endpoint
def ep(m=30, similar=10, done=0, with_results=0):
    return {"terms": ["fev1", "trough"], "m": m, "similar_ids": ids(similar), "done_n": done, "done_with_results": with_results,
            "done_no_results_ids": ids(done - with_results, "NCT9"), "all_ids": ids(m)}


def test_endpoint_fires_under_20_percent_similar():
    assert fr.endpoint(ep(m=30, similar=6))[0] is None  # exactly 20%: not under
    f, _ = fr.endpoint(ep(m=30, similar=5))  # 16.7%
    check_flag(f)
    assert f["id"] == "endpoint_precedent" and f["n"] == 30 and "uncommon" in f["title"]


def test_endpoint_fires_when_completed_ones_posted_results_under_half():
    assert fr.endpoint(ep(similar=15, done=6, with_results=3))[0] is None  # exactly 50%: not under
    f, _ = fr.endpoint(ep(similar=15, done=6, with_results=2))
    check_flag(f)
    assert "rarely posted results" in f["title"] and f["n"] == 6
    assert fr.endpoint(ep(similar=15, done=4, with_results=0))[0] is None  # only 4 completed: below min n


def test_endpoint_both_conditions_and_min_n():
    f, _ = fr.endpoint(ep(m=30, similar=5, done=6, with_results=1))
    assert "uncommon" in f["title"] and "rarely posted" in f["title"]
    assert fr.endpoint(ep(m=4, similar=0))[0] is None  # fewer than 5 comparables
    assert fr.endpoint(None)[1].startswith("Endpoint: not checked")


# ------------------------------------------------------------ 4. design
def des(control=True, stopped=1, m=30):
    return {"m": m, "control": control, "stopped": [{"nct_id": i, "text": "stopped: placebo concerns"} for i in ids(stopped)]}


def test_design_fires_with_two_stopped_trials_and_a_control_arm():
    assert fr.design(des(stopped=1)) == (None, None)  # one stopped trial is an anecdote, not a pattern
    f, _ = fr.design(des(stopped=2))
    check_flag(f)
    assert f["id"] == "design_control_arm_stops" and f["n"] == 30 and f["evidence_ids"] == ids(2)
    assert "mentioning placebo, ethics or a control arm" in f["body"]


def test_design_skips_without_a_control_arm_or_without_stops_and_says_why():
    assert fr.design(des(control=False))[1].startswith("Design: not checked. The design has no placebo or control arm")
    assert "does not say" in fr.design(des(control=None))[1]
    assert fr.design(des(stopped=0)) == (None, None)
    assert fr.design(des(m=4))[0] is None


# ------------------------------------------------------------ 5. sample size (demoted)
def test_size_fires_only_at_2x_the_maximum_actual_enrollment():
    sz = {"c": 12, "max": 200, "ids": ids(12)}
    assert fr.size(sz, 399)[0] is None
    f, _ = fr.size(sz, 400)
    check_flag(f)
    assert f["id"] == "size_above_actual" and f["n"] == 12
    assert f["confidence"] == "stated"  # regression: it used to say "outside source" with no source linked
    assert fr.size({"c": 4, "max": 100, "ids": ids(4)}, 1000)[0] is None  # fewer than 5 completed comparables


# ------------------------------------------------------------ confidence labels and ranking
def test_outside_source_only_with_a_link_and_unknown_only_when_the_record_is_silent():
    base = dict(fid="x", element="size", title="t", body="b", question="q", action_label="a", n=5, strength=5, evidence_ids=ids(5))
    assert fr.make_flag(**base)["confidence"] == "stated"
    assert fr.make_flag(**base, source_url="https://example.org/paper")["confidence"] == "outside"
    assert fr.make_flag(**base, silent=True)["confidence"] == "unknown"


def mk(element, strength):
    return fr.make_flag(element, element, "t", "b", "q", "a", 5, strength, ids(5))


def test_rank_by_strength_then_tie_order_and_max_three():
    flags = [mk("size", 20), mk("design", 20), mk("endpoints", 20), mk("sites", 20), mk("population", 20)]
    assert [f["element"] for f in fr.rank(flags)] == ["population", "sites", "endpoints"]  # ties: population, sites, endpoint, design, size
    assert [f["element"] for f in fr.rank([mk("population", 6), mk("size", 40), mk("sites", 11)])] == ["size", "sites", "population"]
    assert all("_strength" not in f for f in fr.rank(flags))
    assert len(fr.rank([mk("sites", 1)] * 2)) == 2


def test_all_thresholds_live_in_config():
    for name in ("MIN_N", "MAX_FLAGS", "TIE_ORDER", "POPULATION_STRICTER_SHARE", "SITES_MIN_TRIALS", "SITES_STATUS_VERIFIED_MONTHS",
                 "ENDPOINT_SIMILAR_MAX_SHARE", "ENDPOINT_RESULTS_MIN_SHARE", "DESIGN_TERMS", "DESIGN_MIN_STOPPED", "SIZE_TARGET_VS_MAX_RATIO"):
        assert hasattr(cfg, name)
    assert (cfg.MIN_N, cfg.MAX_FLAGS, cfg.POPULATION_STRICTER_SHARE, cfg.SITES_MIN_TRIALS, cfg.ENDPOINT_SIMILAR_MAX_SHARE,
            cfg.ENDPOINT_RESULTS_MIN_SHARE, cfg.SIZE_TARGET_VS_MAX_RATIO) == (5, 3, 0.75, 10, 0.20, 0.50, 2.0)


# ------------------------------------------------------------ Step 3 contract: every rule has one case that fires and one that does not
def _pop_fires():
    return fr.population(cu([1] * 6 + [3] * 2), {ids(8)[6]})[0]


def _pop_silent():
    return fr.population(cu([1] * 6 + [3] * 2), set())[0]  # same numbers, but nobody stopped for enrollment


PAIRS = {
    "population": (_pop_fires, _pop_silent),
    "sites": (lambda: fr.sites({"n": 10, "ids": ids(10)}, ["Germany"], "COPD")[0], lambda: fr.sites({"n": 9, "ids": ids(9)}, ["Germany"], "COPD")[0]),
    "endpoint": (lambda: fr.endpoint(ep(m=30, similar=5))[0], lambda: fr.endpoint(ep(m=30, similar=6))[0]),
    "design": (lambda: fr.design(des(stopped=2))[0], lambda: fr.design(des(stopped=1))[0]),
    "size": (lambda: fr.size({"c": 12, "max": 200, "ids": ids(12)}, 400)[0], lambda: fr.size({"c": 12, "max": 200, "ids": ids(12)}, 399)[0]),
}


@pytest.mark.parametrize("rule", list(PAIRS))
def test_each_rule_has_one_case_that_fires_and_one_that_does_not(rule):
    fires, silent = PAIRS[rule]
    flag = fires()
    assert flag is not None, f"{rule} should fire"
    check_flag(flag)
    assert silent() is None, f"{rule} should NOT fire"
