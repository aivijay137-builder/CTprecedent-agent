import type { Comparable, Element, Tier } from "./types";

export const fmtDate = (iso: string) => {
  const d = new Date(iso + "T00:00:00");
  return isNaN(+d) ? iso : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
};

export const daysOld = (iso: string) => Math.floor((Date.now() - +new Date(iso + "T00:00:00")) / 86400000);
export const isStale = (iso: string) => daysOld(iso) > 3;

export const nctUrl = (id: string) => `https://clinicaltrials.gov/study/${id}`;

export const ELEMENT_LABEL: Record<Element, string> = {
  population: "Population", endpoints: "Endpoints", size: "Sample size", sites: "Sites", design: "Design",
};

export const CONFIDENCE_LABEL: Record<Tier, string> = {
  stated: "Stated in record", outside: "Supported by outside source", unknown: "Not stated",
};

export const TIER_LABEL: Record<Tier, string> = { stated: "stated in record", outside: "outside source", unknown: "not stated" };

export function howEnded(c: Comparable): string {
  switch (c.status) {
    case "COMPLETED": return c.has_results ? "Completed, results posted" : "Completed, no results";
    case "TERMINATED": return "Terminated";
    case "WITHDRAWN": return "Withdrawn";
    case "UNKNOWN": return "Status unknown";
    case "RECRUITING": return "Recruiting";
    default: return c.status.replaceAll("_", " ").toLowerCase();
  }
}

export const BUCKET_LABEL: Record<string, string> = {
  completed_results: "Completed, results posted", completed_no_results: "Completed, no results",
  terminated: "Terminated", withdrawn: "Withdrawn", unknown: "Status unknown", running: "Still running",
};

// Control-arm choices for the forms. Values map to ClinicalTrials.gov arm-group types (what the Design rule reads).
export const CONTROL_OPTIONS: { value: string; label: string; arms: string[] }[] = [
  { value: "", label: "Not sure", arms: [] },
  { value: "PLACEBO", label: "Placebo", arms: ["EXPERIMENTAL", "PLACEBO_COMPARATOR"] },
  { value: "ACTIVE", label: "Active comparator", arms: ["EXPERIMENTAL", "ACTIVE_COMPARATOR"] },
  { value: "SHAM", label: "Sham", arms: ["EXPERIMENTAL", "SHAM_COMPARATOR"] },
  { value: "NOTX", label: "No-treatment control", arms: ["EXPERIMENTAL", "NO_INTERVENTION"] },
  { value: "SINGLE", label: "None (single-arm)", arms: ["EXPERIMENTAL"] },
];
export function controlValue(arms: string[] = []): string {
  if (!arms.length) return "";
  const has = (a: string) => arms.includes(a);
  return has("PLACEBO_COMPARATOR") ? "PLACEBO" : has("ACTIVE_COMPARATOR") ? "ACTIVE" : has("SHAM_COMPARATOR") ? "SHAM" : has("NO_INTERVENTION") ? "NOTX" : "SINGLE";
}

export const KEEP_REASONS = ["Needed for the mechanism", "Regulatory requirement", "Follows our earlier study", "Other"];

export const store = {
  get<T>(k: string): T | null {
    try { const v = localStorage.getItem(k); return v ? (JSON.parse(v) as T) : null; } catch { return null; }
  },
  set(k: string, v: unknown) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage blocked: fine */ } },
};
