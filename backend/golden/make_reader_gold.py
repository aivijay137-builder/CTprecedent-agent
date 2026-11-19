"""Builds backend/golden/reader_gold.json: 40 real eligibility texts + the numeric entry limits a careful human reader finds in each.

Run once (needs the full registry):  python backend/golden/make_reader_gold.py
The JSON is committed, so scoring (backend/eval_reader.py) needs no database.

LABELLING POLICY (what counts as a "limit")
- A numeric limit on a PATIENT MEASURE: age, BMI, weight, lab value, vital sign, lung function, smoking pack-years, a clinical score, a count of events.
- Direction is about who may ENTER: key ends _min (lowest allowed in) or _max (highest allowed in). Age keys are min_age / max_age.
- Under Exclusion, the limit points the other way ("excluded if eGFR < 30" -> egfr_min 30). An excluded band is not a limit; skipped.
- Skipped on purpose: time windows ("within 3 months"), drug doses, counts of visits/sessions, birth-year ranges, a child's age, ambiguous wording.
- The same limit written twice (inclusion and exclusion) is labelled once. Sex-specific limits are labelled once per value.

STATUS: labelled by Claude as a first draft, NOT yet reviewed by a domain expert. Every label carries the quoted fragment, so a reviewer can check it in seconds.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

# nct_id -> [(key, value, unit, fragment copied from the text)]   (empty list = the text has no numeric limit)
LABELS = {
    "NCT04031261": [("min_age", 16, "years", "aged 16 years or over")],
    "NCT01337336": [("min_age", 40, "years", "at least 40 years of age")],
    "NCT04014868": [("min_age", 18, "years", "Age \\> 18years"), ("max_age", 80, "years", "\\< 80years")],
    "NCT01285882": [("min_age", 18, "years", "Patient aged under 18 years old")],
    "NCT00774176": [("smoking_pack_years_min", 20, "pack-years", ">/= 20 pack-yr"), ("fev1_pct_predicted_max", 70, "%", "FEV1 \\</= 70%"),
                    ("fev1_fvc_ratio_max", 70, "%", "FEV1/FVC \\</= 70%")],
    "NCT00163423": [("fev1_pct_predicted_min", 80, "%", "FEV1 80 - 105% of predicted"), ("fev1_pct_predicted_max", 105, "%", "FEV1 80 - 105% of predicted"),
                    ("smoking_pack_years_max", 10, "pack-years", "Current smoking with more than 10 pack-years")],
    "NCT00894426": [("min_age", 45, "years", "over 45 years old"), ("fev1_pct_predicted_max", 50, "%", "post-FEV1 \\< 50%"),
                    ("smoking_pack_years_min", 10, "pack-years", "> 10 packs per year".replace("> ", "\\> "))],
    "NCT00281242": [("smoking_pack_years_min", 20, "pack-years", "more than 20 pack-years")],
    "NCT06525051": [("min_age", 18, "years", "Patients under 18 years of age")],
    "NCT03157518": [("bmi_min", 30, "kg/m2", "BMI over 30")],
    "NCT00207337": [("rv_pct_predicted_min", 220, "%", "Residual volume (RV) ≥ 220% predicted"), ("tlc_pct_predicted_min", 133, "%", "Total lung capacity (TLC) ≥ 133%"),
                    ("fev1_pct_predicted_max", 40, "%", "\\< 40% of predicted"), ("fev1_l_max", 1, "L", "FEV1 \\< 1 liter"),
                    ("mmrc_min", 2, "", "scoring ≥ 2 on the modified Medical Research Council scale"), ("fev1_pct_predicted_min", 20, "%", "FEV1 \\> 20%"),
                    ("dlco_pct_predicted_min", 15, "%", "DLco) \\< 15% of predicted"), ("hospitalizations_max", 3, "events", "requiring \\> 3 hospitalizations")],
    "NCT05533957": [("pao2_max", 60, "mmHg", "PaO2 in room air less than 60 mmHg"), ("fev1_fvc_ratio_max", 70, "%", "FEV1/FVC \\<70%"),
                    ("fev1_pct_predicted_max", 50, "%", "FEV1 \\< 50% of predicted")],
    "NCT01729247": [("min_age", 7, "years", "Age: 7 to 60 years of age"), ("max_age", 60, "years", "Age: 7 to 60 years of age"),
                    ("smoking_pack_years_max", 10, "pack-years", "greater than a 10 pack-year history")],
    "NCT03359122": [("exacerbations_prior_year_min", 1, "events", "at least one COPD exacerbation during 1 year")],
    "NCT05876403": [("min_age", 35, "years", "Age 35-60years"), ("max_age", 60, "years", "Age 35-60years"),
                    ("fev1_fvc_ratio_max", 0.7, "", "FEV1/FVC \\<0.7"), ("fev1_pct_predicted_min", 30, "%", "30%\\<FEV1\\<80%"), ("fev1_pct_predicted_max", 80, "%", "30%\\<FEV1\\<80%")],
    "NCT07746310": [],
    "NCT00160407": [("hemoglobin_min", 12, "gm/dl", "Hemoglobin values of greater than or equal to 12 gm/dl for females"), ("hemoglobin_min", 13, "gm/dl", "13 gm/dl for males"),
                    ("wbc_min", 3000, "/mm3", "WBC count \\> 3,000/mm3".replace("3,000", "3,000")), ("neutrophil_min", 1500, "/mm3", "Neutrophil count \\> 1,500/mm3"),
                    ("platelets_min", 70000, "/mm3", "Platelets \\> 70,000/mm3"), ("albumin_min", 3.0, "g/dl", "Albumin \\>3.0 g/dl"),
                    ("creatinine_max", 1.4, "mg/dl", "Serum creatinine \\<1.4mg/dl"), ("alt_min", 40, "U/L", "Alanine aminotransferase (ALT) greater than or equal to 40 U/L"),
                    ("bmi_min", 27, "kg/m2", "BMI \\> or equal to 27 kg/m2"), ("alcohol_max", 20, "g/day", "greater than 20 grams per day")],
    "NCT05768581": [("bmi_min", 30, "kg/m2", "BMI major of 30 kg/m2"), ("max_age", 65, "years", "age over 65 years"), ("vas_max", 7, "", "visual analogue scale score \\>7")],
    "NCT03159312": [("min_age", 18, "years", "Age between 18 - 60 years"), ("max_age", 60, "years", "Age between 18 - 60 years"),
                    ("weight_max", 180, "kg", "weight \\<180 kilograms")],
    "NCT01695083": [("min_age", 18, "years", "Age ≥ 18 years"), ("bmi_min", 35, "kg/m2", "BMI ≥ 35 kg/m2"), ("weight_max", 230, "kg", "weight\\> 230 kg"),
                    ("anteroposterior_diameter_max", 40, "cm", "anteroposterior diameter\\>40 cm"), ("alcohol_max", 20, "g/day", "\\> 20 g per day for women"),
                    ("alcohol_max", 30, "g/day", "\\> 30 g per day for men")],
    "NCT02420145": [("waist_circumference_min", 88, "cm", "Waist circumference at least 88cm"), ("bmi_min", 25, "kg/m2", "Body mass index at least 25"),
                    ("diastolic_blood_pressure_max", 120, "mmHg", "diastolic blood pressure more than 120mmHg")],
    "NCT07440914": [("min_age", 40, "years", "aged 40-80 years"), ("max_age", 80, "years", "aged 40-80 years"), ("lvef_max", 40, "%", "(LVEF) ≤ 40%"),
                    ("systolic_blood_pressure_max", 180, "mmHg", "BP \\> 180/110 mmHg"), ("diastolic_blood_pressure_max", 110, "mmHg", "BP \\> 180/110 mmHg")],
    "NCT06683430": [("min_age", 60, "years", "aged ≥60 years"), ("systolic_blood_pressure_min", 130, "mmHg", "systolic blood pressure (SBP) ≥130 mmHg"),
                    ("diastolic_blood_pressure_min", 85, "mmHg", "diastolic blood pressure (DBP) ≥85 mmHg"), ("creatinine_max", 1.2, "mmol/L", "creatinine serum levels \\>1.2 mmol/L"),
                    ("fasting_blood_sugar_max", 126, "mg/dL", "fasting blood sugar \\>126 mg/dL"), ("bmi_max", 30, "kg/m2", "obesity (BMI ≥30 kg/m2 )")],
    "NCT02915250": [("min_age", 18, "years", "aged 18-70 years"), ("max_age", 70, "years", "aged 18-70 years"), ("hba1c_min", 7.5, "%", "HbA1c level between 7.5% and 9.5%"),
                    ("hba1c_max", 9.5, "%", "HbA1c level between 7.5% and 9.5%"), ("bmi_min", 20, "kg/m2", "Body mass index between 20.0 and 40.0 kg/m2"),
                    ("bmi_max", 40, "kg/m2", "Body mass index between 20.0 and 40.0 kg/m2"), ("systolic_blood_pressure_min", 90, "mmHg", "range of 90-160 mmHg for systolic"),
                    ("systolic_blood_pressure_max", 160, "mmHg", "range of 90-160 mmHg for systolic"), ("diastolic_blood_pressure_min", 50, "mmHg", "50-95 mmHg for diastolic"),
                    ("diastolic_blood_pressure_max", 95, "mmHg", "50-95 mmHg for diastolic"), ("heart_rate_min", 50, "bpm", "heart rate outside the range 50-90"),
                    ("heart_rate_max", 90, "bpm", "heart rate outside the range 50-90")],
    "NCT00413335": [("min_age", 10, "years", "Aged 10 to 18 yrs"), ("max_age", 18, "years", "Aged 10 to 18 yrs"), ("testes_volume_min", 6, "ml", "testes size\\>6ml"),
                    ("glucose_min", 140, "mg/dl", "plasma glucose\\>140mg/dl"), ("glucose_max", 200, "mg/dl", "\\<200mg/dl"), ("creatinine_max", 1.0, "mg", "creatinine\\>1.0mg"),
                    ("ast_max", 2.5, "x ULN", "AST and ALT\\>2.5 ULN"), ("alt_max", 2.5, "x ULN", "AST and ALT\\>2.5 ULN"), ("hematocrit_min", 30, "", "Hct\\<30")],
    "NCT02530788": [("bilirubin_max", 2, "mg/dl", "bilirubin \\>2mg/dl")],
    "NCT05629117": [("hba1c_min", 7, "%", "HbA1C level of \\> 7%"), ("min_age", 17, "years", "17 years or older")],
    "NCT05196659": [("min_age", 18, "years", "age ≥18 years")],
    "NCT00103363": [("smoking_pack_years_min", 20, "pack-years", "≥ 20 pack years"), ("fev1_pct_predicted_max", 75, "%", "FEV\\_1 \\< 75% predicted"),
                    ("fev1_fvc_ratio_max", 75, "%", "FEV\\_1/FVC ≤ 75%"), ("min_age", 25, "years", "25 and over")],
    "NCT05180487": [],
    "NCT00183560": [("hrsd17_min", 14, "", "Score less than 14 on the Hamilton Rating Scale")],
    "NCT07037680": [("min_age", 18, "years", "≥18 years old"), ("ecog_max", 2, "", "score ≤2 was required")],
    "NCT02149849": [("min_age", 18, "years", "18 years and older")],
    "NCT02448303": [("min_age", 18, "years", "≥ 18 years of age"), ("ecog_max", 1, "", "ECOG performance status of 0 or 1")],
    "NCT02097745": [("min_age", 18, "years", "18-80 years of age"), ("max_age", 80, "years", "18-80 years of age")],
    "NCT03653351": [("min_age", 60, "years", "aged 60 or above"), ("sbt_max", 9, "", "score of 0-9 on the Short Blessed Test"),
                    ("moca_min", 25, "", "(MoCA) score ≥25"), ("promis_depression_min", 16, "", "PROMIS depression scale score of greater or equal to 16"),
                    ("promis_anxiety_min", 14, "", "PROMIS anxiety score greater or equal to 14")],
    "NCT06186167": [("min_age", 40, "years", "40 years of age or older")],
    "NCT02910388": [],
    "NCT03764839": [("min_age", 18, "years", "Age 18-80 years"), ("max_age", 80, "years", "Age 18-80 years")],
    "NCT07379749": [("min_age", 18, "years", "between 18 and 90 years old"), ("max_age", 90, "years", "between 18 and 90 years old")],
}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\\", "", s)).strip().lower()


def main():
    import duckdb
    db = ROOT / "data" / "serving_full" / "serving.duckdb"
    c = duckdb.connect(db.as_posix(), read_only=True)
    items, bad = [], []
    for nct, labels in LABELS.items():
        row = c.execute("SELECT criteria FROM study_eligibility WHERE nct_id=?", [nct]).fetchone()
        cond = c.execute("SELECT term FROM study_conditions WHERE nct_id=? ORDER BY kind LIMIT 1", [nct]).fetchone()
        text = row[0]
        for key, val, unit, frag in labels:
            if norm(frag) not in norm(text):
                bad.append((nct, key, frag))
        items.append({"nct_id": nct, "condition": cond[0] if cond else "", "text": text,
                      "limits": [{"key": k, "value": v, "unit": u, "fragment": f} for k, v, u, f in labels]})
    if bad:
        sys.exit("fragments not found in text:\n" + "\n".join(map(str, bad)))
    out = {"labelled_by": "Claude (first draft), not yet reviewed by a domain expert", "policy": __doc__.split("LABELLING POLICY")[1].split("STATUS")[0].strip(), "items": items}
    (HERE / "reader_gold.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(items)} texts, {sum(len(i['limits']) for i in items)} limits")


if __name__ == "__main__":
    main()
