"""Validation for therapeutic-area packs (config files in Prompts/packs). Run:  python -m packs.schema   (from the src folder)  or  python src/packs/schema.py
Fails when: a number has no n, a rule has no rationale or no evidence, a prompt add-on is over 150 words, or a pack has a hard filter without a fallback position."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ROOT = Path(__file__).resolve().parent.parent.parent / "Prompts" / "packs"


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n: int = Field(ge=0)                     # how many trials the number rests on
    query: str                               # id of the SQL in _mined/_queries.sql


class Rule(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    mode: Literal["hard_filter", "boost", "penalty"]
    rationale: str = Field(min_length=20)    # plain English: why the rule exists
    evidence: Evidence
    relax_rank: Optional[int] = None         # hard filters only: 1 = relaxed first

    @model_validator(mode="after")
    def _hard_needs_rank(self):
        if self.mode == "hard_filter" and self.relax_rank is None:
            raise ValueError(f"hard filter '{self.name}' needs relax_rank (the fallback ladder)")
        return self


class Field_(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    label: str
    unit: str = ""
    synonyms: list[str]
    evidence: Evidence
    rationale: str = Field(min_length=15)


class Norm(BaseModel):
    model_config = ConfigDict(extra="allow")
    field: str
    n: int = Field(ge=0)
    low_n: bool                              # true when n < 30: do not lean on it
    source: str

    @model_validator(mode="after")
    def _low(self):
        if self.low_n != (self.n < 30):
            raise ValueError(f"norm '{self.field}': low_n must be {self.n < 30} for n={self.n}")
        return self


class Pack(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    level: Literal["base", "area", "indication"]
    version: str
    status: Literal["draft", "reviewed"]
    routing: dict
    prompt_addon: str
    extraction_fields: list[Field_] = []
    subtypes: list[Rule] = []
    trial_archetypes: list[Rule] = []
    era_breakpoints: list[Rule] = []
    intervention_split: Optional[Rule] = None
    cutoff_norms: list[Norm] = []
    design_norms: dict = {}
    outcome_priors: dict = {}
    eval: dict

    @field_validator("prompt_addon")
    @classmethod
    def _addon_len(cls, v):
        if len(v.split()) > 150:
            raise ValueError(f"prompt_addon has {len(v.split())} words (max 150)")
        return v

    @model_validator(mode="after")
    def _every_number_has_n(self):
        def walk(d, path):
            if isinstance(d, dict):
                numeric = [k for k, v in d.items() if isinstance(v, (int, float)) and not isinstance(v, bool) and k not in ("n", "year", "version")]
                if numeric and "n" not in d and not any(k.startswith("n_") or k.endswith("_n") for k in d):
                    raise ValueError(f"numbers without an n at {path}: {numeric}")
                for k, v in d.items():
                    walk(v, f"{path}.{k}")
            elif isinstance(d, list):
                for i, v in enumerate(d):
                    walk(v, f"{path}[{i}]")
        walk(self.design_norms, "design_norms")
        walk(self.outcome_priors, "outcome_priors")
        return self


def validate_all(root: Path = ROOT) -> int:
    bad = 0
    files = sorted(root.glob("_base.yaml")) + sorted((root / "areas").glob("*.yaml")) + sorted((root / "indications").glob("*.yaml"))
    for f in files:
        try:
            Pack(**yaml.safe_load(f.read_text(encoding="utf-8")))
            print("ok   ", f.relative_to(root))
        except Exception as e:  # report every file, not just the first failure
            bad += 1
            print("FAIL ", f.relative_to(root), "->", str(e).splitlines()[0:3])
    print(f"{len(files) - bad} of {len(files)} packs valid")
    return bad


if __name__ == "__main__":
    sys.exit(1 if validate_all() else 0)
