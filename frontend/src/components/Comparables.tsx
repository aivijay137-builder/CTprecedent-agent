import type { Comparable } from "../types";
import { TIER_LABEL, howEnded, nctUrl } from "../util";

export function Comparables({ items, excluded, onToggle }: { items: Comparable[]; excluded: string[]; onToggle: (id: string) => void }) {
  const kept = items.length - excluded.filter((id) => items.some((c) => c.nct_id === id)).length;
  return (
    <div className="tablewrap">
      <table>
        <caption className="sr">Comparable trials</caption>
        <thead><tr><th scope="col">Trial</th><th scope="col">Why picked</th><th scope="col">How it ended</th><th scope="col">Stop reason</th><th scope="col"><span className="sr">Remove or restore</span></th></tr></thead>
        <tbody>
          {items.map((c) => {
            const gone = excluded.includes(c.nct_id);
            return (
              <tr key={c.nct_id} className={gone ? "removed" : ""}>
                <td><a href={nctUrl(c.nct_id)} target="_blank" rel="noreferrer"><b>{c.nct_id}</b></a><span className="ttl">{c.title}</span></td>
                <td style={{ minWidth: 220 }}>{c.why_picked}</td>
                <td style={{ minWidth: 150 }}>{howEnded(c)}</td>
                <td>
                  {c.status !== "TERMINATED" ? "—" : (
                    <>{c.stop_reason ?? "Reason not stated"}{" "}<span className="tier">({TIER_LABEL[c.stop_tier ?? "unknown"]})</span></>
                  )}
                </td>
                <td style={{ whiteSpace: "nowrap" }}><button className="linkbtn" aria-label={`${gone ? "Restore" : "Remove"} ${c.nct_id}`} onClick={() => onToggle(c.nct_id)}>{gone ? "Restore" : "Remove"}</button></td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="tablefoot">Showing {items.length} of {items.length} comparables{kept !== items.length ? ` (${items.length - kept} marked for removal)` : ""}. Removing one changes the counts after you re-run.</div>
    </div>
  );
}
