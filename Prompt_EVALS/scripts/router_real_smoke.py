"""Router smoke test on the REAL registry and the REAL draft packs (read-only, no AI, no engine involved).
For the golden designs plus a few made-up conditions, prints which pack the router chooses and why, and the merged add-on size.
Run from the Faro folder:  CTG_DB_PATH=<local registry copy> python EVALS/scripts/router_real_smoke.py"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent.parent
os.environ["LLM_ENABLED"] = "off"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend" / "golden"))
import make_golden  # noqa: E402
from backend import engine  # noqa: E402
from backend.packlib import loader, merge, router  # noqa: E402

packs = loader.load_all()
print(f"{len(packs)} packs loaded from {loader.packs_dir()}")
cx = engine.Ctx()
cases = {k: b for k, b in make_golden.designs().items()}
for name, terms in {"type 2 diabetes (made up)": ["Diabetes Mellitus, Type 2"], "non-small cell lung cancer (made up)": ["Carcinoma, Non-Small-Cell Lung"],
                    "multiple myeloma (made up)": ["Multiple Myeloma"], "asthma (made up)": ["Asthma"], "glaucoma (made up)": ["Glaucoma"],
                    "no MeSH term (free text only)": []}.items():
    cases[name] = SimpleNamespace(condition=name, mesh_terms=terms, intervention_type=["DRUG"], primary_endpoint="")
expect = {"bronchiectasis_nct": (None, "respiratory"), "heart_failure_form": (None, "cardiovascular"), "psoriasis_form": ("psoriasis", "dermatology"),
          "type 2 diabetes (made up)": (None, "metabolic_endocrine"), "non-small cell lung cancer (made up)": (None, "oncology_solid"),
          "multiple myeloma (made up)": (None, "oncology_heme"), "asthma (made up)": ("asthma", "respiratory"), "glaucoma (made up)": (None, "ophthalmology"),
          "no MeSH term (free text only)": (None, None)}
bad = 0
for name, b in cases.items():
    r = router.route(cx, b, packs)
    e = merge.merge(packs, r["area"], r["indication"])
    got = (r["indication"], r["area"])
    ok = got == expect[name]
    bad += not ok
    print(f"{'ok  ' if ok else 'DIFF'} {name:40s} -> indication={r['indication']}, area={r['area']} | add-on {len(merge.addon_for(e).split()) if e else 0} words | {r['reason'][:70]}")
    if not ok:
        print(f"       expected {expect[name]}; matches: {[(m['id'], m['priority']) for m in r['matches']]}")
print("router chose as expected for every case" if not bad else f"{bad} case(s) differ from what I expected")
sys.exit(1 if bad else 0)
