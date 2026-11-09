import { useCallback, useEffect, useRef, useState } from "react";
import { api, demoExamples, demoReset, setRole } from "./api";
import { Confirm } from "./components/Confirm";
import { NewDesign } from "./components/NewDesign";
import { Settings } from "./components/Settings";
import { loadAi } from "./llmKey";
import { Criteria } from "./components/Criteria";
import { PackageView } from "./components/PackageView";
import { Progress } from "./components/Progress";
import { Results } from "./components/Results";
import { LeftNav, NAV, SidePanel, TopBar, type Status } from "./components/Shell";
import type { DesignBrief, Element, Flag, Health, PackageSnapshot, Role, RunResult } from "./types";
import { store } from "./util";

type Mode = "criteria" | "confirm" | "progress" | "results" | "new" | "settings";
const DEFAULT_NCT = "NCT03460704"; // seeds the "COPD-201 draft v3" workspace
interface Saved { brief: DesignBrief; draftVersion: number; runId: string | null; runDraft: number | null }

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [role, setRoleState] = useState<Role>("lead");
  const [nav, setNav] = useState("population");
  const [mode, setMode] = useState<Mode>("criteria");
  const [brief, setBrief] = useState<DesignBrief | null>(null);
  const [draftVersion, setDraftVersion] = useState(1);
  const [runDraft, setRunDraft] = useState<number | null>(null);
  const [run, setRun] = useState<RunResult | null>(null);
  const [progressId, setProgressId] = useState<string | null>(null);
  const [excluded, setExcluded] = useState<string[]>([]);
  const [pkg, setPkg] = useState<PackageSnapshot | null>(null);
  const [error, setError] = useState("");
  const retry = useRef<() => void>(() => {});

  // ---- start up: health, then restore the saved draft/run or seed from the default NCT ----
  useEffect(() => {
    (async () => {
      try {
        setHealth(await api.health());
        const saved = store.get<Saved>("ctp-state");
        if (saved?.brief) {
          setBrief(saved.brief); setDraftVersion(saved.draftVersion); setRunDraft(saved.runDraft);
          if (saved.runId) { try { setRun(await api.getRun(saved.runId)); } catch { setRunDraft(null); } }
        } else {
          setBrief(await api.fromNct(DEFAULT_NCT));
        }
      } catch (e) { setError((e as Error).message); }
    })();
  }, []);

  useEffect(() => {
    if (brief) store.set("ctp-state", { brief, draftVersion, runId: run?.run_id ?? null, runDraft } satisfies Saved);
  }, [brief, draftVersion, run?.run_id, runDraft]);

  // the reviewer sees the frozen package of the current run
  useEffect(() => {
    if (run?.package_id) api.getPackage(run.package_id).then(setPkg).catch(() => setPkg(null));
    else setPkg(null);
  }, [run?.package_id, role]);

  const refreshRun = useCallback(async (id?: string) => { setRun(await api.getRun(id ?? run!.run_id)); }, [run]);

  const switchRole = (r: Role) => {
    setRoleState(r); setRole(r); setNav("population");
    if (r === "lead" && run) refreshRun().catch(() => {}); // pick up flags a reviewer sent back
  };

  // ---- status of the Precedent card ----
  const openN = run?.flags.filter((f) => f.status === "open").length ?? 0;
  const outOfDate = !!run && runDraft !== draftVersion;
  const status: Status = !run ? { label: "Not run", tone: "" }
    : outOfDate ? { label: "Out of date", tone: "amber" }
    : openN > 0 ? { label: `${openN} open`, tone: "amber" }
    : run.package_id ? { label: "Complete", tone: "green" } : { label: "Ready", tone: "blue" };

  // ---- actions ----
  const startRun = async (b: DesignBrief, focus: Element[]) => {
    setError("");
    try {
      const { run_id } = await api.createRun(b, focus, []);
      retry.current = () => startRun(b, focus);
      setBrief(b);  // keep the cutoffs read on the Confirm screen, so a Re-run checks the same ones
      setProgressId(run_id); setMode("progress");
    } catch (e) { setError((e as Error).message); }
  };
  const startRerun = async () => {
    if (!run || !brief) return;
    setError("");
    try {
      const { run_id } = await api.rerun(run.run_id, brief, excluded);
      retry.current = startRerun;
      setProgressId(run_id); setMode("progress");
    } catch (e) { setError((e as Error).message); }
  };
  const finished = async () => {
    if (!progressId) return;
    setRun(await api.getRun(progressId)); setRunDraft(draftVersion); setExcluded([]); setMode("results");
  };
  const decide = async (f: Flag, action: string, reason?: string) => {
    await api.decide(run!.run_id, f.id, action, reason);
    await refreshRun();
  };
  const makePackage = async () => { await api.makePackage(run!.run_id); await refreshRun(); };
  const review = async (flagId: string, action: "agree" | "send_back", comment?: string) => {
    setPkg(await api.review(pkg!.package_id, flagId, action, comment));
  };
  const loadNct = async (nct: string): Promise<string | null> => {
    try {
      setBrief(await api.fromNct(nct));
      setDraftVersion((v) => v + 1); setRun(null); setRunDraft(null); setExcluded([]); setPkg(null); setError("");
      return null;
    } catch (e) { return (e as Error).message; }
  };
  const submitNewDesign = (b: DesignBrief) => {
    setBrief(b); setDraftVersion((v) => v + 1); setRun(null); setRunDraft(null); setExcluded([]); setPkg(null); setError("");
    setMode("confirm");
  };
  const openPrecedent = () => { setNav("population"); if (role === "lead") setMode(run ? "results" : "confirm"); };
  const editBrief = (b: DesignBrief) => {
    const reworded = !!brief && (b.eligibility_text !== brief.eligibility_text || b.condition !== brief.condition);
    setBrief(reworded ? { ...b, structured_cutoffs: null } : b);  // new wording: the cutoffs must be read again (Confirm does that)
    setDraftVersion((v) => v + 1);
  };

  const phaseText = brief?.phase.length ? brief.phase.map((p) => p.replace("PHASE", "Phase ").replace("EARLY_", "Early ")).join("/") : "Phase not set";
  const studyMeta = `${health?.fixtures ? "COPD-201" : brief?.nct_id ?? (brief?.condition || "New design")} · ${phaseText} · Draft v${draftVersion}`;

  // ---- centre column ----
  let centre;
  if (!brief) {
    centre = error
      ? <div className="inner"><div className="banner red" role="alert">Could not reach the API: {error}. Is <code>npm run dev</code> running?</div></div>
      : <div className="inner"><p className="lead" aria-live="polite">Loading the draft design…</p></div>;
  } else if (nav !== "population") {
    const label = NAV.find((n) => n.id === nav)?.label ?? "";
    centre = (
      <div className="inner">
        <h1>{label}</h1>
        <div className="card" style={{ marginTop: 16 }}>
          <p>This is the existing editor, not part of this prototype.</p>
          <div className="actions"><button className="btn" onClick={() => setNav("population")}>Back</button></div>
        </div>
      </div>
    );
  } else if (role === "reviewer") {
    centre = <PackageView pkg={pkg} onReview={review} />;
  } else if (mode === "settings") {
    centre = <Settings onClose={() => setMode(run ? "results" : "criteria")} />;
  } else if (mode === "new") {
    centre = <NewDesign onSubmit={submitNewDesign} onCancel={() => setMode(run ? "results" : "criteria")} />;
  } else if (mode === "confirm") {
    centre = (
      <>
        {error && <div className="banner red" role="alert">{error}</div>}
        <Confirm brief={brief} onChange={editBrief} onRun={startRun} onCancel={() => { setError(""); setMode(run ? "results" : "criteria"); }}
          onLoadNct={loadNct} fixtures={!!health?.fixtures} onNewDesign={() => setMode("new")} />
      </>
    );
  } else if (mode === "progress" && progressId) {
    centre = <Progress runId={progressId} onDone={finished} onCancel={() => setMode(run ? "results" : "criteria")} onRetry={() => retry.current()} />;
  } else if (mode === "results" && run) {
    centre = (
      <>
        {error && <div className="banner red" role="alert">{error}</div>}
        <Results run={run} outOfDate={outOfDate} excluded={excluded} packaged={!!run.package_id}
          onToggleExcluded={(id) => setExcluded((x) => (x.includes(id) ? x.filter((i) => i !== id) : [...x, id]))}
          onDecide={decide} onRerun={startRerun} onPackage={makePackage} />
      </>
    );
  } else {
    centre = <Criteria brief={brief} onSave={(t) => editBrief({ ...brief, eligibility_text: t })} onOpenPrecedent={openPrecedent} precedentLabel={status.label} onNewDesign={() => setMode("new")} />;
  }

  const examples = demoExamples();
  const demoBar = examples.length > 0 && role === "lead" && (
    <div className="demobar" role="region" aria-label="Demo examples">
      <p><strong>Demo with saved results.</strong> Every number was computed from real ClinicalTrials.gov data (as of {run?.data_as_of ?? health?.data_as_of}) by the real engine. Nothing runs live here. Pick an example, then follow the flow: confirm, run, decide on each flag, package, switch to Reviewer.</p>
      <div className="chips">
        {examples.map((x) => (
          <button key={x.key} type="button" className="chip" title={x.blurb}
            onClick={async () => { const m = await loadNct("demo:" + x.key); if (m) setError(m); else setMode("criteria"); }}>{x.label}</button>
        ))}
        <button type="button" className="chip" onClick={() => demoReset()}>Reset demo</button>
      </div>
    </div>
  );

  return (
    <div className="app">
      <TopBar role={role} onRole={switchRole} meta={studyMeta} onSettings={examples.length === 0 && role === "lead" ? () => setMode("settings") : undefined} aiOn={!!loadAi()?.key} />
      <div className="body">
        <LeftNav onlyPopulation startHere={!run} active={nav} onPick={(id) => { setNav(id); if (id === "population" && mode !== "progress") setMode("criteria"); }} />
        <main className="main">{demoBar}{centre}</main>
        <SidePanel status={status} onOpen={openPrecedent} dataAsOf={run?.data_as_of ?? health?.data_as_of ?? new Date().toISOString().slice(0, 10)} fixtures={!!health?.fixtures} />
      </div>
    </div>
  );
}
