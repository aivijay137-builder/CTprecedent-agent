"""Router on the REAL registry and the REAL draft packs (skips itself where either is missing, e.g. in GitHub CI).
Added after EVALS run R09 found leaked parent terms mis-routing designs. Run: python -m pytest backend/test_packs_real.py -q"""
from types import SimpleNamespace

import pytest

from backend import engine
from backend.packlib import loader, router


@pytest.fixture(scope="module")
def packs():
    if not loader.available():
        pytest.skip("no pack files on this machine")
    return loader.load_all()


CASES = [
    (["Bronchiectasis"], None, "respiratory"),                       # was routed to COPD before the fix
    (["Heart Failure"], None, "cardiovascular"),                     # was routed to metabolic before the fix
    (["Psoriasis"], "psoriasis", "dermatology"),
    (["Asthma"], "asthma", "respiratory"),
    (["Carcinoma, Non-Small-Cell Lung"], None, "oncology_solid"),    # was routed to blood cancers before the fix
    (["Multiple Myeloma"], None, "oncology_heme"),
    (["Glaucoma"], None, "ophthalmology"),                           # was routed to metabolic before the fix
    (["Diabetes Mellitus, Type 2"], None, "metabolic_endocrine"),
    ([], None, None),
]


@pytest.mark.parametrize("terms,ind,area", CASES)
def test_real_designs_route_to_the_expected_pack(packs, terms, ind, area):
    b = SimpleNamespace(condition=" ".join(terms), mesh_terms=terms)
    r = router.route(engine.Ctx(), b, packs)
    assert (r["indication"], r["area"]) == (ind, area), r["reason"]
