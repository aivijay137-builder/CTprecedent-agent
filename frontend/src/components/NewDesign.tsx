import { useEffect, useState } from "react";
import { api } from "../api";
import type { DesignBrief } from "../types";
import { CONTROL_OPTIONS, controlValue } from "../util";

const PHASES = ["EARLY_PHASE1", "PHASE1", "PHASE1/PHASE2", "PHASE2", "PHASE2/PHASE3", "PHASE3", "PHASE4"];
const TYPES = ["DRUG", "BIOLOGICAL", "DEVICE", "PROCEDURE", "BEHAVIORAL", "DIETARY_SUPPLEMENT", "OTHER"];

export const emptyBrief = (): DesignBrief => ({
  source: "form", nct_id: null, condition: "", mesh_terms: [], phase: [], intervention_type: [], eligibility_text: "",
  structured_cutoffs: null, primary_endpoint: "", primary_endpoint_timeframe: "", target_enrollment: null, enrollment_type: "ESTIMATED", countries: [], arm_types: [],
});

export function NewDesign({ onSubmit, onCancel }: { onSubmit: (b: DesignBrief) => void; onCancel: () => void }) {
  const [b, setB] = useState<DesignBrief>(emptyBrief());
  const [typed, setTyped] = useState("");
  const [picks, setPicks] = useState<{ term: string; n_trials: number }[]>([]);
  const [lookupErr, setLookupErr] = useState("");
  const [showErr, setShowErr] = useState(false);
  const set = (p: Partial<DesignBrief>) => setB((x) => ({ ...x, ...p }));

  // look up registry conditions as the user types (waits 300 ms after the last keystroke)
  useEffect(() => {
    setLookupErr("");
    if (typed.trim().length < 2) { setPicks([]); return; }
    let live = true;
    const t = setTimeout(() => {
      api.suggest(typed.trim()).then((r) => live && setPicks(r)).catch((e: Error) => live && setLookupErr(e.message));
    }, 300);
    return () => { live = false; clearTimeout(t); };
  }, [typed]);

  const missing = [!b.condition.trim() && "condition", !b.phase.length && "phase", !b.primary_endpoint.trim() && "primary endpoint", !b.target_enrollment && "target enrollment"].filter(Boolean) as string[];
  const bad = (k: string) => showErr && missing.includes(k);
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (missing.length) { setShowErr(true); return; }
    onSubmit({ ...b, condition: b.condition.trim() });
  };

  return (
    <form className="inner" onSubmit={submit} noValidate>
      <h1>New design</h1>
      <p className="lead">Describe your own study, for any condition. The check compares it with similar trials on ClinicalTrials.gov. Nothing is saved to the registry.</p>
      {showErr && missing.length > 0 && <div className="banner red" role="alert" style={{ marginTop: 16 }}>Fill in: {missing.join(", ")}.</div>}

      <h2 className="sectionhead">Condition</h2>
      <label className={`field card ${bad("condition") ? "bad" : ""}`}><span>Condition or disease (required)</span>
        <input value={typed} placeholder="e.g. type 2 diabetes, psoriasis, heart failure" aria-invalid={bad("condition")} autoComplete="off"
          onChange={(e) => { setTyped(e.target.value); set({ condition: e.target.value, mesh_terms: [] }); }} />
        {bad("condition") && <div className="err">Condition is required.</div>}
      </label>
      {picks.length > 0 && (
        <div role="group" aria-label="Matching registry conditions" style={{ marginTop: 8 }}>
          <p className="lead">Pick the registry condition that matches, so the right trials are searched:</p>
          <div className="chips">
            {picks.map((p) => (
              <button type="button" key={p.term} className="chip" aria-pressed={b.mesh_terms[0] === p.term}
                onClick={() => set({ mesh_terms: b.mesh_terms[0] === p.term ? [] : [p.term], condition: b.mesh_terms[0] === p.term ? typed : p.term })}>
                {p.term} ({p.n_trials.toLocaleString()} trials)
              </button>
            ))}
          </div>
        </div>
      )}
      {typed.trim().length >= 2 && picks.length === 0 && !lookupErr && <p className="lead" aria-live="polite">No registry condition matches yet. The check will search trials whose condition text contains what you typed.</p>}
      {b.mesh_terms.length === 0 && picks.length > 0 && <p className="lead">None picked: the check will search trials whose condition text contains “{typed.trim()}”.</p>}
      {lookupErr && <div className="err" role="alert">{lookupErr}</div>}

      <h2 className="sectionhead">Design</h2>
      <div className="grid2">
        <label className={`field card ${bad("phase") ? "bad" : ""}`}><span>Phase (required)</span>
          <select value={b.phase.join("/")} aria-invalid={bad("phase")} onChange={(e) => set({ phase: e.target.value ? e.target.value.split("/") : [] })}>
            <option value="">Choose a phase</option>
            {PHASES.map((p) => <option key={p} value={p}>{p.replace("PHASE", "Phase ").replaceAll("_", " ")}</option>)}
          </select>{bad("phase") && <div className="err">Phase is required.</div>}</label>
        <label className="field card"><span>Intervention type</span>
          <select value={b.intervention_type[0] ?? ""} onChange={(e) => set({ intervention_type: e.target.value ? [e.target.value] : [] })}>
            <option value="">Not sure</option>
            {TYPES.map((t) => <option key={t} value={t}>{t.charAt(0) + t.slice(1).toLowerCase().replaceAll("_", " ")}</option>)}
          </select></label>
        <label className="field card"><span>Control arm</span>
          <select value={controlValue(b.arm_types)} onChange={(e) => set({ arm_types: CONTROL_OPTIONS.find((o) => o.value === e.target.value)?.arms ?? [] })}>
            {CONTROL_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select></label>
        <label className={`field card ${bad("primary endpoint") ? "bad" : ""}`}><span>Primary endpoint (required)</span>
          <input value={b.primary_endpoint} placeholder="e.g. Change in HbA1c from baseline" aria-invalid={bad("primary endpoint")} onChange={(e) => set({ primary_endpoint: e.target.value })} />
          {bad("primary endpoint") && <div className="err">Primary endpoint is required.</div>}</label>
        <label className="field card"><span>Endpoint timeframe</span>
          <input value={b.primary_endpoint_timeframe} placeholder="e.g. 26 weeks" onChange={(e) => set({ primary_endpoint_timeframe: e.target.value })} /></label>
        <label className={`field card ${bad("target enrollment") ? "bad" : ""}`}><span>Target enrollment (required)</span>
          <input type="number" min={1} value={b.target_enrollment ?? ""} aria-invalid={bad("target enrollment")}
            onChange={(e) => set({ target_enrollment: e.target.value ? Number(e.target.value) : null })} />
          {bad("target enrollment") && <div className="err">Target enrollment is required.</div>}</label>
        <label className="field card"><span>Countries (comma separated, optional)</span>
          <input value={b.countries.join(", ")} placeholder="United States, Germany" onChange={(e) => set({ countries: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} /></label>
      </div>

      <h2 className="sectionhead">Eligibility criteria</h2>
      <label className="field"><span>Paste or type your inclusion and exclusion criteria (optional, but it improves the match)</span>
        <textarea value={b.eligibility_text} placeholder={"Inclusion Criteria:\n* Age 18 to 75 years\n* HbA1c between 7.0% and 10.5%\n\nExclusion Criteria:\n* Type 1 diabetes"}
          onChange={(e) => set({ eligibility_text: e.target.value })} style={{ minHeight: 200 }} /></label>
      <p className="lead">On the next screen you will see which numeric cutoffs were read from this text, each with the sentence it came from, and you can edit them.</p>

      <div className="actions" style={{ marginTop: 24 }}>
        <button className="btn primary" type="submit">Continue to confirm</button>
        <button className="btn" type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}
