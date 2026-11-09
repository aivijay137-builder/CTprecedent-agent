import { useEffect, useState } from "react";
import { api } from "../api";
import type { Flag, TrialSummary } from "../types";
import { CONFIDENCE_LABEL, ELEMENT_LABEL, KEEP_REASONS, nctUrl } from "../util";

const STATUS: Record<Flag["status"], { label: string; tone: string }> = {
  open: { label: "Open", tone: "amber" }, accepted: { label: "Accepted", tone: "green" }, kept: { label: "Kept as is", tone: "blue" },
  deferred: { label: "Discuss at review", tone: "blue" }, resolved: { label: "Resolved", tone: "green" },
};

export function Evidence({ ids }: { ids: string[] }) {
  const [rows, setRows] = useState<(TrialSummary | { nct_id: string; missing: true })[] | null>(null);
  useEffect(() => {
    let live = true;
    Promise.all(ids.map((id) => api.trial(id).catch(() => ({ nct_id: id, missing: true as const }))))
      .then((r) => live && setRows(r));
    return () => { live = false; };
  }, [ids]);
  if (!rows) return <p className="lead" aria-live="polite">Loading trials…</p>;
  const capped = ids.length >= 50;
  return (
    <><ul className="evidence" aria-label="Trials behind this flag">
      {rows.map((t) => (
        <li key={t.nct_id}>
          <a href={nctUrl(t.nct_id)} target="_blank" rel="noreferrer">{t.nct_id}</a>
          {"missing" in t ? <span className="sub"> (details not available)</span> : (
            <>
              {" "}{t.title}
              <div className="sub">
                {t.status.replaceAll("_", " ").toLowerCase()}{t.enrollment != null ? ` · ${t.enrollment} enrolled` : ""}
                {t.status === "TERMINATED" && ` · stop reason: ${t.stop_reason ?? "reason not stated"}`}
              </div>
            </>
          )}
        </li>
      ))}
    </ul>{capped && <p className="lead">Showing the first 50 trials.</p>}</>
  );
}

export function FlagCard({ flag, onDecide }: { flag: Flag; onDecide: (action: string, reason?: string) => Promise<void> }) {
  const [keeping, setKeeping] = useState(false);
  const [reason, setReason] = useState("");
  const [showTrials, setShowTrials] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const st = STATUS[flag.status];
  const open = flag.status === "open";

  const go = async (action: string, r?: string) => {
    setBusy(true); setErr("");
    try { await onDecide(action, r); setKeeping(false); setReason(""); }
    catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  };

  return (
    <article className={`flag ${open ? "" : flag.status === "resolved" ? "resolved" : "done"}`} aria-labelledby={`f-${flag.id}`}>
      <div className="head">
        <span className="el">{ELEMENT_LABEL[flag.element]}</span>
        <span className={`dot ${flag.confidence}`} aria-hidden="true" />
        <span>{CONFIDENCE_LABEL[flag.confidence]}</span>
        {flag.n ? <span title="Trials this claim is computed over">· n = {flag.n}</span> : null}
        {flag.source_url ? <a href={flag.source_url} target="_blank" rel="noreferrer">· source</a> : null}
        <span className={`badge ${st.tone} status`}>{st.label}</span>
      </div>
      <h3 id={`f-${flag.id}`}>{flag.title}</h3>
      <p className="fbody">{flag.body}</p>
      {flag.written_by === "ai" && <p className="lead" style={{ margin: "2px 0 0", fontSize: 12 }}>Worded by AI from the evidence above. Every number was checked against it.</p>}
      <p className="ask">To consider: {flag.question.charAt(0).toLowerCase() + flag.question.slice(1)}</p>

      {open && !keeping && (
        <div className="actions">
          <button className="btn primary" disabled={busy} onClick={() => go("accept")}>{flag.action_label}</button>
          <button className="btn" disabled={busy} onClick={() => setKeeping(true)}>Keep as is</button>
          <button className="btn" disabled={busy} onClick={() => go("defer")}>Discuss at review</button>
          <button className="linkbtn" aria-expanded={showTrials} onClick={() => setShowTrials(!showTrials)}>See the trials</button>
        </div>
      )}

      {open && keeping && (
        <div role="group" aria-label="Reason for keeping as is">
          <p className="ask">Why keep it as is? Pick a reason (required).</p>
          <div className="chips">
            {KEEP_REASONS.map((r) => <button key={r} className="chip" aria-pressed={reason === r} onClick={() => setReason(r)}>{r}</button>)}
          </div>
          <div className="actions">
            <button className="btn primary" disabled={!reason || busy} onClick={() => go("keep", reason)}>Confirm keep as is</button>
            <button className="btn" onClick={() => { setKeeping(false); setReason(""); }}>Back</button>
          </div>
        </div>
      )}

      {!open && (
        <div className="decided">
          <span>
            {flag.status === "accepted" && "Accepted. Edit your design, then re-run to confirm this flag clears."}
            {flag.status === "kept" && `Kept as is: ${flag.decision?.reason ?? ""}`}
            {flag.status === "deferred" && "Marked for discussion at protocol review."}
            {flag.status === "resolved" && "Resolved: this flag no longer fires after your changes."}
          </span>
          {flag.status !== "resolved" && <button className="linkbtn" disabled={busy} onClick={() => go("undo")}>Undo</button>}
          <button className="linkbtn" aria-expanded={showTrials} onClick={() => setShowTrials(!showTrials)}>See the trials</button>
        </div>
      )}
      {err && <div className="err" role="alert">{err}</div>}
      {showTrials && <Evidence ids={flag.evidence_ids} />}
    </article>
  );
}
