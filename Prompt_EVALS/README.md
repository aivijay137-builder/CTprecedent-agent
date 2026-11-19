# EVALS

The record of how the therapeutic packs, the router and the "with or without pack" comparison are built and tested.

| File or folder | What it holds |
|---|---|
| `DECISIONS.md` | Every decision, in order: who decided, why, what else was considered, the run that backs it |
| `RUNS.md` | Every test or eval run: what it checks, the command, pass or fail, link to the full output |
| `runs/` | Full output of each run (`<date>_R<number>_<name>.txt`) |
| `EvalSummary.md` | **Start here.** Every step done so far, explained in plain English, with what each run showed |
| `RESULTS.md` | Plain-English summary of what the results mean so far (updated as runs are added) |
| `golden/` | Copy of the golden regression snapshot (also at `backend/golden/golden_base_runs.json`) |
| `scripts/` | The scripts behind the runs |
| `record.py` | Runs a command and records it: `python Prompt_EVALS/record.py <name> "<what it checks>" -- <command>` |

## Two different kinds of check (do not mix them up)
| | Regression check | Quality eval |
|---|---|---|
| Question | Did the base (prompt-only) results change? | Do packs make the results better? |
| Needs a person | No | Yes (hand-graded comparables, known stop reasons) |
| Status | Golden snapshot taken and repeatable (R06); the "packs off is unchanged" test comes with the build | **Not built**: the quality eval (not built) |

Until the quality eval exists, the compare view shows **what changed**, not **whether it is better**.

This folder is local only. Say if you want it added to the GitHub repo.
