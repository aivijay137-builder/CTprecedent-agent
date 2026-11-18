import type { Role } from "../types";
import { demoExamples } from "../api";
import { fmtDate, isStale } from "../util";

export const NAV = [{ id: "population", label: "Study Design", next: false }];

export function TopBar({ role, onRole, meta, onSettings, aiOn }: { role: Role; onRole: (r: Role) => void; meta: string; onSettings?: () => void; aiOn?: boolean }) {
  return (
    <header className="topbar">
      <span className="logo" aria-hidden="true" />
      <span className="name">Déjà Trial</span>
      <span className="meta">{meta}</span>
      <div className="toggle" role="group" aria-label="View as">
        <button aria-pressed={role === "lead"} onClick={() => onRole("lead")}>Study lead</button>
        <button aria-pressed={role === "reviewer"} onClick={() => onRole("reviewer")}>Reviewer</button>
      </div>
      {import.meta.env.VITE_DEMO_URL && <a className="demolink" href={import.meta.env.VITE_DEMO_URL} target="_blank" rel="noreferrer"><span>Concept prototype.</span> <b>See worked examples</b></a>}
      {onSettings && <button className="btn" onClick={onSettings} title="Optional: use your own AI key">{aiOn ? "AI key: on" : "AI key"}</button>}
    </header>
  );
}

export function LeftNav({ active, onPick, onlyPopulation = false, startHere = false }: { active: string; onPick: (id: string) => void; onlyPopulation?: boolean; startHere?: boolean }) {
  return (
    <nav className="nav" aria-label="Design elements">
      <div className="label">Design</div>
      {NAV.map((n) => (
        <button key={n.id} className={`${n.next ? "next" : ""} ${onlyPopulation && n.id === "population" ? "start" : ""}`.trim()} aria-current={active === n.id ? "page" : undefined} onClick={() => onPick(n.id)}
          disabled={onlyPopulation && n.id !== "population"} title={onlyPopulation && n.id !== "population" ? "Not part of this prototype. Only Population has the precedent check." : undefined}>
          {n.label}
          {onlyPopulation && n.id === "population" && startHere && <span className="startpill">Start here</span>}
        </button>
      ))}
    </nav>
  );
}

export interface Status { label: string; tone: "" | "amber" | "green" | "blue" }

export function SidePanel({ status, onOpen, dataAsOf, fixtures }: { status: Status; onOpen: () => void; dataAsOf: string; fixtures: boolean }) {
  const stale = isStale(dataAsOf) && demoExamples().length === 0; // the saved-results demo is a replay, so its date is not 'old'
  return (
    <aside className="side" aria-label="Design checks">
      <div className="label">Design checks</div>
      <button className="pcard" onClick={onOpen} aria-label={`Precedent check, ${status.label}. Open`}>
        <div className="row"><span className="t">Precedent</span><span className={`badge ${status.tone}`}>{status.label}</span></div>
        <p className="d">How comparable trials on ClinicalTrials.gov ended, and why.</p>
      </button>
      <Footer dataAsOf={dataAsOf} stale={stale} fixtures={fixtures} />
    </aside>
  );
}

export function Footer({ dataAsOf, stale, fixtures }: { dataAsOf: string; stale: boolean; fixtures: boolean }) {
  return (
    <footer className="footer">
      {fixtures && <span className="fx">Illustrative fixture data.</span>}
      Data from ClinicalTrials.gov as of <span className={stale ? "stale" : ""}>{fmtDate(dataAsOf)}{stale ? " (older than 3 days)" : ""}</span>.
      Concept prototype.
    </footer>
  );
}
