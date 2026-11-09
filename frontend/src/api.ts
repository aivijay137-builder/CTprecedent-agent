import type { Cutoff, DesignBrief, Diff, Flag, Health, PackageSnapshot, Role, RunResult, TrialSummary } from "./types";

let role: Role = "lead";
export const setRole = (r: Role) => { role = r; };
// demo hooks: empty here (the demo build replaces this file with src/demo/api.ts)
export const demoExamples = (): { key: string; label: string; blurb: string }[] => [];
export const demoReset = () => {};

const API = import.meta.env.VITE_API_URL ?? ""; // Vercel: the Railway address; local: empty (the dev server proxies /api)

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API + "/api" + path, {
      method,
      headers: { "Content-Type": "application/json", "X-Role": role },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error("Can't reach the API server (port 8765). Check that `npm run dev` is still running in your terminal, then try again.");
  }
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* keep statusText */ }
    throw new Error(msg);
  }
  return res.json();
}

const trialCache = new Map<string, Promise<TrialSummary>>();

export const api = {
  health: () => call<Health>("GET", "/health"),
  fromNct: (nct_id: string) => call<DesignBrief>("POST", "/briefs/from-nct", { nct_id }),
  suggest: (q: string) => call<{ term: string; n_trials: number }[]>("GET", `/conditions/suggest?q=${encodeURIComponent(q)}`),
  parse: (eligibility_text: string, condition: string) =>
    call<{ cutoffs: Cutoff[]; note?: string | null }>("POST", "/briefs/parse", { eligibility_text, condition }),
  createRun: (brief: DesignBrief, focus: string[], excluded_ids: string[] = []) =>
    call<{ run_id: string }>("POST", "/runs", { brief, focus, filters: {}, excluded_ids }),
  getRun: (id: string) => call<RunResult>("GET", `/runs/${id}`),
  decide: (runId: string, flagId: string, action: string, reason?: string) =>
    call<Flag>("POST", `/runs/${runId}/flags/${flagId}/decision`, { action, reason }),
  rerun: (runId: string, brief: DesignBrief, excluded_ids: string[]) =>
    call<{ run_id: string; diff: Diff }>("POST", `/runs/${runId}/rerun`, { brief, excluded_ids }),
  makePackage: (runId: string) => call<{ package_id: string }>("POST", `/runs/${runId}/package`),
  getPackage: (id: string) => call<PackageSnapshot>("GET", `/packages/${id}`),
  review: (pid: string, flag_id: string, action: "agree" | "send_back", comment?: string) =>
    call<PackageSnapshot>("POST", `/packages/${pid}/review`, { flag_id, action, comment }),
  trial: (nct: string) => {
    if (!trialCache.has(nct)) trialCache.set(nct, call<TrialSummary>("GET", `/trials/${nct}`));
    return trialCache.get(nct)!;
  },
};
