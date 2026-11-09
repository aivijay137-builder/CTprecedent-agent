"""Run the real engine from the command line and print the result: python backend/try_engine.py NCT03460704"""
import json, sys, time
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
import backend  # noqa: F401  (puts src/ on the path)
import adapters
from backend import engine


def show(res):
    bl = res["bottom_line"]
    print(bl, "| as of", res["data_as_of"], "|", res["condition_support"])
    print("outcomes", res["outcomes"]["comparables"], "\nbaseline", res["outcomes"]["baseline"])
    print("stop causes", [(s["cause"], s["count"], s["tier"]) for s in res["stop_causes"]])
    for k, v in res["elements"].items():
        for f in v["findings"]:
            print(f"  [{k}] n={f['n']} ids={len(f['evidence_ids'])}  {f['text']}")
    for f in res["flags"]:
        print("FLAG", f["id"], "|", f["title"], "|", f["body"])
    print("no flags reason:", res["no_flags_reason"])
    for c in res["comparables"][:5]:
        print("  comp", c["nct_id"], c["similarity"], c["status"], "|", c["why_picked"])


if __name__ == "__main__":
    b = adapters.brief_from_nct(sys.argv[1] if len(sys.argv) > 1 else "NCT03460704")
    print(b.condition, b.phase, b.mesh_terms, b.countries[:5], b.target_enrollment)
    t = time.time()
    res = engine.run(b, ["population", "endpoints", "size", "sites", "design"], [])
    print(f"{time.time() - t:.1f} s, {len(res['audit'])} audited queries")
    show(res)
