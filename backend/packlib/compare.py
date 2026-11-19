"""Compares two finished runs of the same design (for example prompt-only vs with a pack): which comparables moved, which flags changed.
It describes WHAT CHANGED. It does not say which run is better: that needs a quality eval against hand-graded comparables (not built)."""


def _label(run: dict) -> str:
    p = run.get("pack")
    return f"With pack: {p['pack']}" if p else "Prompt only"


def _ranks(run: dict) -> dict:
    return {c["nct_id"]: i + 1 for i, c in enumerate(run.get("comparables", []))}


def compare_runs(a: dict, b: dict) -> dict:
    ra, rb = _ranks(a), _ranks(b)
    info = {c["nct_id"]: c for r in (b, a) for c in r.get("comparables", [])}
    row = lambda n, **kw: {"nct_id": n, "title": info[n].get("title", ""), "why_picked": info[n].get("why_picked", ""), **kw}
    both = [n for n in ra if n in rb]
    moved = sorted((row(n, rank_a=ra[n], rank_b=rb[n]) for n in both if ra[n] != rb[n]), key=lambda r: -abs(r["rank_a"] - r["rank_b"]))
    fa, fb = {f["id"]: f for f in a.get("flags", [])}, {f["id"]: f for f in b.get("flags", [])}
    pa, pb = a.get("pack"), b.get("pack")
    return {
        "a": {"run_id": a.get("run_id"), "label": _label(a), "n_comparables": len(ra), "risk": a.get("bottom_line", {}).get("risk"), "sentence": a.get("bottom_line", {}).get("sentence"), "ai_usage": a.get("ai_usage")},
        "b": {"run_id": b.get("run_id"), "label": _label(b), "n_comparables": len(rb), "risk": b.get("bottom_line", {}).get("risk"), "sentence": b.get("bottom_line", {}).get("sentence"), "ai_usage": b.get("ai_usage")},
        "comparables": {"in_both": len(both), "same_rank": len(both) - len(moved),
                        "only_a": [row(n, rank_a=ra[n]) for n in ra if n not in rb],
                        "only_b": [row(n, rank_b=rb[n]) for n in rb if n not in ra],
                        "moved": moved[:15]},
        "flags": {"in_both": [i for i in fa if i in fb], "only_a": [i for i in fa if i not in fb], "only_b": [i for i in fb if i not in fa],
                  "n_changed": [{"id": i, "n_a": fa[i]["n"], "n_b": fb[i]["n"]} for i in fa if i in fb and fa[i]["n"] != fb[i]["n"]]},
        "pack_log": (pb or pa or {}),
        "note": "This shows what changed, not which result is better. A quality check against hand-graded comparables is still to be built.",
    }
