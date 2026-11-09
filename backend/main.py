"""FastAPI app. FIXTURES=true (default) serves canned data from backend/fixtures; Phase B replaces the engine."""
import asyncio
import copy
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

from dotenv import load_dotenv
import hashlib

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

import adapters
from sync import sync_ctg
from . import appdb, byok, criteria, engine, llmsvc, readers
from .schemas import (DecisionIn, Diff, DiffItem, Flag, Health, NctIn, PackageId, PackageSnapshot, ParseIn,
                      ParseOut, ConditionSuggestion, RerunIn, RerunOut, ReviewIn, RunId, RunIn, RunResult, TrialSummary)

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
FIXTURES = os.environ.get("FIXTURES", "true").lower() == "true"
FX = Path(__file__).parent / "fixtures"
REQUIRED = {"condition": "Condition", "phase": "Phase", "primary_endpoint": "Primary endpoint",
            "target_enrollment": "Target enrollment"}
STEPS = ["Finding comparable trials", "Counting how they ended", "Reading why they stopped",
         "Checking each design element", "Writing the flags"]

app = FastAPI(title="Protocol Precedent Agent")
_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]  # the Vercel domain; blank = same-origin only
if _origins:
    app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Role", "X-LLM-Key", "X-LLM-Base-URL", "X-LLM-Model"])


def _visitor(request: Request) -> str:
    """Anonymous visitor id: a hash of the IP (Railway puts the real one in X-Forwarded-For). The IP itself is never stored."""
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def _limit_checks(request: Request):
    limit = int(os.environ.get("RATE_LIMIT_PER_DAY", "20"))
    if not appdb.use_check(_visitor(request), limit):
        raise HTTPException(429, f"Daily limit reached: {limit} precedent checks per day on this public demo. Try again tomorrow.")
appdb.init()
_attempts: dict[str, int] = {}  # demo: NCT05000003 fails on odd attempts, so Retry works
JOBS: dict[str, dict] = {}  # real engine: run_id -> {events, state, error}


def _start_job(brief, focus, excluded, parent=None, creds=None) -> str:
    """Run the real engine in a background thread; the SSE endpoint streams its progress."""
    run_id = appdb.new_id("run")
    job = {"events": [], "state": "running", "error": "", "t0": time.time()}
    JOBS[run_id] = job

    def progress(step, status):
        job["events"].append({"step": step, "label": STEPS[step - 1], "status": status,
                              "elapsed_ms": int((time.time() - job["t0"]) * 1000)})

    def work():
        try:
            with llmsvc.use(creds):  # the visitor's own key, if any (a new thread does not inherit it)
                res = engine.run(brief, focus, excluded, progress)
            res["run_id"] = run_id
            if parent:
                engine.apply_diff(parent, res)
            appdb.save_run(res, parent["run_id"] if parent else None)
            job["state"] = "done"
        except engine.RegistryBusy as e:
            job["error"], job["state"] = str(e), "error"
        except Exception as e:  # shown to the user with a Retry button; full trace goes to the terminal
            traceback.print_exc()
            job["error"], job["state"] = f"The check failed: {e}", "error"

    threading.Thread(target=work, daemon=True).start()
    return run_id


def _fx(name):
    return json.loads((FX / f"{name}.json").read_text(encoding="utf-8"))


def _need_fixtures():
    if not FIXTURES:
        raise HTTPException(501, "Real engine arrives in Phase B. Set FIXTURES=true.")


# ---------- briefs ----------
@app.post("/api/briefs/from-nct")
def from_nct(body: NctIn):
    nct = body.nct_id.strip().upper()
    if FIXTURES:
        b = _fx("briefs").get(nct)
        if not b:
            raise HTTPException(404, f"{nct} not found in the fixture set. Try the IDs in docs/api.md.")
        return b
    try:
        return adapters.brief_from_nct(nct)
    except KeyError:
        raise HTTPException(404, f"{nct} was not found in the registry database.")
    except Exception as e:
        if "lock" in str(e).lower() or "IO Error" in str(e):
            raise HTTPException(503, "The registry database is being updated right now. Try again in a minute.")
        raise


@app.get("/api/conditions/suggest", response_model=list[ConditionSuggestion])
def suggest(q: str = ""):
    if FIXTURES:
        demo = ["Pulmonary Disease, Chronic Obstructive", "Diabetes Mellitus, Type 2", "Bronchiectasis"]
        return [{"term": t, "n_trials": 100} for t in demo if q.lower() in t.lower()]
    try:
        return engine.suggest_conditions(q)
    except engine.RegistryBusy as e:
        raise HTTPException(503, str(e))


@app.post("/api/briefs/parse", response_model=ParseOut)
def parse(body: ParseIn, request: Request):
    creds = byok.from_request(request)
    if not FIXTURES:  # Phase C adds live LLM parsing; until then reuse cutoffs already parsed (free)
        hit = engine.cached_cutoffs(body.eligibility_text)
        if hit:
            return {"cutoffs": hit, "note": "Cutoffs were parsed earlier for this exact trial text (no LLM call)."}
        text = body.eligibility_text
        if not text.strip():
            return {"cutoffs": [], "note": "No eligibility text yet."}
        why = ""
        try:
            with llmsvc.use(creds):
                found = readers.parse_design(text, body.condition, llmsvc.Budget(5))
            bad = sum(1 for c in found if not c["valid"])
            note = (f"Read by AI. Each quoted sentence was checked against your text{f'; {bad} could not be matched and are marked' if bad else ''}."
                    if found else "The AI found no numeric limits in this text. The check still compares your wording with each trial's.")
            return {"cutoffs": found, "note": note}
        except llmsvc.LLMUnavailable as e:
            why = str(e)
        except Exception as e:  # never break the Confirm screen because of the AI
            why = f"The AI reader failed ({type(e).__name__})."
        found = criteria.parse_criteria(text)
        note = f"{why} Read by simple rules instead: only what a sentence literally says. Check each one." if found else f"{why} No numeric limits found by the simple rules either."
        return {"cutoffs": found, "note": note.strip()}
    text = body.eligibility_text
    if "COPD" not in text.upper():
        return {"cutoffs": [] if not text.strip() else [
            {"field": "Age", "value": "18-75", "unit": "years", "source_sentence": "Age 18 to 75 years", "valid": "18 to 75" in text}]}
    return {"cutoffs": [
        {"field": "Age", "value": "40-80", "unit": "years", "source_sentence": "Age 40 to 80 years", "valid": True},
        {"field": "FEV1 / FVC (post-bronchodilator)", "value": "<0.70", "unit": "ratio",
         "source_sentence": "Physician-diagnosed COPD, post-bronchodilator FEV1/FVC < 0.70", "valid": True},
        {"field": "FEV1 % predicted", "value": "30-60", "unit": "% predicted",
         "source_sentence": "Post-bronchodilator FEV1 between 30% and 60% of predicted", "valid": True},
        {"field": "Prior exacerbations", "value": ">=2", "unit": "per 12 months",
         "source_sentence": "At least 2 moderate or severe COPD exacerbations in the previous 12 months", "valid": True},
        {"field": "Smoking history", "value": ">=10", "unit": "pack-years",
         "source_sentence": "Current or former smoker with at least 10 pack-years", "valid": True},
        {"field": "Blood eosinophils", "value": ">=300", "unit": "cells/uL", "source_sentence": "", "valid": False}]}


# ---------- runs ----------
def _missing(brief) -> list[str]:
    return [label for k, label in REQUIRED.items() if not getattr(brief, k)]


def _pick(brief) -> str:
    m = {"NCT03460704": "copd", "NCT05000003": "copd", "NCT05000001": "basic", "NCT05000004": "basic",
         "NCT05000002": "few"}
    if brief.nct_id in m:
        return m[brief.nct_id]
    return "copd" if any(w in brief.condition.lower() for w in ("copd", "obstructive")) else "basic"


def parent_focus(parent: dict):
    return [e for e, v in parent["elements"].items() if v["findings"]] or ["population", "endpoints", "size", "sites", "design"]


def _recompute(res: dict) -> dict:
    """Recompute counts after comparables are removed (fixture stand-in for the SQL in Phase B)."""
    comps = res["comparables"]
    term = [c for c in comps if c["status"] == "TERMINATED"]
    enr = [c for c in term if "enroll" in (c["stop_reason"] or "").lower() or "recruit" in (c["stop_reason"] or "").lower()]
    bl = res["bottom_line"]
    bl.update(n_comparables=len(comps), n_terminated=len(term), n_terminated_enrollment=len(enr))
    bl["sentence"] = f"{len(comps)} comparable trials; {len(term)} terminated" + (f", {len(enr)} for slow enrollment." if enr else ".")

    def bucket(c):
        s = c["status"]
        if s == "COMPLETED":
            return "completed_results" if c["has_results"] else "completed_no_results"
        return {"TERMINATED": "terminated", "WITHDRAWN": "withdrawn", "UNKNOWN": "unknown"}.get(s, "running")
    res["outcomes"]["comparables"] = {b: sum(1 for c in comps if bucket(c) == b) for b in res["outcomes"]["baseline"]}
    if len(comps) < 5:
        bl["risk"], res["flags"] = "insufficient", []
        res["no_flags_reason"] = (f"Only {len(comps)} comparable trials are left. At least 5 are needed before a flag "
                                  "can be raised, so none are shown rather than guessing from too little evidence.")
    return res


def _make_run(brief, excluded: list[str], parent: dict | None = None) -> dict:
    res = _fx(_pick(brief))
    res["run_id"] = appdb.new_id("run")
    res["brief_echo"] = brief.model_dump()
    res["comparables"] = [c for c in res["comparables"] if c["nct_id"] not in set(excluded)]
    _recompute(res)
    if parent:  # carry decisions by flag rule id; accepted flags "no longer fire" -> resolved
        old = {f["id"]: f for f in parent["flags"]}
        d = Diff()
        for f in res["flags"]:
            o = old.get(f["id"])
            if not o:
                d.new.append(DiffItem(id=f["id"], title=f["title"]))
            elif o["status"] in ("accepted", "resolved"):
                f["status"], f["decision"] = "resolved", o["decision"]
                d.resolved.append(DiffItem(id=f["id"], title=f["title"]))
            else:
                f["status"], f["decision"] = o["status"], o["decision"]
                d.still_open.append(DiffItem(id=f["id"], title=f["title"]))
        res["diff"] = d.model_dump()
    appdb.save_run(res, parent["run_id"] if parent else None)
    return res


@app.post("/api/runs", response_model=RunId)
def create_run(body: RunIn, request: Request):
    miss = _missing(body.brief)
    if miss:
        raise HTTPException(422, "Missing required: " + ", ".join(miss))
    if not FIXTURES:
        _limit_checks(request)
        return {"run_id": _start_job(body.brief, body.focus, body.excluded_ids, creds=byok.from_request(request))}
    res = _make_run(body.brief, body.excluded_ids)
    if body.brief.nct_id == "NCT05000003":  # demo: every other attempt fails
        _attempts["n"] = _attempts.get("n", 0) + 1
        if _attempts["n"] % 2 == 1:
            res["_demo_fail"] = True
            appdb.save_run(res)
    return {"run_id": res["run_id"]}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get("/api/runs/{run_id}/events")
async def events(run_id: str):
    job = JOBS.get(run_id)
    if job:
        async def stream():
            sent = 0
            while True:
                while sent < len(job["events"]):
                    yield _sse("step", job["events"][sent])
                    sent += 1
                if job["state"] == "done":
                    yield _sse("done", {"run_id": run_id})
                    return
                if job["state"] == "error":
                    yield _sse("error", {"message": job["error"]})
                    return
                await asyncio.sleep(0.15)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
    res = appdb.load_run(run_id)
    if not res:
        raise HTTPException(404, "run not found")
    fail = res.get("_demo_fail", False)

    async def gen():
        t0 = time.time()
        ms = lambda: int((time.time() - t0) * 1000)
        for i, label in enumerate(STEPS, 1):
            yield _sse("step", {"step": i, "label": label, "status": "running", "elapsed_ms": ms()})
            await asyncio.sleep(0.7)
            if fail and i == 3:
                yield _sse("error", {"message": "Could not read the stop reasons (demo failure). Retry should work."})
                return
            yield _sse("step", {"step": i, "label": label, "status": "done", "elapsed_ms": ms()})
        yield _sse("done", {"run_id": run_id})
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


def _run_or_404(run_id) -> dict:
    res = appdb.load_run(run_id)
    if not res and JOBS.get(run_id, {}).get("state") == "running":
        raise HTTPException(409, "This run is still in progress.")
    if not res:
        raise HTTPException(404, "run not found")
    return res


@app.get("/api/runs/{run_id}", response_model=RunResult)
def get_run(run_id: str):
    return _run_or_404(run_id)


@app.post("/api/runs/{run_id}/flags/{flag_id}/decision", response_model=Flag)
def decide(run_id: str, flag_id: str, body: DecisionIn, x_role: str = Header("lead")):
    res = _run_or_404(run_id)
    f = next((f for f in res["flags"] if f["id"] == flag_id), None)
    if not f:
        raise HTTPException(404, "flag not found")
    if body.action == "keep" and not (body.reason or "").strip():
        raise HTTPException(422, "A reason is required to keep a flag as is.")
    status = {"accept": "accepted", "keep": "kept", "defer": "deferred", "undo": "open"}[body.action]
    f["status"] = status
    f["decision"] = None if body.action == "undo" else {"action": body.action, "reason": body.reason, "role": x_role, "at": appdb.now()}
    res["package_id"] = None  # any later decision makes an earlier package out of date
    appdb.save_run(res)
    appdb.log(x_role, "flag", body.action, run_id=run_id, flag_id=flag_id, reason=body.reason)
    return f


@app.post("/api/runs/{run_id}/rerun", response_model=RerunOut)
def rerun(run_id: str, body: RerunIn, request: Request):
    parent = _run_or_404(run_id)
    miss = _missing(body.brief)
    if miss:
        raise HTTPException(422, "Missing required: " + ", ".join(miss))
    if not FIXTURES:  # the diff arrives with the finished run (GET /runs/{id}.diff); see docs/api.md
        _limit_checks(request)
        return {"run_id": _start_job(body.brief, list(parent_focus(parent)), body.excluded_ids, parent, creds=byok.from_request(request)), "diff": {}}
    res = _make_run(body.brief, body.excluded_ids, parent)
    return {"run_id": res["run_id"], "diff": res["diff"]}


# ---------- packages ----------
@app.post("/api/runs/{run_id}/package", response_model=PackageId)
def package(run_id: str, x_role: str = Header("lead")):
    res = _run_or_404(run_id)
    if any(f["status"] == "open" for f in res["flags"]):
        raise HTTPException(409, "Decide every open flag before packaging.")
    order = {"deferred": 0}  # deferred first
    flags = sorted(copy.deepcopy(res["flags"]), key=lambda f: order.get(f["status"], 1))
    snap = dict(package_id=appdb.new_id("pkg"), run_id=run_id, created_at=appdb.now(), data_as_of=res["data_as_of"],
                brief_echo=res["brief_echo"], bottom_line=res["bottom_line"], flags=flags, reviews={})
    appdb.save_package(snap)
    res["package_id"] = snap["package_id"]
    appdb.save_run(res)
    appdb.log(x_role, "package", "create", run_id=run_id, package_id=snap["package_id"])
    return {"package_id": snap["package_id"]}


def _pkg_or_404(pid) -> dict:
    p = appdb.load_package(pid)
    if not p:
        raise HTTPException(404, "package not found")
    return p


@app.get("/api/packages/{package_id}", response_model=PackageSnapshot)
def get_package(package_id: str):
    return _pkg_or_404(package_id)


@app.post("/api/packages/{package_id}/review", response_model=PackageSnapshot)
def review(package_id: str, body: ReviewIn, x_role: str = Header("reviewer")):
    p = _pkg_or_404(package_id)
    if body.flag_id not in {f["id"] for f in p["flags"]}:
        raise HTTPException(404, "flag not in this package")
    p["reviews"][body.flag_id] = {"action": body.action, "comment": body.comment, "role": x_role, "at": appdb.now()}
    appdb.save_package(p)
    appdb.log(x_role, "review", body.action, run_id=p["run_id"], package_id=package_id, flag_id=body.flag_id, reason=body.comment)
    if body.action == "send_back":  # reopen the flag for the study lead (package_id stays until they decide again)
        res = appdb.load_run(p["run_id"])
        for f in res["flags"]:
            if f["id"] == body.flag_id:
                f["status"] = "open"
        appdb.save_run(res)
    return p


# ---------- evidence + health ----------
@app.get("/api/trials/{nct_id}", response_model=TrialSummary)
def trial(nct_id: str):
    if not FIXTURES:
        t = engine.trial_summary(nct_id.upper())
        if not t:
            raise HTTPException(404, f"{nct_id} not found")
        return t
    t = _fx("trials").get(nct_id.upper())
    if not t:
        raise HTTPException(404, f"{nct_id} not found")
    return t


@app.get("/api/health", response_model=Health)
def health():
    info = {"data_as_of": "2026-11-02", "row_counts": {"copd_trials": 1412}}
    if not FIXTURES:
        try:
            info = engine.health()
        except Exception:  # registry locked by a sync: the app still starts, the date shows as unknown
            info = {"data_as_of": time.strftime("%Y-%m-%d"), "row_counts": {}}
    sync = {}
    if not FIXTURES:
        try:  # last sync result + a warning if it failed; skipped while a sync holds the file
            c = engine.connect()
            sync = sync_ctg.health(c)
            c.close()
        except Exception:
            pass
    return {**info, **sync, "version": (os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "dev")[:7],
            "llm_configured": llmsvc.configured(), "llm_enabled": llmsvc.enabled(),
            "fixtures": FIXTURES}


@app.post("/api/llm/test")
def llm_test(request: Request):
    """The Settings panel's "Test key" button: one tiny call with the visitor's key. The key is used for this request only."""
    creds = byok.from_request(request)
    if not creds:
        raise HTTPException(400, "Enter your provider address, model and key first.")
    with llmsvc.use(creds):
        return llmsvc.test_key()


@app.post("/admin/sync", status_code=202)
def admin_sync(mode: str = "daily", x_sync_secret: str | None = Header(None)):
    """Start a data sync in the background (called daily by the cron service). Secret header required."""
    secret = os.environ.get("SYNC_SECRET")
    if not secret:
        raise HTTPException(503, "Sync is disabled: SYNC_SECRET is not set on the server.")
    if x_sync_secret != secret:
        raise HTTPException(403, "Wrong or missing secret.")
    if mode not in sync_ctg.MODES:
        raise HTTPException(400, f"mode must be one of {sorted(sync_ctg.MODES)}")
    if sync_ctg.is_running():
        raise HTTPException(409, "A sync is already running.")
    # a separate process: it holds the database file while it writes, and the app shows "try again" until it is done
    subprocess.Popen([sys.executable, "-m", "sync.sync_ctg", mode], cwd=ROOT)
    return {"started": mode}


# One-server mode (`npm start`): serve the built front end from the same address as the API.
# Must stay last so it never shadows /api routes.
DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="web")
