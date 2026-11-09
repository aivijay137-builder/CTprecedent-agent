"""Design Brief: the one input shape the whole agent uses."""
from typing import Literal, Optional
from pydantic import BaseModel, Field


class DesignBrief(BaseModel):
    """Draft trial design.

    NOTE: for finished trials, enrollment is ACTUAL and the original target is
    lost (the CT.gov snapshot has no change history).
    """
    source: Literal["form", "nct", "usdm"]
    nct_id: Optional[str] = None
    condition: str = ""
    mesh_terms: list[str] = Field(default_factory=list)
    phase: list[str] = Field(default_factory=list)  # e.g. ["PHASE2"]
    intervention_type: list[str] = Field(default_factory=list)
    eligibility_text: str = ""
    structured_cutoffs: Optional[dict] = None  # filled in Step 2
    primary_endpoint: str = ""
    primary_endpoint_timeframe: str = ""
    target_enrollment: Optional[int] = None
    enrollment_type: Optional[Literal["ACTUAL", "ESTIMATED"]] = None
    countries: list[str] = Field(default_factory=list)
    arm_types: list[str] = Field(default_factory=list)  # CT.gov arm-group types, e.g. EXPERIMENTAL, PLACEBO_COMPARATOR; empty = not stated
