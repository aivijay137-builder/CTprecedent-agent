import { useState } from "react";
import type { Flag, PackageSnapshot } from "../types";
import { ELEMENT_LABEL, fmtDate } from "../util";

function detail(f: Flag): string {
  if (f.status === "kept" || f.decision?.action === "keep") return `Kept as is: ${f.decision?.reason ?? ""}`;
  if (f.decision?.action === "accept") return "Accepted and edited";
  if (f.decision?.action === "defer") return "Marked for discussion at review";
  return f.status;
}

export function PackageView({ pkg, onReview }: { pkg: PackageSnapshot | null; onReview: (flagId: string, action: "agree" | "send_back", comment?: string) => Promise<void> }) {
  const [backing, setBacking] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [err, setErr] = useState("");
  if (!pkg) {
    return (
      <div className="inner">
        <div className="card"><h1>Protocol review: precedent check</h1>
          <p className="lead">No precedent check has been added to the review package yet. The study lead adds it once every flag has a decision.</p></div>
      </div>
    );
  }
  const go = async (id: string, a: "agree" | "send_back", c?: string) => {
    setErr("");
    try { await onReview(id, a, c); setBacking(null); setComment(""); } catch (e) { setErr((e as Error).message); }
  };
  return (
    <div className="inner">
      <div className="card" style={{ padding: 24 }}>
        <h1>Protocol review: precedent check</h1>
        <p className="lead">Snapshot of draft v3, registry data as of {fmtDate(pkg.data_as_of)}. Deferred flags first.</p>
        <div style={{ marginTop: 16 }}>
          {pkg.flags.length === 0 && <p className="lead">This check raised no flags.</p>}
          {pkg.flags.map((f) => {
            const r = pkg.reviews[f.id];
            return (
              <div key={f.id}>
                <div className="rrow">
                  <div className="t"><b>{ELEMENT_LABEL[f.element]}: {f.title}</b><span>{detail(f)}</span></div>
                  {r ? (
                    <span className={`badge ${r.action === "agree" ? "green" : "amber"}`}>{r.action === "agree" ? "Agreed" : "Sent back to study lead"}</span>
                  ) : (
                    <div className="btns">
                      <button className="btn green" onClick={() => go(f.id, "agree")}>Agree</button>
                      <button className="btn" aria-expanded={backing === f.id} onClick={() => setBacking(backing === f.id ? null : f.id)}>Send back</button>
                    </div>
                  )}
                </div>
                {r?.comment && <p className="lead" style={{ margin: "4px 16px" }}>Comment: {r.comment}</p>}
                {backing === f.id && !r && (
                  <div className="card" style={{ marginTop: 4 }}>
                    <label className="field"><span>Comment for the study lead (optional)</span>
                      <textarea style={{ minHeight: 80 }} value={comment} onChange={(e) => setComment(e.target.value)} /></label>
                    <div className="actions"><button className="btn primary" onClick={() => go(f.id, "send_back", comment)}>Send back and reopen the flag</button>
                      <button className="btn" onClick={() => setBacking(null)}>Cancel</button></div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
        {err && <div className="err" role="alert">{err}</div>}
      </div>
    </div>
  );
}
