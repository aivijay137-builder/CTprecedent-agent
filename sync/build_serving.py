"""Build serving.duckdb from the existing local ctg.duckdb (no download). Use this to try the flat store on this machine.
On Railway there is no ctg.duckdb: run `python -m sync.sync_ctg bootstrap` instead.
Usage: python -m sync.build_serving [path to ctg.duckdb] [--limit N]    (--limit builds a small test store from N studies)"""
import argparse
import sys
import time
from pathlib import Path

from . import flatsql, store

ap = argparse.ArgumentParser()
ap.add_argument("src", nargs="?", default=str(Path(__file__).resolve().parent.parent.parent / "ctg.duckdb"))
ap.add_argument("--limit", type=int)
_a = ap.parse_args()
SRC, LIMIT = Path(_a.src), _a.limit

store.DATA_DIR.mkdir(parents=True, exist_ok=True)
if store.SERVING_DB.exists():
    sys.exit(f"{store.SERVING_DB} already exists; delete it first (this tool never overwrites)")
t0 = time.time()
con = store.connect()
store.init(con)
con.execute(f"ATTACH '{SRC.as_posix()}' AS src (READ_ONLY)")
lim = f"ORDER BY nct_id LIMIT {LIMIT}" if LIMIT else ""
con.execute(f"CREATE TEMP TABLE pick AS SELECT nct_id FROM src.studies_current {lim}")
cols = ", ".join(flatsql.FLAT_COLS)
for t in ["study_sites", "study_conditions", "study_interventions", "study_outcomes", "study_eligibility"]:
    con.execute(f"DROP INDEX IF EXISTS ix_{t}_nct")
CHUNK = 3000  # the raw JSON is large: parse it in slices so memory stays bounded
con.execute("SET preserve_insertion_order=false")
con.execute("CREATE TEMP TABLE pick_n AS SELECT nct_id, (row_number() OVER (ORDER BY nct_id) - 1) // %d AS chunk FROM pick" % CHUNK)
for ch in range(con.execute("SELECT max(chunk) FROM pick_n").fetchone()[0] + 1):
    con.execute(f"""INSERT INTO studies_current ({cols}, row_updated_at)
      SELECT f.*, u.row_updated_at FROM ({flatsql.flat(f"(SELECT * FROM src.studies_current WHERE nct_id IN (SELECT nct_id FROM pick_n WHERE chunk = {ch}))")}) f
      JOIN src.studies_current u USING (nct_id)""".replace("f.*,", ", ".join("f." + c for c in flatsql.FLAT_COLS) + ","))
    con.execute("CHECKPOINT")  # flushes written rows to disk so memory does not build up
    print("  chunk", ch, f"{time.time()-t0:.0f}s", flush=True)
print("studies_current", con.execute("SELECT count(*) FROM studies_current").fetchone()[0], f"{time.time()-t0:.0f}s", flush=True)
for t in ["study_sites", "study_conditions", "study_interventions", "study_outcomes", "study_eligibility", "study_labels", "study_changes"]:
    con.execute(f"INSERT INTO {t} SELECT * FROM src.{t} WHERE nct_id IN (SELECT nct_id FROM pick)")
    print(t, con.execute(f"SELECT count(*) FROM {t}").fetchone()[0], f"{time.time()-t0:.0f}s", flush=True)
store.init(con)  # creates the indexes
asof = store.data_as_of(con)
store.set_state(con, "data_as_of", asof)
store.set_state(con, "watermark", asof)  # the next daily sync fetches everything updated since this date (minus 2 days)
con.execute("DETACH src")
con.execute("CHECKPOINT")
con.close()
print(f"done in {time.time()-t0:.0f}s; data_as_of {asof}; {store.SERVING_DB} = {store.SERVING_DB.stat().st_size / 1e9:.2f} GB")
