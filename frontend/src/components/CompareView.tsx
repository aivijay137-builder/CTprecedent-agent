import type { Compare, CompareRow } from "../types";
import { nctUrl } from "../util";

const flagName = (id: string) =>
  id.startsWith("pop_") ? "Population" : id.startsWith("sites_") ? "Sites" : id.startsWith("endpoint_") ? "Endpoint" : id.startsWith("design_") ? "Design" : id.startsWith("size_") ? "Sample size" : id.replace(/_/g, " ");

function Rows({ rows, which }: { rows: CompareRow[]; which: "a" | "b" | "both" }) {
  if (!rows.length) return <p className="hint">None.</p>;
  return (
    <ul style={{ paddingLeft: 18 }}>
      {rows.map((r) => (
        <li key={r.nct_id} style={{ marginBottom: 6 }}>
          <a href={nctUrl(r.nct_id)} target="_blank" rel="noreferrer">{r.nct_id}</a> {r.title}
          <br /><span className="hint">
            {which === "a" && `was #${r.rank_a} without the pack`}
            {which === "b" && `now #${r.rank_b} with the pack`}
            {which === "both" && `#${r.rank_a} without the pack → #${r.rank_b} with it`}
            {which !== "a" && r.why_picked.includes("pack") ? `: ${r.why_picked.split(", ").filter((x) => x.includes("pack")).join("; ")}` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** What changed between the prompt-only run (A) and the pack run (B). It does NOT say which is better. */
export function CompareView({ cmp, onBack }: { cmp: Compare; onBack: () => void }) {
  const c = cmp.comparables, f = cmp.flags, log = cmp.pack_log;
  const swapped = c.only_a.length;
  const tok = (x?: { calls: number; tokens: number } | null) => (x && x.calls > 0 ? `${x.calls} AI call${x.calls === 1 ? "" : "s"}, about ${x.tokens.toLocaleString()} tokens` : "No AI");
  return (
    <div className="inner">
      <h1>Prompt only vs with a pack</h1>
      <p className="lead">The same design, run both ways. This shows <b>what changed</b>. It does not say which result is better.</p>

      <div className="card" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {[cmp.a, cmp.b].map((s, i) => (
          <div key={i}>
            <div className="label">{s.label}</div>
            <div className="big" style={{ margin: "4px 0" }}>{s.sentence}</div>
            <div className="hint">{s.risk ? `Risk: ${s.risk}. ` : ""}{tok(s.ai_usage)}</div>
          </div>
        ))}
      </div>

      <h2 className="sectionhead">Comparable trials</h2>
      <div className="banner grey" role="status">
        {c.in_both} of {cmp.a.n_comparables} trials appear in both lists, {c.same_rank} at exactly the same rank.
        {swapped === 0 ? " The pack did not change which trials are listed." : ` The pack swapped ${swapped} trial${swapped === 1 ? "" : "s"}.`}
      </div>
      {c.only_b.length > 0 && (<><h3>Brought in by the pack</h3><Rows rows={c.only_b} which="b" /></>)}
      {c.only_a.length > 0 && (<><h3>Left out by the pack</h3><Rows rows={c.only_a} which="a" /></>)}
      {c.moved.length > 0 && (<><h3>Biggest rank changes (in both lists)</h3><Rows rows={c.moved.slice(0, 5)} which="both" /></>)}

      <h2 className="sectionhead">Flags</h2>
      <div className="banner grey" role="status">
        {f.only_a.length === 0 && f.only_b.length === 0 && f.n_changed.length === 0
          ? `Same flags in both runs (${f.in_both.map(flagName).join(", ") || "none"}), with the same n.`
          : "The flags differ:"}
      </div>
      <ul style={{ paddingLeft: 18 }}>
        {f.only_a.map((i) => <li key={i}>Only without the pack: {flagName(i)}</li>)}
        {f.only_b.map((i) => <li key={i}>Only with the pack: {flagName(i)}</li>)}
        {f.n_changed.map((x) => <li key={x.id}>{flagName(x.id)}: n = {x.n_a} without the pack, {x.n_b} with it</li>)}
      </ul>

      {log.hard_filter && (
        <>
          <h2 className="sectionhead">What the pack did</h2>
          <ul style={{ paddingLeft: 18 }}>
            <li>Drug vs device filter: {log.hard_filter.applied ? `removed ${log.hard_filter.removed} trials` : log.hard_filter.relaxed ? "relaxed (too few trials would remain)" : "not applied"} ({log.hard_filter.reason}).</li>
            <li>Ranking hints: {log.ranking?.applied ? `${log.ranking.boosted_subtype ?? 0} trials boosted for subtype, ${log.ranking.boosted_endpoint_type ?? 0} for endpoint type` : "off"}.</li>
            <li>Older-trial penalty: {log.ranking?.era_applied ? `${log.ranking.penalised_era ?? 0} trials penalised` : "off"}.</li>
            <li>Prompt add-on: {log.parts?.addon ? "on (matters only when an AI key reads the text)" : "off"}.</li>
          </ul>
        </>
      )}

      <p className="hint">{cmp.note}</p>
      <div className="actions"><button className="btn primary" onClick={onBack}>Back to the results</button></div>
    </div>
  );
}
