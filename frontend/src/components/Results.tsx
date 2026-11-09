import { useRef, useState } from "react";
import type { Element, Flag, RunResult } from "../types";
import { BUCKET_LABEL, ELEMENT_LABEL, TIER_LABEL, daysOld, fmtDate, isStale, nctUrl } from "../util";
import { Comparables } from "./Comparables";
import { Evidence, FlagCard } from "./FlagCard";

type Tab = "flags" | "comparables" | "limits";
const RISK: Record<string, { label: string; tone: string }> = {
  low: { label: "Low precedent risk", tone: "green" }, medium: { label: "Medium precedent risk", tone: "amber" },
  high: { label: "High precedent risk", tone: "red" }, insufficient: { label: "Not enough precedent", tone: "" },
};

export function Results({ run, outOfDate, excluded, onToggleExcluded, onDecide, onRerun, onPackage, packaged }: {
  run: RunResult; outOfDate: boolean; excluded: string[]; onToggleExcluded: (id: string) => void;
  onDecide: (flag: Flag, action: string, reason?: string) => Promise<void>; onRerun: () => void; onPackage: () => Promise<void>; packaged: boolean;
}) {
  const [tab, setTab] = useState<Tab>("flags");
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const bl = run.bottom_line;
  const risk = RISK[bl.risk];
  const openN = run.flags.filter((f) => f.status === "open").length;
  const tabs: { id: Tab; label: string }[] = [
    { id: "flags", label: "Flags" }, { id: "comparables", label: `Comparables (${bl.n_comparables})` },
    { id: "limits", label: "What the registry can't tell you" },
  ];
  const onKey = (e: React.KeyboardEvent, i: number) => {
    const j = e.key === "ArrowRight" ? (i + 1) % 3 : e.key === "ArrowLeft" ? (i + 2) % 3 : -1;
    if (j >= 0) { e.preventDefault(); setTab(tabs[j].id); refs.current[tabs[j].id]?.focus(); }
  };
  const stale = isStale(run.data_as_of);

  return (
    <div className="inner">
      {run.diff && (
        <div className="banner green" role="status">
          <b>Since your last run:</b> {run.diff.resolved.length} resolved, {run.diff.still_open.length} still open, {run.diff.new.length} new.
          <ul>
            {run.diff.resolved.map((d) => <li key={d.id}>Resolved: {d.title}</li>)}
            {run.diff.still_open.map((d) => <li key={d.id}>Still open: {d.title}</li>)}
            {run.diff.new.map((d) => <li key={d.id}>New: {d.title}</li>)}
          </ul>
        </div>
      )}
      {outOfDate && <div className="banner amber" role="status">Your draft changed after this check ran, so these results are out of date. Re-run the check.</div>}
      {stale && <div className="banner amber">Registry data is {daysOld(run.data_as_of)} days old (as of {fmtDate(run.data_as_of)}). Newer trials may be missing.</div>}
      {run.condition_support === "basic" && (
        <div className="banner grey">Basic support for this condition: comparables and outcomes come from the registry, but eligibility cutoffs are not parsed, so population checks use text only.</div>
      )}

      <div className="bottom">
        <span className={`badge ${risk.tone}`}>{risk.label}</span>
        <div className="txt">
          <div className="big">{bl.sentence}</div>
          <div className="sub">
            {run.flags.length === 0 ? "No flags raised. Nothing changes in your design until you edit it."
              : `${openN} of ${run.flags.length} flags open. Nothing changes in your design until you edit it.`}
            {excluded.length > 0 && ` ${excluded.length} comparable${excluded.length > 1 ? "s" : ""} marked for removal: re-run to update the counts.`}
          </div>
        </div>
        <button className="btn" onClick={onRerun}>Re-run check</button>
      </div>

      <div className="tabs" role="tablist" aria-label="Precedent results">
        {tabs.map((t, i) => (
          <button key={t.id} role="tab" id={`tab-${t.id}`} aria-selected={tab === t.id} aria-controls={`panel-${t.id}`} tabIndex={tab === t.id ? 0 : -1}
            ref={(el) => { refs.current[t.id] = el; }} onClick={() => setTab(t.id)} onKeyDown={(e) => onKey(e, i)}>{t.label}</button>
        ))}
      </div>

      {tab === "flags" && (
        <div role="tabpanel" id="panel-flags" aria-labelledby="tab-flags">
          <div className="legend" aria-label="Confidence key">
            <span><i className="dot stated" /> Stated in record</span><span><i className="dot outside" /> Supported by outside source</span><span><i className="dot unknown" /> Not stated</span>
          </div>
          {run.flags.length === 0 && <div className="banner grey" role="status">{run.no_flags_reason ?? "No flags."}</div>}
          {run.flags.map((f) => <FlagCard key={f.id} flag={f} onDecide={(a, r) => onDecide(f, a, r)} />)}
          {run.rule_notes && run.rule_notes.length > 0 && (
            <div className="banner grey" role="note">
              <b>Not checked:</b>
              <ul>{run.rule_notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
            </div>
          )}
          {openN === 0 && !outOfDate && (
            <div className="card" style={{ borderColor: "var(--green-solid)" }}>
              <h2>{run.flags.length ? "Every flag has a decision" : "Precedent check finished"}</h2>
              <p className="lead">{packaged ? "This check is in the review package. The reviewer will see it under their view." : "Add this check to the review package so a reviewer can see it at protocol review."}</p>
              <div className="actions">
                {packaged ? <span className="badge green">Added to review package</span> : <button className="btn green" onClick={onPackage}>Add to review package</button>}
              </div>
            </div>
          )}
          <Background run={run} />
          <Audit run={run} />
        </div>
      )}

      {tab === "comparables" && (
        <div role="tabpanel" id="panel-comparables" aria-labelledby="tab-comparables">
          <Comparables items={run.comparables} excluded={excluded} onToggle={onToggleExcluded} />
        </div>
      )}

      {tab === "limits" && (
        <div role="tabpanel" id="panel-limits" aria-labelledby="tab-limits">
          <div className="card">
            <ul style={{ listStyle: "disc", paddingLeft: 20 }}>{run.limits.map((l, i) => <li key={i} style={{ padding: "4px 0" }}>{l}</li>)}</ul>
          </div>
        </div>
      )}
    </div>
  );
}

function Audit({ run }: { run: RunResult }) {
  if (!run.audit?.length) return null;
  return (
    <details>
      <summary>SQL behind these numbers ({run.audit.length} queries)</summary>
      <div>
        <p className="lead">Every number above comes from one of these queries against the registry database (ctg.duckdb). Paste one into DuckDB to check it.</p>
        {run.audit.map((a, i) => (
          <details key={i}><summary>{a.name}</summary><pre style={{ whiteSpace: "pre-wrap", fontSize: 11, margin: 0, paddingBottom: 12 }}>{a.sql}</pre></details>
        ))}
      </div>
    </details>
  );
}

function Background({ run }: { run: RunResult }) {
  const o = run.outcomes;
  const cTot = Object.values(o.comparables).reduce((a, b) => a + b, 0) || 1;
  const bTot = Object.values(o.baseline).reduce((a, b) => a + b, 0) || 1;
  const [openIds, setOpenIds] = useState<string | null>(null);
  return (
    <>
      <h2 className="sectionhead">Background evidence</h2>
      <details>
        <summary>How the comparables ended, against all trials for this condition</summary>
        <div className="tablewrap"><table className="bars">
          <thead><tr><th>Outcome</th><th>Comparables</th><th>All trials ({bTot.toLocaleString()})</th></tr></thead>
          <tbody>{Object.keys(o.baseline).map((k) => (
            <tr key={k}><td>{BUCKET_LABEL[k] ?? k}</td>
              <td>{o.comparables[k] ?? 0} ({Math.round(((o.comparables[k] ?? 0) / cTot) * 100)}%)<div className="bar" style={{ width: `${((o.comparables[k] ?? 0) / cTot) * 100}%` }} /></td>
              <td>{o.baseline[k].toLocaleString()} ({Math.round((o.baseline[k] / bTot) * 100)}%)<div className="bar base" style={{ width: `${(o.baseline[k] / bTot) * 100}%` }} /></td></tr>
          ))}</tbody>
        </table></div>
      </details>
      <details>
        <summary>Why the terminated comparables stopped</summary>
        <div>
          {run.stop_causes.length === 0 && <p className="lead">No terminated comparables.</p>}
          <ul>{run.stop_causes.map((s) => (
            <li key={s.cause} style={{ padding: "8px 0", borderBottom: "1px solid var(--surface-2)" }}>
              <b>{s.cause}</b>: {s.count} <span className="tier">({TIER_LABEL[s.tier]})</span>
              <ul>{s.quotes.map((q) => (
                <li key={q.nct_id} className="src">{q.quote ? `“${q.quote}”` : "Reason not stated"} <a href={nctUrl(q.nct_id)} target="_blank" rel="noreferrer">{q.nct_id}</a></li>
              ))}</ul>
            </li>
          ))}</ul>
        </div>
      </details>
      <details>
        <summary>Element by element</summary>
        <div>
          {(Object.keys(run.elements) as Element[]).map((el) => (
            <div key={el} style={{ marginTop: 12 }}>
              <h2>{ELEMENT_LABEL[el]}</h2>
              <ul>{run.elements[el].findings.map((f, i) => (
                <li key={i} style={{ padding: "4px 0" }}>
                  {f.text} <span className="tier">(n = {f.n})</span>{" "}
                  {f.n > 0 && <button className="linkbtn" aria-expanded={openIds === `${el}${i}`} onClick={() => setOpenIds(openIds === `${el}${i}` ? null : `${el}${i}`)}>See the trials</button>}
                  {openIds === `${el}${i}` && <Evidence ids={f.evidence_ids} />}
                </li>
              ))}</ul>
            </div>
          ))}
        </div>
      </details>
    </>
  );
}
