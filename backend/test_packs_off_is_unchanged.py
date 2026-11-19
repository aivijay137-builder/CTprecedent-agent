"""THE guarantee: with no pack chosen, the engine returns exactly what it returned before packs existed.
Compares three real designs (AI off, local registry copy) with the golden snapshot in backend/golden/golden_base_runs.json.
Skips itself where the registry is missing. Run: python -m pytest backend/test_packs_off_is_unchanged.py -q"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "golden"))
import make_golden  # noqa: E402
from backend.packlib import loader, merge  # noqa: E402

GOLDEN = json.loads((Path(__file__).parent / "golden" / "golden_base_runs.json").read_text(encoding="utf-8"))
_designs: dict = {}
LIVE = "sites_competing_trials"  # counts trials recruiting now, so n and the ID list move with every registry sync


SIM_TOL = 0.02  # similarity is rounded to 2 places and computed over the candidate pool, so one score can move 0.01 when the registry grows


def same(a: dict, b: dict) -> bool:
    """Equal to the golden snapshot in everything except registry drift: the live site count (that flag's n and evidence_ids)
    and similarity scores, which may differ by up to SIM_TOL. IDs, order, flags, bottom line and rule notes must match exactly."""
    def stable(d):
        d = json.loads(json.dumps(d))
        for f in d["flags"]:
            if f["id"] == LIVE:
                f["n"], f["evidence_ids"] = None, None
        sim = d.pop("similarity")
        return json.dumps(d, sort_keys=True), sim
    (x, xs), (y, ys) = stable(a), stable(b)
    return x == y and len(xs) == len(ys) and all(abs(p - q) <= SIM_TOL for p, q in zip(xs, ys))


def designs() -> dict:
    """Built on first use, not at import: building a design reads the registry, which CI does not have."""
    if not _designs:
        _designs.update(make_golden.designs())
    return _designs


@pytest.fixture(autouse=True)
def ai_off(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "off")


def run(name, pack=None):
    from backend import engine
    r = engine.run(designs()[name], ["population", "endpoints", "size", "sites", "design"], [], pack=pack)
    return {"comparables": [c["nct_id"] for c in r["comparables"]], "similarity": [c["similarity"] for c in r["comparables"]],
            "flags": [{"id": f["id"], "n": f["n"], "evidence_ids": f["evidence_ids"]} for f in r["flags"]],
            "bottom_line": r["bottom_line"], "rule_notes": r["rule_notes"]}, r


@pytest.mark.parametrize("name", list(GOLDEN))
def test_prompt_only_matches_the_golden_snapshot(name):
    snap, full = run(name)
    assert same(snap, GOLDEN[name])
    assert full["pack"] is None


@pytest.mark.parametrize("name", list(GOLDEN))
def test_a_pack_with_every_part_switched_off_also_matches_the_golden_snapshot(name):
    if not loader.available():
        pytest.skip("no pack files on this machine")
    packs = loader.load_all()
    eff = merge.merge(packs, "respiratory", None, {"addon": False, "ranking": False, "hard_filter": False})
    snap, full = run(name, eff)
    assert same(snap, GOLDEN[name])
    assert full["pack"]["hard_filter"]["applied"] is False and full["pack"]["ranking"]["applied"] is False


@pytest.mark.parametrize("name", list(GOLDEN))
def test_a_pack_with_every_part_switched_off_equals_prompt_only_exactly(name):
    """No tolerance and no golden file: both runs read the same registry state, so they must be identical."""
    if not loader.available():
        pytest.skip("no pack files on this machine")
    eff = merge.merge(loader.load_all(), "respiratory", None, {"addon": False, "ranking": False, "hard_filter": False})
    assert json.dumps(run(name, eff)[0], sort_keys=True) == json.dumps(run(name)[0], sort_keys=True)
