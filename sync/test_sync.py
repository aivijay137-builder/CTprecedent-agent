"""Sync tests: no network, no real data. Run: python -m pytest sync -q"""
import datetime as dt

import pytest

from sync import labels, store, sync_ctg


def study(nct, status="RECRUITING", enroll=100, why=None, crit="Inclusion: age 18+", country="Germany", alloc="RANDOMIZED", date="2026-11-01"):
    return {"hasResults": False, "protocolSection": {
        "identificationModule": {"nctId": nct, "briefTitle": f"COPD trial {nct}", "organization": {"fullName": "Org", "class": "OTHER"}},
        "statusModule": {"overallStatus": status, "whyStopped": why, "statusVerifiedDate": "2026-10",
                         "lastUpdatePostDateStruct": {"date": date}},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Acme", "class": "INDUSTRY"}},
        "designModule": {"studyType": "INTERVENTIONAL", "phases": ["PHASE3"], "enrollmentInfo": {"count": enroll, "type": "ESTIMATED"},
                         "designInfo": {"allocation": alloc, "maskingInfo": {"masking": "DOUBLE"}}},
        "conditionsModule": {"conditions": ["COPD"], "keywords": ["emphysema"]},
        "armsInterventionsModule": {"armGroups": [{"type": "EXPERIMENTAL"}, {"type": "PLACEBO_COMPARATOR"}],
                                    "interventions": [{"type": "DRUG", "name": "X"}]},
        "outcomesModule": {"primaryOutcomes": [{"measure": "FEV1", "timeFrame": "12 weeks"}]},
        "eligibilityModule": {"eligibilityCriteria": crit, "minimumAge": "18 Years", "sex": "ALL"},
        "contactsLocationsModule": {"locations": [{"facility": "Site A", "city": "Berlin", "country": country, "status": "RECRUITING"}]}},
        "derivedSection": {"conditionBrowseModule": {"meshes": [{"id": "D029424", "term": "Pulmonary Disease, Chronic Obstructive"}], "ancestors": []}}}


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(store, "SERVING_DB", tmp_path / "serving.duckdb")
    monkeypatch.setattr(sync_ctg, "LOCK", tmp_path / ".sync.lock")
    monkeypatch.setattr(sync_ctg, "PAUSE_S", 0)
    c = store.connect()
    store.init(c)
    yield c
    c.close()


def test_flat_columns_and_children(db):
    store.apply_studies(db, [study("NCT00000001")], "r1")
    r = db.execute("SELECT allocation, masking, status_verified_date, arm_types, keywords, phases, enrollment FROM studies_current").fetchone()
    assert r == ("RANDOMIZED", "DOUBLE", "2026-10", "EXPERIMENTAL,PLACEBO_COMPARATOR", "emphysema", "PHASE3", 100)
    assert db.execute("SELECT count(*) FROM study_sites").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM study_conditions WHERE kind='mesh'").fetchone()[0] == 1
    cols = [c[1] for c in db.execute("PRAGMA table_info('studies_current')").fetchall()]
    assert not {"protocolSection", "derivedSection", "resultsSection"} & set(cols)  # flat only


def test_changes_are_logged_with_old_and_new(db):
    store.apply_studies(db, [study("NCT00000001")], "r1")
    assert db.execute("SELECT change_type FROM study_changes").fetchall() == [("new",)]
    store.apply_studies(db, [study("NCT00000001", status="TERMINATED", enroll=80, why="slow enrollment", country="France", date="2026-11-03")], "r2")
    ch = {(f, o, n) for f, o, n in db.execute("SELECT field, old_value, new_value FROM study_changes WHERE run_folder='r2'").fetchall()}
    assert ("overall_status", "RECRUITING", "TERMINATED") in ch and ("enrollment", "100", "80") in ch
    assert db.execute("SELECT count(*) FROM studies_current").fetchone()[0] == 1  # upsert, not duplicate
    assert db.execute("SELECT country FROM study_sites").fetchall() == [("France",)]


def test_labels_stop_cause(db):
    store.apply_studies(db, [study("NCT00000001", status="TERMINATED", why="Slow enrollment of patients")], "r1")
    assert labels.label_stale(db) == 1
    assert db.execute("SELECT stop_cause FROM study_labels").fetchone()[0] != "empty_or_blank"
    assert labels.label_stale(db) == 0  # nothing stale the second time


def _fake_pages(monkeypatch, studies, total=None):
    monkeypatch.setattr(sync_ctg, "pages", lambda params, token=None: iter([(studies, None, len(studies) if total is None else total)]))


def test_daily_sync_ok_and_watermark(db, monkeypatch):
    store.set_state(db, "watermark", "2026-11-01")
    db.close()
    _fake_pages(monkeypatch, [study("NCT00000002")])
    out = sync_ctg.run("daily")
    assert out["status"] == "ok" and out["fetched"] == 1 and out["new_studies"] == 1
    c = store.connect(read_only=True)
    assert store.get_state(c, "watermark") == dt.date.today().isoformat()
    assert store.get_state(c, "data_as_of") == "2026-11-01"
    c.close()


def test_failed_sync_rolls_back_and_warns(db, monkeypatch):
    store.set_state(db, "watermark", "2026-11-01")
    db.close()
    _fake_pages(monkeypatch, [study("NCT00000003")], total=5)  # API says 5, sent 1
    out = sync_ctg.run("daily")
    assert out["status"] == "failed" and "API total" in out["error"]
    c = store.connect(read_only=True)
    assert c.execute("SELECT count(*) FROM studies_current").fetchone()[0] == 0  # nothing half-applied
    assert "failed" in sync_ctg.health(c)["sync_warning"]
    c.close()


def test_zero_records_on_weekday_fails(db, monkeypatch):
    store.set_state(db, "watermark", "2026-11-01")
    db.close()
    _fake_pages(monkeypatch, [])
    monkeypatch.setattr(sync_ctg.dt, "date", type("D", (dt.date,), {"today": classmethod(lambda c: dt.date(2026, 11, 9))}))  # a Monday
    assert "zero records" in sync_ctg.run("daily")["error"]


def test_zero_records_after_a_weekend_is_fine(db, monkeypatch):
    store.set_state(db, "watermark", "2026-11-09")  # window starts Saturday 7 Nov: only the weekend, nothing is posted then
    db.close()
    _fake_pages(monkeypatch, [])
    monkeypatch.setattr(sync_ctg.dt, "date", type("D", (dt.date,), {"today": classmethod(lambda c: dt.date(2026, 11, 9))}))
    assert sync_ctg.run("daily")["status"] == "ok"


def test_refuses_second_sync_and_needs_bootstrap(db, monkeypatch):
    db.close()
    sync_ctg.LOCK.write_text(str(__import__("os").getpid()))
    assert sync_ctg.run("daily")["status"] == "refused"
    sync_ctg.LOCK.unlink()
    assert "bootstrap" in sync_ctg.run("daily")["error"]


def test_bootstrap_resumes_from_saved_token(db, monkeypatch):
    seen = []
    def fake(params, token=None):
        seen.append(token)
        yield [study("NCT00000004")], None, 1
    store.set_state(db, "bootstrap_token", "abc")
    store.set_state(db, "bootstrap_started", "2026-11-09")
    db.close()
    monkeypatch.setattr(sync_ctg, "pages", fake)
    assert sync_ctg.run("bootstrap")["status"] == "ok"
    assert seen == ["abc"]


def test_ids_check_fetches_missed_and_removes_dropped(db, monkeypatch):
    store.apply_studies(db, [study("NCT00000005")], "r0")
    db.close()
    def fake(params, token=None):
        if params.get("fields") == "NCTId":
            yield [study("NCT00000006")], None, 1  # registry has only 6
        else:
            yield [study("NCT00000006")], None, 1
    monkeypatch.setattr(sync_ctg, "pages", fake)
    assert sync_ctg.run("ids")["status"] == "ok"
    c = store.connect(read_only=True)
    assert [r[0] for r in c.execute("SELECT nct_id FROM studies_current").fetchall()] == ["NCT00000006"]
    assert c.execute("SELECT change_type FROM study_changes WHERE nct_id='NCT00000005' AND change_type='removed'").fetchone()
    c.close()
