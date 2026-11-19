// Mirrors backend/schemas.py. Keep the two in step.
export type Tier = "stated" | "outside" | "unknown";
export type Element = "population" | "endpoints" | "size" | "sites" | "design";
export type FlagStatus = "open" | "accepted" | "kept" | "deferred" | "resolved";
export type Role = "lead" | "reviewer";

export interface DesignBrief {
  source: "form" | "nct" | "usdm";
  nct_id: string | null;
  condition: string;
  mesh_terms: string[];
  phase: string[];
  intervention_type: string[];
  eligibility_text: string;
  structured_cutoffs: { cutoffs: Cutoff[] } | null;
  primary_endpoint: string;
  primary_endpoint_timeframe: string;
  target_enrollment: number | null;
  enrollment_type: "ACTUAL" | "ESTIMATED" | null;
  countries: string[];
  arm_types: string[];
}

export interface Cutoff {
  key?: string | null;
  field: string;
  value: string | null;
  unit: string;
  source_sentence: string;
  valid: boolean;
}

export interface Comparable {
  nct_id: string;
  title: string;
  why_picked: string;
  similarity: number;
  status: string;
  stop_reason: string | null;
  stop_tier: Tier | null;
  enrollment: number | null;
  has_results: boolean;
}

export interface Finding { text: string; n: number; evidence_ids: string[] }
export interface Decision { action: "accept" | "keep" | "defer"; reason: string | null; role: string; at: string }

export interface Flag {
  id: string;
  element: Element;
  title: string;
  body: string;
  question: string;
  confidence: Tier;
  evidence_ids: string[];
  status: FlagStatus;
  action_label: string;
  n?: number;
  source_url?: string | null;
  written_by?: "template" | "ai";
  decision: Decision | null;
}

export interface DiffItem { id: string; title: string }
export interface Diff { resolved: DiffItem[]; still_open: DiffItem[]; new: DiffItem[] }

export interface RunResult {
  run_id: string;
  brief_echo: DesignBrief;
  data_as_of: string;
  ai_usage?: { calls: number; tokens: number; own_key: boolean } | null;
  pack?: PackLog | null;
  condition_support: "full" | "basic";
  bottom_line: {
    risk: "low" | "medium" | "high" | "insufficient";
    n_comparables: number;
    n_terminated: number;
    n_terminated_enrollment: number;
    sentence: string;
  };
  comparables: Comparable[];
  outcomes: { comparables: Record<string, number>; baseline: Record<string, number> };
  stop_causes: { cause: string; count: number; tier: Tier; quotes: { nct_id: string; quote: string | null }[] }[];
  elements: Record<Element, { findings: Finding[] }>;
  flags: Flag[];
  no_flags_reason: string | null;
  rule_notes?: string[];
  limits: string[];
  diff: Diff | null;
  package_id: string | null;
  audit?: { name: string; sql: string }[];
}

export interface Review { action: "agree" | "send_back"; comment: string | null; role: string; at: string }
export interface PackageSnapshot {
  package_id: string;
  run_id: string;
  created_at: string;
  data_as_of: string;
  brief_echo: DesignBrief;
  bottom_line: RunResult["bottom_line"];
  flags: Flag[];
  reviews: Record<string, Review>;
}

export interface TrialSummary {
  nct_id: string; title: string; status: string; stop_reason: string | null; stop_tier: Tier | null;
  enrollment: number | null; has_results: boolean; sponsor: string; phase: string; start_date: string; countries: string[];
}

export interface Health { data_as_of: string; row_counts: Record<string, number>; llm_configured: boolean; fixtures: boolean }

export interface StepEvent { step: number; label: string; status: "running" | "done"; elapsed_ms: number }

// ---- therapeutic packs (optional; the server reports none when no pack files are installed)
export interface PackInfo { id: string; level: "area" | "indication"; label: string; version: string; status: string; parent?: string | null }
export interface PackChoice { area: string | null; indication: string | null; parts: Record<string, boolean> }
export interface PackRoute {
  available: boolean; area?: string | null; indication?: string | null; reason?: string; all_packs?: PackInfo[];
  preview?: { label: string; status: string; versions: Record<string, string>; addon_text: string; n_subtypes: number; n_endpoint_types: number; n_era_rules: number; hard_filter?: string | null } | null;
}
export interface PackLog {
  pack: string; status: string; parts: Record<string, boolean>;
  hard_filter: { applied: boolean; relaxed: boolean; removed: number; reason: string; name?: string; would_remove?: number };
  ranking: { applied: boolean; reason?: string; design_subtypes?: string[]; design_endpoint_type?: string | null; boosted_subtype?: number; boosted_endpoint_type?: number; penalised_era?: number; era_applied?: boolean; window?: number };
}
export interface CompareRow { nct_id: string; title: string; why_picked: string; rank_a?: number; rank_b?: number }
export interface Compare {
  a: { run_id: string; label: string; n_comparables: number; risk: string | null; sentence: string | null; ai_usage?: { calls: number; tokens: number } | null };
  b: { run_id: string; label: string; n_comparables: number; risk: string | null; sentence: string | null; ai_usage?: { calls: number; tokens: number } | null };
  comparables: { in_both: number; same_rank: number; only_a: CompareRow[]; only_b: CompareRow[]; moved: CompareRow[] };
  flags: { in_both: string[]; only_a: string[]; only_b: string[]; n_changed: { id: string; n_a: number; n_b: number }[] };
  pack_log: Partial<PackLog>; note: string;
}
