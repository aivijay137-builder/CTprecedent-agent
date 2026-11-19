"""relax.count agrees with the engine's own candidate count, and loosening never lowers it. Real registry (skipped without it).
Run: python -m pytest backend/test_relax.py -q"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "golden"))
import make_golden  # noqa: E402
from backend import engine, relax  # noqa: E402


@pytest.fixture(scope="module")
def cx():
    return engine.Ctx()


@pytest.mark.parametrize("name", ["bronchiectasis_nct", "heart_failure_form", "psoriasis_form"])
def test_count_matches_the_engine_and_loosening_only_adds(cx, name):
    b = make_golden.designs()[name]
    _, n_engine, _ = engine.find_comparables(cx, b, [])
    assert relax.count(cx, b) == n_engine                      # same query, same number
    parent = relax.parent_term(cx, b)
    base = relax.count(cx, b)
    assert relax.count(cx, b, ("phase",)) >= base
    if parent:
        assert relax.count(cx, b, ("condition_level",), parent) >= base
        assert relax.count(cx, b, ("phase", "condition_level"), parent) >= relax.count(cx, b, ("phase",))
