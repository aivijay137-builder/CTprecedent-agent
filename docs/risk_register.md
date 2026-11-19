# Risk register

Scores are 1 (low) to 3 (high). Score = likelihood (L) x impact (I). Owner is the role that would act, since this is a one-person project.

| # | Risk | L | I | Score | Mitigation in place | Gap, next step | Owner |
|---|---|---|---|---|---|---|---|
| R01 | **Invented NCT ID or number** shown as fact | 1 | 3 | 3 | SQL produces every number and ID; AI only rewords; `eval_grounding.py` (5 designs, 306 IDs, none unknown) | Not run in CI yet; sample is 5 designs | Engineer |
| R02 | **Hostile text in eligibility criteria** changes a limit | 2 | 3 | 6 | Prompt v7 rule, `looks_injected`, quote check; 8/8 hostile cases, `test_injection.py` | Word list only; a reworded attack can pass. Add a model pass that classifies each source sentence | Engineer |
| R03 | **AI misreads a limit** (wrong value or a skipped one) | 2 | 2 | 4 | Source quote must exist; precision 85.8% and recall 63.3% on the gold set; AI reader off by default | Precision is a single run; gold set labelled by Claude, expert review pending | PM |
| R04 | **Stale data** | 2 | 2 | 4 | Daily sync; footer shows the last good sync date | No alert if the sync cron fails for days | Engineer |
| R05 | **Confidential draft design exposed** (stored in `app.db`, shared link, sent to an LLM vendor) | 2 | 3 | 6 | Key never stored; AI off unless the user opts in | Drafts kept with no expiry or login. Add a retention limit and delete; say so in the UI | PM |
| R06 | **Over-trust:** a user treats "no flag" as "design is fine" | 2 | 3 | 6 | "No flags is a finding, not an error" message; under 5 comparables says insufficient; accept or defer is the user's call | No evidence yet of how people read it; test with 3 real users | PM |
| R07 | **API key leak** | 1 | 3 | 3 | Never stored or logged; scrubbed from errors; `test_byok.py` | Browser-side exposure is the user's to manage | Engineer |
| R08 | **Bias by therapeutic area:** rules and packs tuned on COPD work worse elsewhere | 3 | 2 | 6 | Packs labelled draft and unreviewed; the "did not help" result is published | Gold set is mixed-condition but small (40 texts); add areas before claiming generality | PM |
| R09 | **Provider outage or rate limit** stalls a run | 3 | 1 | 3 | Fallback models, free-reader fallback, per-run time budget, `LLM_MAX_WAIT_S` | Two fallback models return 404 on the current account (D36) | Engineer |
| R10 | **Cost overrun** from many AI calls | 1 | 2 | 2 | Daily cap $0.50, 60 calls per run, answer cache, per-visitor rate limit | Caps are per instance, not per user | Engineer |

Highest score is 6: R02, R05, R06, R08. Act on R02 and R05 before any pilot.
