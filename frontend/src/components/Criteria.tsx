import { useState } from "react";
import type { DesignBrief } from "../types";

function split(text: string) {
  const [inc, exc = ""] = text.split(/exclusion criteria:?/i);
  const lines = (s: string) => s.split("\n").map((l) => l.replace(/^[\s*\-•]+/, "").trim()).filter((l) => l && !/inclusion criteria:?/i.test(l));
  return { inc: lines(inc), exc: lines(exc) };
}

export function Criteria({ brief, onSave, onOpenPrecedent, precedentLabel, onNewDesign }: {
  brief: DesignBrief; onSave: (text: string) => void; onOpenPrecedent: () => void; precedentLabel: string; onNewDesign: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(brief.eligibility_text);
  const { inc, exc } = split(brief.eligibility_text);
  return (
    <div className="inner">
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <h1>Population</h1>
        {!editing && <span style={{ marginLeft: "auto", display: "flex", gap: 8 }}><button className="btn" onClick={onNewDesign}>New design</button><button className="btn" onClick={() => { setText(brief.eligibility_text); setEditing(true); }}>Edit criteria</button></span>}
      </div>
      <p className="lead">{brief.condition} · {brief.phase.join(", ") || "Phase not set"} · target {brief.target_enrollment ?? "not set"} participants</p>
      <div className="banner grey" style={{ marginTop: 16 }}>
        Precedent check: <b>{precedentLabel}</b>. <button className="linkbtn" onClick={onOpenPrecedent}>Open precedent check</button>
      </div>
      {editing ? (
        <div className="card">
          <label className="field">
            <span>Eligibility criteria (text)</span>
            <textarea value={text} onChange={(e) => setText(e.target.value)} />
          </label>
          <div className="actions">
            <button className="btn primary" onClick={() => { onSave(text); setEditing(false); }}>Save draft</button>
            <button className="btn" onClick={() => setEditing(false)}>Cancel</button>
          </div>
        </div>
      ) : (
        <>
          <div className="card"><h2>Inclusion criteria</h2><ul style={{ marginTop: 8 }}>{inc.map((l, i) => <li key={i} style={{ padding: "4px 0" }}>{l}</li>)}</ul></div>
          <div className="card"><h2>Exclusion criteria</h2><ul style={{ marginTop: 8 }}>{exc.map((l, i) => <li key={i} style={{ padding: "4px 0" }}>{l}</li>)}</ul></div>
        </>
      )}
    </div>
  );
}
