"""Hand-check helpers for the cutoff extraction.

  python src/review.py make [--alt]      write data/cutoffs_review.csv (50 random trials)
  python src/review.py score <file.csv>  read your filled copy and print accuracy per field
"""
import sys
from pathlib import Path
import duckdb
import pandas as pd
from extract import FIELDS, DB, PROMPT_VERSION  # same field list as the extractor

ERROR_TYPES = "wrong_direction | wrong_subgroup | guessed | unit_or_scale | bad_quote | other"
OUT = Path(__file__).resolve().parent.parent / "data" / "cutoffs_review.csv"


def make(n=50):
    con = duckdb.connect(str(DB), read_only=True)
    df = con.execute(f"SELECT * FROM copd_cutoffs WHERE status='ok' AND prompt_version='{PROMPT_VERSION}'").df()
    pick = df.sample(min(n, len(df)), random_state=7)  # fixed seed -> same 50 each time
    rows = []
    for _, r in pick.iterrows():
        for f in FIELDS:
            if r[f + "_status"] in ("ok", "invalid"):  # only fields the model claims to have found
                v = r[f + "_value"] + (f" {r[f + '_unit']}" if pd.notna(r[f + "_unit"]) else "")
                rows.append(dict(nct_id=r["nct_id"], model=r["model"], field=f, extracted_value=v,
                                 field_status=r[f + "_status"], source_sentence=r[f + "_source"],
                                 link=f"https://clinicaltrials.gov/study/{r['nct_id']}",
                                 correct="", error_type="", note=""))
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"{len(pick)} trials, {len(rows)} extracted values -> {OUT}")
    print("Fill 'correct' with y or n. For every n, also fill 'error_type' with one of:")
    print("  " + ERROR_TYPES)


def score(path):
    df = pd.read_csv(path, dtype=str).fillna("")
    df["correct"] = df["correct"].str.strip().str.lower()
    print(f"rows: {len(df)}, filled in: {(df.correct.isin(['y', 'n'])).sum()}, "
          f"unrecognised/blank: {(~df.correct.isin(['y', 'n'])).sum()}")
    d = df[df.correct.isin(["y", "n"])]
    g = d.groupby("field")["correct"].agg(checked="count", correct=lambda s: (s == "y").sum())
    g["accuracy_%"] = (100 * g["correct"] / g["checked"]).round(1)
    print(g.to_string())
    wrong = d[d.correct == "n"]
    if len(wrong):
        # every wrong answer should carry an error type, so we learn WHY it failed
        kind = wrong["error_type"].str.strip().replace("", "(missing)") if "error_type" in wrong else "(missing)"
        print("\nERRORS BY TYPE:")
        print(kind.value_counts().to_string())
        print("\nERRORS BY FIELD x TYPE:")
        print(pd.crosstab(wrong["field"], kind).to_string())
    print(f"\nOVERALL: {(d.correct == 'y').sum()}/{len(d)} = {100 * (d.correct == 'y').mean():.1f}%")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "make":
        make()
    elif len(sys.argv) > 2 and sys.argv[1] == "score":
        score(sys.argv[2])
    else:
        print(__doc__)
