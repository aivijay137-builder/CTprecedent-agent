"""Builds copd_trials / copd_excluded in precedent.duckdb from ctg.duckdb (read-only)."""
import duckdb
from pathlib import Path
from adapters import CTG

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "copd_sample.csv"

COPD_TEXT = r"(\bCOPD\b|chronic obstructive pulmonary|emphysema|chronic bronchitis)"
CANCER = r"(lung cancer|lung neoplasm|\bNSCLC\b|\bSCLC\b|carcinoma|mesothelioma)"

SQL = f"""
CREATE OR REPLACE TABLE _all AS
WITH s AS (
  SELECT nct_id, has_results, protocolSection p,
         (derivedSection->'$.conditionBrowseModule')::VARCHAR mesh,
         coalesce(array_to_string(CAST(json_extract(protocolSection,'$.conditionsModule.conditions') AS VARCHAR[]),' | '),'') conds
  FROM ctg.studies
  WHERE protocolSection->>'$.designModule.studyType'='INTERVENTIONAL'
), f AS (
  SELECT *, coalesce(mesh,'') LIKE '%"Pulmonary Disease, Chronic Obstructive"%' m_mesh,
         regexp_matches(conds, '{COPD_TEXT}', 'i') m_text,
         regexp_matches(conds||' '||coalesce(mesh,''), '{CANCER}', 'i') is_cancer
  FROM s
)
SELECT nct_id,
  p->>'$.identificationModule.briefTitle' title,
  CAST(json_extract(p,'$.designModule.phases') AS VARCHAR[]) phases,
  p->>'$.statusModule.overallStatus' overall_status,
  p->>'$.statusModule.whyStopped' why_stopped,
  CAST(p->>'$.designModule.enrollmentInfo.count' AS INTEGER) enrollment_count,
  p->>'$.designModule.enrollmentInfo.type' enrollment_type,
  p->>'$.statusModule.startDateStruct.date' start_date,
  p->>'$.statusModule.primaryCompletionDateStruct.date' primary_completion_date,
  p->>'$.statusModule.primaryCompletionDateStruct.type' primary_completion_type,
  p->>'$.statusModule.statusVerifiedDate' status_verified_date,
  p->>'$.sponsorCollaboratorsModule.leadSponsor.name' lead_sponsor,
  p->>'$.sponsorCollaboratorsModule.leadSponsor.class' sponsor_class,
  list_distinct(CAST(json_extract(p,'$.armsInterventionsModule.interventions[*].type') AS VARCHAR[])) intervention_types,
  p->>'$.eligibilityModule.eligibilityCriteria' eligibility_text,
  p->>'$.eligibilityModule.minimumAge' min_age,
  p->>'$.eligibilityModule.maximumAge' max_age,
  p->>'$.outcomesModule.primaryOutcomes[0].measure' primary_outcome,
  p->>'$.outcomesModule.primaryOutcomes[0].timeFrame' primary_timeframe,
  list_distinct(CAST(json_extract(p,'$.contactsLocationsModule.locations[*].country') AS VARCHAR[])) countries,
  has_results,
  CASE WHEN m_mesh AND m_text THEN 'both' WHEN m_mesh THEN 'mesh' ELSE 'text' END match_method,
  CASE WHEN is_cancer THEN 'lung cancer / carcinoma mention' END excluded_reason
FROM f WHERE m_mesh OR m_text;
CREATE OR REPLACE TABLE copd_trials AS SELECT * FROM _all WHERE excluded_reason IS NULL;
CREATE OR REPLACE TABLE copd_excluded AS SELECT * FROM _all WHERE excluded_reason IS NOT NULL;
DROP TABLE _all;
"""


def main():
    con = duckdb.connect(str(ROOT / "precedent.duckdb"))
    con.execute("SET memory_limit='2GB'; SET threads=2")
    con.execute(f"ATTACH '{CTG}' AS ctg (READ_ONLY)")
    con.execute(SQL)
    q = lambda s: con.execute(s).fetchall()
    print("total rows:", q("select count(*) from copd_trials")[0][0])
    print("excluded:", q("select count(*) from copd_excluded")[0][0])
    for col in ["overall_status", "match_method"]:
        print(f"by {col}:", q(f"select {col}, count(*) from copd_trials group by 1 order by 2 desc"))
    print("by phase:", q("select coalesce(array_to_string(phases,'/'),'(none)'), count(*) from copd_trials group by 1 order by 2 desc"))
    con.execute("SELECT * FROM copd_trials USING SAMPLE 20 ROWS (reservoir, 42)").df().to_csv(OUT, index=False)
    print("sample ->", OUT)


if __name__ == "__main__":
    main()
