import { useEffect, useState } from "react";
import { api } from "../api";
import type { DesignBrief, PackChoice, PackRoute } from "../types";

export const DEFAULT_PARTS: Record<string, boolean> = { addon: true, ranking: true, hard_filter: true, era: false };
const PARTS: { key: string; label: string; help: string }[] = [
  { key: "addon", label: "Prompt add-on", help: "Extra guidance for the AI when it reads eligibility text. Only matters if you added an AI key." },
  { key: "ranking", label: "Ranking hints", help: "Nudges trials of the same subtype and the same kind of endpoint a little higher. Never removes a trial." },
  { key: "hard_filter", label: "Drug vs device filter", help: "Leaves out trials of a different kind (for example device trials for a drug design). Relaxed automatically if fewer than 5 trials would remain." },
  { key: "era", label: "Older-trial penalty (draft)", help: "Pushes trials that started before a drug class changed practice lower. Off by default: these years are unreviewed drafts." },
];

/** The design lead's choice for this run: prompt only (default) or prompt + a therapeutic pack. Renders nothing when the server has no packs. */
export function PackOptions({ brief, choice, onChange }: { brief: DesignBrief; choice: PackChoice | null; onChange: (c: PackChoice | null) => void }) {
  const [route, setRoute] = useState<PackRoute | null>(null);
  const [showText, setShowText] = useState(false);
  const terms = brief.mesh_terms.join("|");

  useEffect(() => {
    let live = true;
    api.packsRoute(brief.condition, brief.mesh_terms, choice ? { area: choice.area, indication: choice.indication } : undefined)
      .then((r) => live && setRoute(r)).catch(() => live && setRoute({ available: false }));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [brief.condition, terms, choice?.area, choice?.indication]);

  if (!route?.available) return null;
  const packs = route.all_packs ?? [];
  const areas = packs.filter((p) => p.level === "area");
  const inds = packs.filter((p) => p.level === "indication");
  const on = choice !== null;
  const start = () => onChange({ area: route.area ?? areas[0]?.id ?? null, indication: route.indication ?? null, parts: { ...DEFAULT_PARTS } });
  const set = (p: Partial<PackChoice>) => choice && onChange({ ...choice, ...p });
  const pickInd = (id: string) => {
    const ind = inds.find((p) => p.id === id);
    set({ indication: id || null, area: ind?.parent ?? choice?.area ?? null });
  };
  const prev = route.preview;

  return (
    <>
      <h2 className="sectionhead">Precedent check options</h2>
      <div className="card" role="group" aria-label="Prompt only or prompt with a therapeutic pack">
        <label style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
          <input type="radio" name="packmode" checked={!on} onChange={() => onChange(null)} />
          <span><b>Prompt only</b> (default). The standard check, exactly as before.</span>
        </label>
        <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input type="radio" name="packmode" checked={on} onChange={start} disabled={!route.area && !areas.length} />
          <span><b>Prompt + therapeutic pack</b>. Adds area-specific guidance and ranking hints. You can run both and compare.</span>
        </label>

        {!on && route.area && <p className="hint" style={{ marginTop: 8 }}>A pack is available for this condition: {route.reason}</p>}
        {!on && !route.area && <p className="hint" style={{ marginTop: 8 }}>{route.reason}</p>}

        {on && choice && (
          <div style={{ marginTop: 12 }}>
            <div className="banner amber" role="note">
              <b>Draft pack, not reviewed by an expert.</b> Its numbers come from the registry, but its wording and rules are a first draft. Treat the result as a comparison, not as advice.
            </div>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", margin: "8px 0" }}>
              <label className="field"><span>Area pack</span>
                <select value={choice.area ?? ""} onChange={(e) => set({ area: e.target.value || null, indication: choice.indication && inds.find((p) => p.id === choice.indication)?.parent === e.target.value ? choice.indication : null })}>
                  {areas.map((p) => <option key={p.id} value={p.id}>{p.label} (v{p.version}, {p.status})</option>)}
                </select></label>
              <label className="field"><span>Indication pack (optional)</span>
                <select value={choice.indication ?? ""} onChange={(e) => pickInd(e.target.value)}>
                  <option value="">None</option>
                  {inds.filter((p) => !choice.area || p.parent === choice.area).map((p) => <option key={p.id} value={p.id}>{p.label} (v{p.version}, {p.status})</option>)}
                </select></label>
            </div>
            <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
              <legend className="label" style={{ marginBottom: 4 }}>What to use from the pack</legend>
              {PARTS.map((p) => (
                <label key={p.key} style={{ display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 6 }}>
                  <input type="checkbox" checked={!!choice.parts[p.key]} onChange={(e) => set({ parts: { ...choice.parts, [p.key]: e.target.checked } })} style={{ marginTop: 3 }} />
                  <span><b>{p.label}</b><br /><span className="hint">{p.help}</span></span>
                </label>
              ))}
            </fieldset>
            {prev && (
              <p className="hint">This pack has {prev.n_subtypes} subtype hints, {prev.n_endpoint_types} endpoint types{prev.hard_filter ? " and a drug-vs-device filter" : ""}.
                {" "}<button className="linkbtn" type="button" onClick={() => setShowText(!showText)}>{showText ? "Hide" : "Read"} the prompt add-on text</button></p>
            )}
            {showText && prev && <pre className="card" style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>{prev.addon_text}</pre>}
          </div>
        )}
      </div>
    </>
  );
}
