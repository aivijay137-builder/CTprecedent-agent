"""Tests for the simple-rules eligibility reader (backend/criteria.py). Run: python -m pytest backend/test_criteria.py -q"""
from backend.criteria import parse_criteria


def by_key(text):
    return {c["key"]: c for c in parse_criteria(text)}


def lines(*xs):
    return "\n".join(xs)


def test_inclusion_limits_are_read_with_their_source_sentence():
    text = lines("Inclusion Criteria:", "* Age 18 to 70 years", "* PASI score >= 12", "* At least 2 COPD exacerbations in the previous 12 months")
    got = by_key(text)
    assert (got["min_age"]["value"], got["max_age"]["value"], got["pasi_score_min"]["value"]) == ("18", "70", "12")
    assert got["exacerbations_prior_year_min"]["value"] == "2"
    assert all(c["source_sentence"] in text for c in got.values())


# ------------------------------------------------------------ the Step 3 bug: Inclusion vs Exclusion
def test_exclusion_greater_than_is_a_ceiling_not_a_floor():  # the exact NCT03460704 line
    got = by_key(lines("Exclusion Criteria:", "* long term (>= 30 days) prednisone at a dose of greater than 15 mg a day"))
    assert got["prednisone_dose_max"]["value"] == "15" and "prednisone_dose_min" not in got


def test_exclusion_less_than_is_a_floor():
    got = by_key(lines("Exclusion Criteria:", "* hemoglobin below 9 g/dL", "* FEV1 < 25% of predicted"))
    assert got["hemoglobin_min"]["value"] == "9" and got["fev1_pct_predicted_min"]["value"] == "25"


def test_same_wording_means_opposite_things_in_the_two_sections():
    text = lines("Inclusion Criteria:", "* eGFR at least 45 mL/min", "Exclusion Criteria:", "* eGFR at least 90 mL/min")
    got = parse_criteria(text)
    assert [(c["key"], c["value"]) for c in got] == [("egfr_min", "45"), ("egfr_max", "90")]


def test_exclusion_age_and_events_flip_too():
    got = by_key(lines("Exclusion Criteria:", "* aged > 75", "* at least 3 hospitalizations in the last year"))
    assert got["max_age"]["value"] == "75" and "min_age" not in got
    assert got["hospitalizations_prior_max"]["value"] == "3"


def test_an_excluded_band_is_skipped_not_guessed():
    # "excluded if HbA1c is between 6 and 7" removes a band; it is not a single floor or ceiling
    assert parse_criteria(lines("Exclusion Criteria:", "* HbA1c between 6.0% and 7.0%")) == []


def test_multiples_of_the_upper_limit_of_normal_keep_their_unit():
    got = by_key(lines("Exclusion Criteria:", "* serum creatinine > 2 x ULN"))
    assert got["serum_creatinine_max"]["value"] == "2" and got["serum_creatinine_max"]["unit"] == "x ULN"


def test_heading_variants_and_sections_that_switch_back():
    text = lines("Key Inclusion Criteria:", "* BMI 25 to 40 kg/m2", "Main Exclusion Criteria", "* BMI greater than 45", "Inclusion:", "* PASI score >= 12")
    got = [(c["key"], c["value"]) for c in parse_criteria(text)]
    # inclusion range 25 to 40 -> floor 25 and ceiling 40; exclusion "greater than 45" -> a second ceiling 45;
    # after the exclusion block, an "Inclusion:" heading switches back, so PASI >= 12 stays a floor
    assert got == [("bmi_min", "25"), ("bmi_max", "40"), ("bmi_max", "45"), ("pasi_score_min", "12")]


def test_text_without_headings_is_read_as_inclusion():
    assert by_key("* PASI score >= 12")["pasi_score_min"]["value"] == "12"


def test_ordinary_sentences_that_mention_the_word_are_not_headings():
    got = by_key(lines("Inclusion Criteria:", "* exclusion of other causes of anemia is required", "* hemoglobin at least 9 g/dL"))
    assert got["hemoglobin_min"]["value"] == "9"
