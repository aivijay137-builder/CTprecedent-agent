"""The serving store: flat tables only, one DuckDB file (SERVING_DB, default <DATA_DIR>/serving.duckdb).
apply_studies() upserts fetched studies and writes field-level changes to study_changes, comparing with the stored values BEFORE replacing them."""
import json
import os
import tempfile
from pathlib import Path

import duckdb
from dotenv import load_dotenv

from . import flatsql

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DATA_DIR = Path(os.environ.get("DATA_DIR") or Path(__file__).resolve().parent.parent / "data")
SERVING_DB = Path(os.environ.get("SERVING_DB") or DATA_DIR / "serving.duckdb")

# columns from flatsql.FLAT_COLS with their types; row_updated_at is added by the store
_TYPES = {"enrollment": "INTEGER", "has_results": "BOOLEAN"}
SCHEMA = [
    "CREATE TABLE IF NOT EXISTS studies_current (" + ", ".join(
        f"{c} {_TYPES.get(c, 'VARCHAR')}" + (" PRIMARY KEY" if c == "nct_id" else "") for c in flatsql.FLAT_COLS) + ", row_updated_at TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS study_sites (nct_id VARCHAR, facility VARCHAR, city VARCHAR, state VARCHAR, country VARCHAR, zip VARCHAR, site_status VARCHAR)",
    "CREATE TABLE IF NOT EXISTS study_conditions (nct_id VARCHAR, kind VARCHAR, mesh_id VARCHAR, term VARCHAR)",
    "CREATE TABLE IF NOT EXISTS study_interventions (nct_id VARCHAR, type VARCHAR, name VARCHAR, description VARCHAR)",
    "CREATE TABLE IF NOT EXISTS study_outcomes (nct_id VARCHAR, kind VARCHAR, measure VARCHAR, time_frame VARCHAR, description VARCHAR)",
    "CREATE TABLE IF NOT EXISTS study_eligibility (nct_id VARCHAR, criteria VARCHAR, min_age VARCHAR, max_age VARCHAR, sex VARCHAR, healthy_volunteers VARCHAR)",
    """CREATE TABLE IF NOT EXISTS study_labels (nct_id VARCHAR PRIMARY KEY, primary_category VARCHAR, mentions VARCHAR,
       category_group VARCHAR, in_scope BOOLEAN, lung_cancer_mention BOOLEAN, stop_cause VARCHAR, stop_tier VARCHAR,
       label_version VARCHAR, derived_at TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS study_changes (nct_id VARCHAR, field VARCHAR, detail VARCHAR, old_value VARCHAR, new_value VARCHAR,
       change_type VARCHAR, last_update_post_date VARCHAR, run_folder VARCHAR, logged_at TIMESTAMP DEFAULT current_timestamp)""",
    """CREATE TABLE IF NOT EXISTS sync_runs (run_id VARCHAR PRIMARY KEY, mode VARCHAR, started_at TIMESTAMP, ended_at TIMESTAMP,
       fetched INTEGER, new_studies INTEGER, changes INTEGER, status VARCHAR, error VARCHAR)""",
    "CREATE TABLE IF NOT EXISTS sync_state (key VARCHAR PRIMARY KEY, value VARCHAR)",
]
INDEXES = [f"CREATE INDEX IF NOT EXISTS ix_{t}_nct ON {t}(nct_id)" for t in
           ["study_sites", "study_conditions", "study_interventions", "study_outcomes", "study_eligibility"]]
SCALARS = ["overall_status", "why_stopped", "enrollment", "primary_completion_date", "lead_sponsor", "has_results", "results_first_post_date"]
LISTS = {  # field -> (table, one comparable text per row, filter)
    "outcomes": ("study_outcomes", "kind || ': ' || coalesce(measure,'') || ' [' || coalesce(time_frame,'') || ']'", ""),
    "conditions": ("study_conditions", "term", "WHERE kind = 'text'"),
    "interventions": ("study_interventions", "coalesce(type,'') || ': ' || coalesce(name,'')", ""),
}


def connect(path=None, read_only=False):
    c = duckdb.connect(str(path or SERVING_DB), read_only=read_only)
    c.execute("SET memory_limit='3GB'; SET threads=2; SET preserve_insertion_order=true")
    return c


def init(con):
    for s in SCHEMA:
        con.execute(s)
    for s in INDEXES:
        con.execute(s)


def get_state(con, key, default=None):
    r = con.execute("SELECT value FROM sync_state WHERE key = ?", [key]).fetchone()
    return r[0] if r else default


def set_state(con, key, value):
    con.execute("INSERT OR REPLACE INTO sync_state VALUES (?, ?)", [key, None if value is None else str(value)])


def _agg(table, expr, where=""):
    return f"SELECT nct_id, string_agg({expr}, ' | ' ORDER BY {expr}) AS v FROM {table} {where} GROUP BY nct_id"


def apply_studies(con, studies, run_name, log_changes=True):
    """Upsert a list of studies (API v2 JSON objects). Caller owns the transaction.
    Returns (n_studies, n_new, n_change_rows)."""
    if not studies:
        return 0, 0, 0
    ids = [s["protocolSection"]["identificationModule"]["nctId"] for s in studies]
    assert len(ids) == len(set(ids)), "duplicate studies inside one page"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(studies, f)
        path = Path(f.name)
    try:
        con.execute("DROP TABLE IF EXISTS d")
        con.execute(f"""CREATE TEMP TABLE d AS SELECT protocolSection->>'$.identificationModule.nctId' AS nct_id,
            hasResults AS has_results, protocolSection, derivedSection
          FROM read_json('{path.as_posix()}', format='array', columns={{
            'protocolSection':'JSON','derivedSection':'JSON','hasResults':'BOOLEAN'}})""")
    finally:
        path.unlink(missing_ok=True)
    con.execute(f"CREATE OR REPLACE TEMP TABLE d_flat AS {flatsql.flat('d')}")
    for t, fn in flatsql.CHILDREN.items():
        con.execute(f"CREATE OR REPLACE TEMP TABLE d_{t} AS {fn('d')}")
    new_, chg = 0, 0
    if log_changes:
        con.execute("CREATE OR REPLACE TEMP TABLE d_old AS SELECT nct_id FROM d WHERE nct_id IN (SELECT nct_id FROM studies_current)")
        con.execute("CREATE OR REPLACE TEMP TABLE chg (nct_id VARCHAR, field VARCHAR, detail VARCHAR, old_value VARCHAR, new_value VARCHAR, change_type VARCHAR, lu VARCHAR)")
        con.execute("INSERT INTO chg SELECT nct_id, 'study', NULL, NULL, overall_status, 'new', last_update_post_date FROM d_flat WHERE nct_id NOT IN (SELECT nct_id FROM d_old)")
        for c in SCALARS:
            con.execute(f"""INSERT INTO chg SELECT n.nct_id, '{c}', NULL, cast(o.{c} AS VARCHAR), cast(n.{c} AS VARCHAR), 'changed', n.last_update_post_date
              FROM d_flat n JOIN studies_current o USING (nct_id) WHERE n.nct_id IN (SELECT nct_id FROM d_old) AND o.{c} IS DISTINCT FROM n.{c}""")
        e = "coalesce(criteria,'') || ' || ages ' || coalesce(min_age,'') || '-' || coalesce(max_age,'') || ' ' || coalesce(sex,'') || ' ' || coalesce(healthy_volunteers,'')"
        con.execute(f"""INSERT INTO chg SELECT k.nct_id, 'eligibility', NULL, o.v, n.v, 'changed', f.last_update_post_date
          FROM d_old k JOIN d_flat f USING (nct_id)
          LEFT JOIN (SELECT nct_id, {e} AS v FROM study_eligibility WHERE nct_id IN (SELECT nct_id FROM d_old)) o USING (nct_id)
          LEFT JOIN (SELECT nct_id, {e} AS v FROM d_study_eligibility) n USING (nct_id)
          WHERE o.v IS DISTINCT FROM n.v""")
        for field, (t, expr, where) in LISTS.items():
            con.execute(f"""INSERT INTO chg SELECT k.nct_id, '{field}', NULL, o.v, n.v, 'changed', f.last_update_post_date
              FROM d_old k JOIN d_flat f USING (nct_id)
              LEFT JOIN ({_agg(t, expr, where + (' AND' if where else 'WHERE') + ' nct_id IN (SELECT nct_id FROM d_old)')}) o USING (nct_id)
              LEFT JOIN ({_agg('d_' + t, expr, where)}) n USING (nct_id)
              WHERE o.v IS DISTINCT FROM n.v""")
        key = "coalesce(facility,'') || ' | ' || coalesce(city,'') || ' | ' || coalesce(zip,'')"
        con.execute(f"""INSERT INTO chg
          SELECT coalesce(o.nct_id, n.nct_id), 'site_status', coalesce(o.k, n.k), o.s, n.s, 'changed', f.last_update_post_date
          FROM (SELECT nct_id, {key} AS k, min(site_status) AS s FROM study_sites WHERE nct_id IN (SELECT nct_id FROM d_old) GROUP BY 1,2) o
          FULL JOIN (SELECT nct_id, {key} AS k, min(site_status) AS s FROM d_study_sites WHERE nct_id IN (SELECT nct_id FROM d_old) GROUP BY 1,2) n
            ON o.nct_id = n.nct_id AND o.k = n.k
          JOIN d_flat f ON f.nct_id = coalesce(o.nct_id, n.nct_id)
          WHERE o.s IS DISTINCT FROM n.s""")
        new_ = con.execute("SELECT count(*) FROM chg WHERE change_type='new'").fetchone()[0]
        chg = con.execute("SELECT count(*) FROM chg").fetchone()[0]
        con.execute("INSERT INTO study_changes (nct_id, field, detail, old_value, new_value, change_type, last_update_post_date, run_folder) "
                    "SELECT nct_id, field, detail, old_value, new_value, change_type, lu, ? FROM chg", [run_name])
    else:
        new_ = con.execute("SELECT count(*) FROM d_flat WHERE nct_id NOT IN (SELECT nct_id FROM studies_current)").fetchone()[0]
    for t in flatsql.CHILDREN:
        con.execute(f"DELETE FROM {t} WHERE nct_id IN (SELECT nct_id FROM d)")
        con.execute(f"INSERT INTO {t} SELECT * FROM d_{t}")
    cols = ", ".join(flatsql.FLAT_COLS)
    con.execute(f"INSERT OR REPLACE INTO studies_current ({cols}, row_updated_at) SELECT {cols}, current_timestamp FROM d_flat")
    return len(ids), new_, chg


def data_as_of(con):
    return con.execute("SELECT max(last_update_post_date) FROM studies_current").fetchone()[0]
