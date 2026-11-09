"""Adapter B: NCT record (from ctg.duckdb) -> DesignBrief."""
import json, os
import duckdb
from dotenv import load_dotenv
from brief import DesignBrief

load_dotenv()
# CTG_DB_PATH in .env wins; otherwise the old default path.
_DD = os.environ.get("DATA_DIR")
CTG = os.environ.get("CTG_DB_PATH") or os.environ.get("SERVING_DB") or f"{_DD or 'data'}/serving.duckdb"


def connect():
    c = duckdb.connect(CTG, read_only=True)
    c.execute("SET memory_limit='2GB'; SET threads=2")
    return c


def brief_from_nct(nct_id: str, con=None) -> DesignBrief:
    """Reads the flat tables of the serving store (no raw JSON)."""
    con = con or connect()
    s = con.execute("SELECT phases, enrollment, enrollment_type, arm_types FROM studies_current WHERE nct_id=?", [nct_id]).fetchone()
    if s is None:
        raise KeyError(f"{nct_id} not found")
    q = lambda sql: con.execute(sql, [nct_id]).fetchall()
    cond = [r[0] for r in q("SELECT term FROM study_conditions WHERE nct_id=? AND kind='text' ORDER BY rowid")]
    mesh = [r[0] for r in q("SELECT term FROM study_conditions WHERE nct_id=? AND kind='mesh' ORDER BY rowid")]
    itypes = sorted({r[0] for r in q("SELECT type FROM study_interventions WHERE nct_id=? AND type IS NOT NULL")})
    elig = (q("SELECT criteria FROM study_eligibility WHERE nct_id=?") or [("",)])[0][0] or ""
    po = (q("SELECT measure, time_frame FROM study_outcomes WHERE nct_id=? AND kind='primary' ORDER BY rowid LIMIT 1") or [("", "")])[0]
    countries = sorted({r[0] for r in q("SELECT country FROM study_sites WHERE nct_id=? AND country IS NOT NULL AND country<>''")})
    return DesignBrief(
        source="nct", nct_id=nct_id,
        condition="; ".join(cond), mesh_terms=mesh,
        phase=[p for p in (s[0] or "").split(",") if p],
        intervention_type=itypes, eligibility_text=elig,
        primary_endpoint=po[0] or "", primary_endpoint_timeframe=po[1] or "",
        target_enrollment=s[1], enrollment_type=s[2],
        countries=countries, arm_types=[a for a in (s[3] or "").split(",") if a],
    )


if __name__ == "__main__":
    for n in ["NCT06317285", "NCT05292950", "NCT03460704"]:
        b = brief_from_nct(n).model_dump()
        b["eligibility_text"] = b["eligibility_text"][:150] + "..."
        print(json.dumps(b, indent=2), "\n")
