import { useEffect, useState } from "react";
import { api } from "../api";
import type { Cutoff, DesignBrief, Element } from "../types";
import { CONTROL_OPTIONS, ELEMENT_LABEL, controlValue } from "../util";

const PHASES = ["EARLY_PHASE1", "PHASE1", "PHASE1/PHASE2", "PHASE2", "PHASE2/PHASE3", "PHASE3", "PHASE4"];
const ELEMENTS = Object.keys(ELEMENT_LABEL) as Element[];

export function missingFields(b: DesignBrief): string[] {
  const m: string[] = [];
  if (!b.condition.trim()) m.push("condition");
  if (!b.phase.length) m.push("phase");
  if (!b.primary_endpoint.trim()) m.push("primary_endpoint");
  if (!b.target_enrollment) m.push("target_enrollment");
  return m;
}
const NAMES: Record<string, string> = { condition: "Condition", phase: "Phase", primary_endpoint: "Primary endpoint", target_enrollment: "Target enrollment" };

export function Confirm({ brief, onChange, onRun, onCancel, onLoadNct, fixtures, onNewDesign }: {
  brief: DesignBrief; onChange: (b: DesignBrief) => void; onRun: (b: DesignBrief, focus: Element[]) => void;
  onCancel: () => void; onLoadNct: (nct: string) => Promise<string | null>; fixtures: boolean; onNewDesign: () => void;
}) {
  const [cutoffs, setCutoffs] = useState<Cutoff[] | null>(null);
  const [parseErr, setParseErr] = useState("");
  const [parseNote, setParseNote] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [focus, setFocus] = useState<Element[]>(ELEMENTS);
  const [showErr, setShowErr] = useState(false);
  const [nct, setNct] = useState("");
  const [nctErr, setNctErr] = useState("");
  const miss = missingFields(brief);
  const set = (p: Partial<DesignBrief>) => onChange({ ...brief, ...p });

  useEffect(() => {
    let live = true;
    setCutoffs(null); setParseErr(""); setParseNote("");
    api.parse(brief.eligibility_text, brief.condition)
      .then((r) => { if (live) { setCutoffs(r.cutoffs); setParseNote(r.note ?? ""); } })
      .catch((e: Error) => live && setParseErr(e.message));
    return () => { live = false; };
  }, [brief.eligibility_text, brief.condition]);

  const bad = (k: string) => showErr && miss.includes(k);
  const edit = (i: number, p: Partial<Cutoff>) => setCutoffs((cs) => cs && cs.map((c, j) => (j === i ? { ...c, ...p } : c)));
  const toggle = (e: Element) => setFocus((f) => (f.includes(e) ? f.filter((x) => x !== e) : [...f, e]));

  const run = () => {
    if (miss.length || !focus.length) { setShowErr(true); return; }
    onRun({ ...brief, structured_cutoffs: cutoffs ? { cutoffs } : null }, focus);
  };

  return (
    <div className="inner">
      <h1>Confirm the design to check</h1>
      <p className="lead">This is what the precedent check will compare against. Fix anything that is wrong before you run it. Nothing changes in your design.</p>

      {showErr && (miss.length > 0 || !focus.length) && (
        <div className="banner red" role="alert" style={{ marginTop: 16 }}>
          {miss.length > 0 && <>Fill in the required fields: {miss.map((m) => NAMES[m]).join(", ")}. </>}
          {!focus.length && <>Pick at least one design element to check.</>}
        </div>
      )}

      <h2 className="sectionhead">Your design</h2>
      <div className="grid2">
        <label className={`field card ${bad("condition") ? "bad" : ""}`}><span>Condition (required)</span>
          <input value={brief.condition} aria-invalid={bad("condition")} onChange={(e) => set({ condition: e.target.value })} />
          {bad("condition") && <div className="err">Condition is required.</div>}</label>
        <label className={`field card ${bad("phase") ? "bad" : ""}`}><span>Phase (required)</span>
          <select value={brief.phase.join("/")} aria-invalid={bad("phase")} onChange={(e) => set({ phase: e.target.value ? e.target.value.split("/") : [] })}>
            <option value="">Choose a phase</option>
            {PHASES.map((p) => <option key={p} value={p}>{p.replace("PHASE", "Phase ").replaceAll("_", " ")}</option>)}
          </select>
          {bad("phase") && <div className="err">Phase is required.</div>}</label>
        <label className={`field card ${bad("primary_endpoint") ? "bad" : ""}`}><span>Primary endpoint (required)</span>
          <input value={brief.primary_endpoint} aria-invalid={bad("primary_endpoint")} onChange={(e) => set({ primary_endpoint: e.target.value })} />
          {bad("primary_endpoint") && <div className="err">Primary endpoint is required.</div>}</label>
        <label className="field card"><span>Endpoint timeframe</span>
          <input value={brief.primary_endpoint_timeframe} onChange={(e) => set({ primary_endpoint_timeframe: e.target.value })} /></label>
        <label className={`field card ${bad("target_enrollment") ? "bad" : ""}`}><span>Target enrollment (required)</span>
          <input type="number" min={1} value={brief.target_enrollment ?? ""} aria-invalid={bad("target_enrollment")}
            onChange={(e) => set({ target_enrollment: e.target.value ? Number(e.target.value) : null })} />
          {bad("target_enrollment") && <div className="err">Target enrollment is required.</div>}</label>
        <label className="field card"><span>Control arm</span>
          <select value={controlValue(brief.arm_types)} onChange={(e) => set({ arm_types: CONTROL_OPTIONS.find((o) => o.value === e.target.value)?.arms ?? [] })}>
            {CONTROL_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select></label>
        <label className="field card"><span>Countries (comma separated)</span>
          <input value={brief.countries.join(", ")} onChange={(e) => set({ countries: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} /></label>
      </div>

      <h2 className="sectionhead">Eligibility cutoffs we read from your criteria</h2>
      <p className="lead" style={{ marginBottom: 8 }} aria-live="polite">
        {cutoffs === null && !parseErr && "Reading your eligibility text…"}
        {cutoffs !== null && `${cutoffs.length} cutoffs found. Each one points to the sentence it came from. Check them, edit if wrong.`}
        {cutoffs !== null && parseNote && <span> {parseNote}</span>}
        {parseErr && <span className="warn">Could not read the criteria: {parseErr}</span>}
      </p>
      {cutoffs && cutoffs.length > 0 && (
        <div className="tablewrap"><table>
          <thead><tr><th>Field</th><th>Value</th><th>Unit</th><th>Source sentence</th><th><span className="sr">Edit</span></th></tr></thead>
          <tbody>
            {cutoffs.map((c, i) => (
              <tr key={i} className="cutrow">
                {editing === i ? (
                  <>
                    <td><input aria-label="Field" value={c.field} onChange={(e) => edit(i, { field: e.target.value })} style={{ width: 150, minHeight: 36 }} /></td>
                    <td><input aria-label="Value" value={c.value ?? ""} onChange={(e) => edit(i, { value: e.target.value })} style={{ width: 80, minHeight: 36 }} /></td>
                    <td><input aria-label="Unit" value={c.unit} onChange={(e) => edit(i, { unit: e.target.value })} style={{ width: 100, minHeight: 36 }} /></td>
                  </>
                ) : (
                  <><td><b>{c.field}</b></td><td>{c.value ?? "—"}</td><td>{c.unit}</td></>
                )}
                <td className="src">{c.source_sentence ? `“${c.source_sentence}”` : <span className="warn">No matching sentence found. Check this one.</span>}</td>
                <td>{editing === i
                  ? <button className="linkbtn" onClick={() => { edit(i, { valid: true }); setEditing(null); }}>Done</button>
                  : <button className="linkbtn" aria-label={`Edit ${c.field}`} onClick={() => setEditing(i)}>Edit</button>}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
      {cutoffs && cutoffs.length === 0 && <div className="banner grey">No cutoffs found. The check will use text similarity only.</div>}

      <h2 className="sectionhead">Which design elements to check</h2>
      <div className="checks" role="group" aria-label="Design elements to check">
        {ELEMENTS.map((e) => (
          <label key={e}><input type="checkbox" checked={focus.includes(e)} onChange={() => toggle(e)} />{ELEMENT_LABEL[e]}</label>
        ))}
      </div>

      <div className="actions" style={{ marginTop: 24 }}>
        <button className="btn primary" onClick={run} disabled={cutoffs === null && !parseErr} title={cutoffs === null && !parseErr ? "Wait until your eligibility text has been read" : undefined}>{cutoffs === null && !parseErr ? "Reading your criteria…" : "Run precedent check"}</button>
        <button className="btn" onClick={onCancel}>Cancel</button>
        <button className="linkbtn" onClick={onNewDesign}>Start a different design</button>
      </div>

      <details style={{ marginTop: 32 }}>
        <summary>Load a different design from an NCT ID</summary>
        <div>
          <form className="actions" onSubmit={async (e) => { e.preventDefault(); setNctErr((await onLoadNct(nct.trim())) ?? ""); }}>
            <label className="field" style={{ flex: 1, minWidth: 200 }}><span>NCT ID</span>
              <input value={nct} placeholder="NCT03460704" onChange={(e) => setNct(e.target.value)} /></label>
            <button className="btn" type="submit" style={{ alignSelf: "flex-end" }}>Load</button>
          </form>
          {nctErr && <div className="err" role="alert">{nctErr}</div>}
          {fixtures && <p className="lead">Demo IDs: NCT03460704 (COPD), NCT05000001 (basic support, older data), NCT05000002 (fewer than 5 comparables), NCT05000003 (first run fails), NCT05000004 (missing fields).</p>}
        </div>
      </details>
    </div>
  );
}
