import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
import pytest
from pydantic import ValidationError
from brief import DesignBrief


def test_minimal_and_defaults():
    b = DesignBrief(source="form", condition="COPD", phase=["PHASE2"])
    assert b.mesh_terms == [] and b.structured_cutoffs is None


def test_bad_source_rejected():
    with pytest.raises(ValidationError):
        DesignBrief(source="email")


def test_from_nct():
    from adapters import brief_from_nct, CTG
    if not pathlib.Path(CTG).exists():
        pytest.skip("ctg.duckdb missing")
    b = brief_from_nct("NCT03460704")
    assert b.source == "nct" and b.phase == ["PHASE3"] and b.enrollment_type == "ACTUAL"
    assert "United States" in b.countries and b.primary_endpoint
