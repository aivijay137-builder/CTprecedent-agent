"""API contract. Every request and response shape lives here (see docs/api.md)."""
from typing import Literal, Optional
from pydantic import BaseModel, Field

from brief import DesignBrief  # reused from src/brief.py

Risk = Literal["low", "medium", "high", "insufficient"]  # "insufficient" = fewer than 5 comparables
Tier = Literal["stated", "outside", "unknown"]
Element = Literal["population", "endpoints", "size", "sites", "design"]
FlagStatus = Literal["open", "accepted", "kept", "deferred", "resolved"]
ALL_ELEMENTS: list[str] = ["population", "endpoints", "size", "sites", "design"]


# ---- briefs ----
class NctIn(BaseModel):
    nct_id: str


class ParseIn(BaseModel):
    eligibility_text: str
    condition: str = ""


class Cutoff(BaseModel):
    key: Optional[str] = None  # machine name, e.g. fev1_pct_predicted_min
    field: str
    value: Optional[str] = None
    unit: str = ""
    source_sentence: str = ""
    valid: bool = True  # False = the source sentence could not be matched in the text


class ParseOut(BaseModel):
    cutoffs: list[Cutoff]
    note: Optional[str] = None  # shown to the user, e.g. "live parsing is not available yet"


# ---- runs ----
class RunIn(BaseModel):
    brief: DesignBrief
    focus: list[Element] = Field(default_factory=lambda: list(ALL_ELEMENTS))
    filters: dict = Field(default_factory=dict)
    excluded_ids: list[str] = Field(default_factory=list)


class RunId(BaseModel):
    run_id: str


class RerunIn(BaseModel):
    brief: DesignBrief
    excluded_ids: list[str] = Field(default_factory=list)


class BottomLine(BaseModel):
    risk: Risk
    n_comparables: int
    n_terminated: int
    n_terminated_enrollment: int
    sentence: str


class Comparable(BaseModel):
    nct_id: str
    title: str
    why_picked: str
    similarity: float
    status: str  # CT.gov overallStatus, e.g. COMPLETED, TERMINATED
    stop_reason: Optional[str] = None  # verbatim whyStopped; None = not stated
    stop_tier: Optional[Tier] = None  # None for trials that did not stop
    enrollment: Optional[int] = None
    has_results: bool = False


class Outcomes(BaseModel):
    comparables: dict[str, int]
    baseline: dict[str, int]  # all trials for the same condition


class StopQuote(BaseModel):
    nct_id: str
    quote: Optional[str] = None


class StopCause(BaseModel):
    cause: str
    count: int
    tier: Tier
    quotes: list[StopQuote] = Field(default_factory=list)


class Finding(BaseModel):
    text: str
    n: int
    evidence_ids: list[str] = Field(default_factory=list)  # len == n, except "not found" (n = 0)


class ElementFindings(BaseModel):
    findings: list[Finding] = Field(default_factory=list)


class Decision(BaseModel):
    action: Literal["accept", "keep", "defer"]
    reason: Optional[str] = None
    role: str
    at: str


class Flag(BaseModel):
    id: str  # rule id, stable across re-runs
    element: Element
    title: str
    body: str
    question: str
    confidence: Tier
    evidence_ids: list[str]
    status: FlagStatus = "open"
    action_label: str = "Accept"  # label of the primary button
    n: int = 0  # trials the claim is computed over (the evidence base); never below MIN_N
    source_url: Optional[str] = None  # a link to an outside source; confidence 'outside' is allowed only with one
    written_by: Literal["template", "ai"] = "template"  # 'ai' = reworded by the AI from the evidence bundle; every number was checked
    decision: Optional[Decision] = None


class DiffItem(BaseModel):
    id: str
    title: str


class Diff(BaseModel):
    resolved: list[DiffItem] = Field(default_factory=list)
    still_open: list[DiffItem] = Field(default_factory=list)
    new: list[DiffItem] = Field(default_factory=list)


class AuditItem(BaseModel):
    name: str
    sql: str  # the exact SQL behind a number; run it in DuckDB against ctg.duckdb to verify


class RunResult(BaseModel):
    run_id: str
    brief_echo: DesignBrief
    data_as_of: str  # ISO date
    condition_support: Literal["full", "basic"]
    bottom_line: BottomLine
    comparables: list[Comparable]
    outcomes: Outcomes
    stop_causes: list[StopCause]
    elements: dict[Element, ElementFindings]
    flags: list[Flag] = Field(default_factory=list, max_length=3)
    no_flags_reason: Optional[str] = None  # set when flags is empty on purpose
    rule_notes: list[str] = Field(default_factory=list)  # why a rule could not be checked
    ai_usage: Optional[dict] = None  # {calls, tokens, own_key}: what the AI reading cost this run
    limits: list[str]
    diff: Optional[Diff] = None  # only on a re-run
    package_id: Optional[str] = None  # set once packaged; cleared by any later decision
    audit: list[AuditItem] = Field(default_factory=list)


class RerunOut(BaseModel):
    run_id: str
    diff: Diff


# ---- decisions, packages, review ----
class DecisionIn(BaseModel):
    action: Literal["accept", "keep", "defer", "undo"]
    reason: Optional[str] = None  # required for "keep"


class PackageId(BaseModel):
    package_id: str


class Review(BaseModel):
    action: Literal["agree", "send_back"]
    comment: Optional[str] = None
    role: str
    at: str


class ReviewIn(BaseModel):
    flag_id: str
    action: Literal["agree", "send_back"]
    comment: Optional[str] = None


class PackageSnapshot(BaseModel):
    package_id: str
    run_id: str
    created_at: str
    data_as_of: str
    brief_echo: DesignBrief
    bottom_line: BottomLine
    flags: list[Flag]  # frozen at packaging time, deferred first
    reviews: dict[str, Review] = Field(default_factory=dict)  # by flag id


# ---- evidence + health ----
class TrialSummary(BaseModel):
    nct_id: str
    title: str
    status: str
    stop_reason: Optional[str] = None
    stop_tier: Optional[Tier] = None
    enrollment: Optional[int] = None
    has_results: bool = False
    sponsor: str = ""
    phase: str = ""
    start_date: str = ""
    countries: list[str] = Field(default_factory=list)


class ConditionSuggestion(BaseModel):
    term: str  # a registry (MeSH) condition
    n_trials: int  # interventional trials with that condition


class Health(BaseModel):
    data_as_of: str
    row_counts: dict[str, int]
    llm_configured: bool
    llm_enabled: bool = False
    fixtures: bool
    last_sync: dict | None = None
    sync_warning: str | None = None
    version: str = "dev"
