import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
import extract as e

TEXT = "Inclusion:\n* Age >= 40 years\n* Post-BD FEV1/FVC < 0.70\n* Current smokers are excluded."


def _ext(**kw):
    base = {f: {"value": "not stated"} for f in e.FIELDS}
    base.update(kw)
    return e.Extraction.model_validate(base)


def test_good_quote_ok_and_missing_is_not_stated():
    r = e.check(_ext(min_age={"value": 40, "unit": "years", "source_sentence": "Age >= 40 years"}), TEXT)
    assert r["min_age"]["status"] == "ok" and r["max_age"]["status"] == "not_stated"


def test_quote_across_line_break_ok():
    r = e.check(_ext(fev1_fvc_ratio_max={"value": "0.70", "source_sentence": "Post-BD FEV1/FVC < 0.70"}), TEXT)
    assert r["fev1_fvc_ratio_max"]["status"] == "ok"


def test_invented_quote_invalid():
    r = e.check(_ext(max_age={"value": 80, "source_sentence": "Age <= 80 years"}), TEXT)
    assert r["max_age"]["status"] == "invalid"


def test_bad_category_invalid():
    r = e.check(_ext(current_smokers_allowed={"value": "maybe", "source_sentence": "Current smokers are excluded."}), TEXT)
    assert r["current_smokers_allowed"]["status"] == "invalid"


def test_markdown_escape_in_source_ignored():
    r = e.check(_ext(fev1_fvc_ratio_max={"value": 0.7, "source_sentence": "FEV1/FVC < 0.7"}), r"FEV1/FVC \< 0.7")
    assert r["fev1_fvc_ratio_max"]["status"] == "ok"
