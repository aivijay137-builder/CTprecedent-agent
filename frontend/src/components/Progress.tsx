import { useEffect, useState } from "react";
import { openEvents } from "../source";
import type { StepEvent } from "../types";

const DEFAULT = ["Finding comparable trials", "Counting how they ended", "Reading why they stopped", "Checking each design element", "Writing the flags"];

export function Progress({ runId, onDone, onCancel, onRetry }: {
  runId: string; onDone: () => void; onCancel: () => void; onRetry: () => void;
}) {
  const [steps, setSteps] = useState<Record<number, StepEvent>>({});
  const [error, setError] = useState("");
  const [reconnecting, setReconnecting] = useState(false);
  const [announce, setAnnounce] = useState("Starting the precedent check.");

  useEffect(() => {
    setSteps({}); setError("");
    const es = openEvents(runId);
    let finished = false;
    es.addEventListener("step", (m) => {
      const s: StepEvent = JSON.parse((m as MessageEvent).data);
      setSteps((p) => ({ ...p, [s.step]: s }));
      setAnnounce(`Step ${s.step} of 5, ${s.label}: ${s.status === "done" ? "done" : "in progress"}.`);
    });
    es.addEventListener("done", () => { finished = true; es.close(); onDone(); });
    es.addEventListener("error", (m) => {
      if (finished) return;
      const data = (m as MessageEvent).data;
      if (data) { es.close(); setError(JSON.parse(data).message); return; }  // the server itself reported a failure
      if (es.readyState === 2) { setError("The connection to the server was lost."); return; }  // closed for good (EventSource.CLOSED)
      setReconnecting(true);  // a dropped connection: the browser reconnects by itself and the check keeps running on the server
    });
    es.addEventListener("open", () => setReconnecting(false));
    return () => { finished = true; es.close(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  if (error) {
    return (
      <div className="inner">
        <h1>The check did not finish</h1>
        <div className="banner red" role="alert" style={{ marginTop: 16 }}>{error}</div>
        <p className="lead">Nothing was changed in your design.</p>
        <div className="actions"><button className="btn primary" onClick={onRetry}>Retry</button><button className="btn" onClick={onCancel}>Back to the design</button></div>
      </div>
    );
  }
  return (
    <div className="inner">
      <h1>Checking precedent</h1>
      <p className="lead">Looking at how similar trials on ClinicalTrials.gov ended. This usually takes under a minute.</p>
      <div className="sr" aria-live="polite" role="status">{announce}</div>
      {reconnecting && <div className="banner grey" role="status">Connection interrupted. Reconnecting… your check is still running.</div>}
      <ol className="steps card" style={{ marginTop: 16, padding: "0 16px", listStyle: "none" }}>
        {DEFAULT.map((label, i) => {
          const s = steps[i + 1];
          const state = s ? s.status : "waiting";
          return (
            <li key={i} className={state}>
              <span className="ic" aria-hidden="true">{state === "done" ? "✓" : ""}</span>
              <span>{i + 1}. {s?.label ?? label}</span>
              <span className="time">{state === "done" ? `${(s!.elapsed_ms / 1000).toFixed(1)} s` : state === "running" ? "working…" : "waiting"}</span>
            </li>
          );
        })}
      </ol>
      <div className="actions"><button className="btn" onClick={onCancel}>Cancel</button></div>
    </div>
  );
}
