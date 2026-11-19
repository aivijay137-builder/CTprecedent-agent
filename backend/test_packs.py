"""Pack loader, router, merge and ranking (fixture packs, fake registry: no real data needed). Run: python -m pytest backend/test_packs.py -q"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.packlib import loader, merge, rank, router

FIX = Path(__file__).parent / "fixtures" / "packs"


@pytest.fixture(autouse=True)
def fixture_packs(monkeypatch):
    monkeypatch.setenv("PACKS_DIR", str(FIX))


def brief(**kw):
    base = dict(condition="COPD", mesh_terms=["Pulmonary Disease, Chronic Obstructive"], intervention_type=["DRUG"], primary_endpoint="Change from baseline in FEV1")
    base.update(kw)
    return SimpleNamespace(**base)


class FakeCx:
    """Stands in for the registry connection: answers the two pack queries from canned data."""
    def __init__(self, parents=(), extras=None):
        self.parents, self.extras, self.asked = list(parents), extras or {}, []

    def q(self, name, sql):
        self.asked.append(name)
        if name.startswith("P1"):
            return [(t,) for t in self.parents]
        if name.startswith("P2"):
            return [(n, y, t) for n, (y, t) in self.extras.items()]
        raise AssertionError(name)


COPD_PARENTS = ["Lung Diseases, Obstructive", "Lung Diseases", "Respiratory Tract Diseases"]


# ---------------------------------------------------------------- loader
def test_loader_finds_and_lists_packs():
    assert loader.available()
    packs = loader.load_all()
    assert set(packs) == {"_base", "respiratory", "cardiovascular", "oncology_solid", "copd"}
    assert {p["id"] for p in loader.summary(packs)} == {"respiratory", "cardiovascular", "oncology_solid", "copd"}  # base is not offered


def test_loader_reports_a_broken_pack(tmp_path, monkeypatch):
    (tmp_path / "areas").mkdir()
    (tmp_path / "_base.yaml").write_text("id: _base\nlevel: base\nversion: 1\nstatus: draft\nrouting: {}\nprompt_addon: x\n")
    (tmp_path / "areas" / "bad.yaml").write_text("id: bad\nlevel: area\n")
    monkeypatch.setenv("PACKS_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="bad.yaml"):
        loader.load_all()


def test_no_pack_files_means_not_available(tmp_path, monkeypatch):
    monkeypatch.setenv("PACKS_DIR", str(tmp_path))
    assert not loader.available()


# ---------------------------------------------------------------- router
def test_copd_design_routes_to_indication_and_its_area():
    r = router.route(FakeCx(COPD_PARENTS), brief(), loader.load_all())
    assert (r["indication"], r["area"]) == ("copd", "respiratory")


def test_a_cancer_design_is_not_routed_to_respiratory():
    b = brief(condition="Lung cancer", mesh_terms=["Carcinoma, Non-Small-Cell Lung"])
    r = router.route(FakeCx(["Lung Neoplasms", "Neoplasms", "Respiratory Tract Diseases"]), b, loader.load_all())
    assert (r["indication"], r["area"]) == (None, "oncology_solid")   # respiratory excludes Neoplasms


def test_equal_priority_is_decided_by_more_matched_terms_then_id():
    packs = loader.load_all()
    ms = router.matches(packs, ["Respiratory Tract Diseases", "Cardiovascular Diseases"])
    assert [m["id"] for m in ms] == ["cardiovascular", "respiratory"]   # cardiovascular matches 2 of its terms; same priority


def test_no_mesh_term_or_no_match_uses_the_base_prompt():
    r = router.route(FakeCx(), brief(mesh_terms=[]), loader.load_all())
    assert (r["indication"], r["area"]) == (None, None) and "no MeSH" in r["reason"]
    r = router.route(FakeCx(["Eye Diseases"]), brief(mesh_terms=["Glaucoma"]), loader.load_all())
    assert (r["indication"], r["area"]) == (None, None) and "No pack matches" in r["reason"]


# ---------------------------------------------------------------- merge
def eff(parts=None, area="respiratory", ind="copd"):
    return merge.merge(loader.load_all(), area, ind, parts)


def test_merge_orders_addon_area_first_then_indication_and_adds_measure_hints():
    text = merge.addon_for(eff())
    assert text.index("AREA NOTES (Respiratory)") < text.index("INDICATION NOTES (COPD)")
    assert "fev1_pct (% predicted)" in text and "fev1_fvc (ratio)" in text


def test_more_specific_pack_replaces_an_item_with_the_same_name():
    subs = {s["name"]: s for s in eff()["subtypes"]}
    assert set(subs) == {"copd", "asthma", "frequent_exacerbators"}
    assert subs["copd"]["regex"] == "copd"      # the indication's version, not the area's "copd|chronic obstructive"


def test_nothing_chosen_means_no_effective_pack_and_no_addon():
    assert merge.merge(loader.load_all(), None, None) is None
    assert merge.addon_for(None) == ""


def test_addon_switch_off_gives_empty_text_but_keeps_other_parts():
    e = eff({"addon": False})
    assert merge.addon_for(e) == "" and e["parts"] == {"addon": False, "ranking": True, "hard_filter": True, "era": False}


def test_area_only_pack_works_without_an_indication():
    e = eff(ind=None)
    assert e["ids"] == ["respiratory"] and "INDICATION" not in e["addon_text"]


# ---------------------------------------------------------------- ranking
def cands(n, types=("DRUG",)):
    return [{"nct_id": f"NCT{i:08d}", "title": f"Trial {i}", "score": 1.0 - i * 0.001, "types": list(types), "pm": "change in fev1", "why": "base"} for i in range(1, n + 1)]


def test_hard_filter_removes_other_classes_when_enough_remain():
    c = cands(10) + cands(3, ("DEVICE",))
    for i, x in enumerate(c[10:]):
        x["nct_id"] = f"NCT9000000{i}"
    out, log = rank.apply(FakeCx(extras={}), c, brief(), eff({"ranking": False}))
    assert len(out) == 10 and all("DRUG" in x["types"] for x in out)
    assert log["hard_filter"]["applied"] and log["hard_filter"]["removed"] == 3


def test_hard_filter_is_relaxed_and_logged_when_fewer_than_five_would_remain():
    drugs, devices = cands(3), cands(8, ("DEVICE",))
    for i, x in enumerate(devices):
        x["nct_id"] = f"NCT9000000{i}"
    out, log = rank.apply(FakeCx(), drugs + devices, brief(), eff({"ranking": False}))
    assert len(out) == 11                                   # nothing removed
    h = log["hard_filter"]
    assert h["relaxed"] and not h["applied"] and h["would_remove"] == 8 and "relaxed" in h["reason"]


def test_hard_filter_never_removes_a_trial_with_no_intervention_type():
    c = cands(6) + cands(2, ())
    for i, x in enumerate(c[6:]):
        x["nct_id"] = f"NCT9100000{i}"
    out, _ = rank.apply(FakeCx(), c, brief(), eff({"ranking": False}))
    assert len(out) == 8


def test_design_without_intervention_type_is_not_filtered():
    out, log = rank.apply(FakeCx(), cands(5) + cands(3, ("DEVICE",)), brief(intervention_type=[]), eff({"ranking": False}))
    assert len(out) == 8 and "no intervention type" in log["hard_filter"]["reason"]


def test_hints_reorder_but_never_remove_and_keep_the_engines_scores():
    c = cands(6)
    c[5]["title"] = "COPD exacerbation study"          # rank 6 shares the design's subtype
    extras = {x["nct_id"]: (2020, "copd") if x is c[5] else (2020, "") for x in c}
    out, log = rank.apply(FakeCx(extras=extras), c, brief(), eff({"hard_filter": False}))
    assert {x["nct_id"] for x in out} == {x["nct_id"] for x in c}                 # nobody removed
    assert out[0]["nct_id"] == c[5]["nct_id"]                                     # boosted to the top
    assert out[0]["score"] == pytest.approx(1.0 - 6 * 0.001)                      # similarity shown is still the engine's
    assert "pack boost: same subtype" in out[0]["why"] and log["ranking"]["boosted_subtype"] == 1


def test_era_penalty_and_endpoint_type_boost():
    c = cands(3)
    c[0]["pm"] = "number of deaths"                     # a different endpoint type from the design's FEV1 change
    extras = {c[0]["nct_id"]: (2010, ""), c[1]["nct_id"]: (2010, ""), c[2]["nct_id"]: (2019, "")}
    out, log = rank.apply(FakeCx(extras=extras), c, brief(), eff({"hard_filter": False, "era": True}))
    g = log["ranking"]
    assert g["design_endpoint_type"] == "lab_or_physiologic_change"
    assert g["boosted_endpoint_type"] == 2               # the two FEV1 trials; the 'deaths' trial is not boosted
    assert g["penalised_era"] == 2                       # the fixture pack's breakpoint is 2015: the two 2010 trials are penalised, the 2019 one is not
    assert out[0]["nct_id"] == c[2]["nct_id"]            # 2019 + same endpoint type: boosted and not penalised, so first
    assert out[-1]["nct_id"] == c[0]["nct_id"]           # 2010 + different endpoint type: penalised and not boosted, so last


def test_era_penalty_is_off_by_default():
    c = cands(3)
    extras = {x["nct_id"]: (2010, "") for x in c}
    _, log = rank.apply(FakeCx(extras=extras), c, brief(), eff({"hard_filter": False}))
    assert log["ranking"]["penalised_era"] == 0 and log["ranking"]["era_applied"] is False


def test_switching_every_part_off_returns_the_list_untouched():
    c = cands(7)
    out, log = rank.apply(FakeCx(), c, brief(), eff({"ranking": False, "hard_filter": False, "era": False}))
    assert [x["nct_id"] for x in out] == [x["nct_id"] for x in c]
    assert not log["hard_filter"]["applied"] and not log["ranking"]["applied"]


def test_ranking_only_looks_at_the_leading_window(monkeypatch):
    monkeypatch.setattr(rank, "WINDOW", 3)
    c = cands(6)
    c[5]["title"] = "copd"
    extras = {x["nct_id"]: (2020, "copd" if x is c[5] else "") for x in c}
    out, _ = rank.apply(FakeCx(extras=extras), c, brief(), eff({"hard_filter": False}))
    assert [x["nct_id"] for x in out][3:] == [x["nct_id"] for x in c][3:]            # beyond the window: order kept
