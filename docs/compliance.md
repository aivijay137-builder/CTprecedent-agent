# Trust and compliance

**What this is:** a design-support tool. It reads public ClinicalTrials.gov data and a sponsor's *draft* trial design. It makes no clinical decision, holds no patient data, and nothing in it is validated for GxP use. This page says what data goes where and what a regulated version would still need. It is not legal advice.

**Not HIPAA.** No patient records enter the system. The real exposure is **confidentiality of an unpublished protocol design**, plus audit trail and validation if a sponsor adopted it.

## Data flow
| Data | Comes from | Where it goes | Stored? | Notes |
|---|---|---|---|---|
| Trial registry (about 610k studies) | ClinicalTrials.gov, public | DuckDB on the server volume | Yes | Public data. Daily sync. |
| The user's draft design (condition, phase, endpoint, criteria text, countries) | The user | API, then `app.db` `runs.result` and `packages.snapshot` | **Yes, as JSON, no expiry** | Confidential to the sponsor. See R05 in `risk_register.md`. |
| The same criteria text and comparable trials' eligibility text | The user, the registry | **The LLM vendor**, only if the user adds their own key | Answers cached in `app.db` (`llm_cache`, `cutoff_cache`) | With no key, nothing leaves the server. |
| User's API key | The user, per request | Held in memory for the request, sent to the vendor | **No, never stored or logged** (`byok.py`, `test_byok.py`) | Private-IP URLs refused. |
| LLM call log | The system | `app.db` `llm_log` | Yes: task, model, tokens, cost, seconds, error | No prompt text. |
| Flag decisions (accept, defer, reviewer notes) | The user, a reviewer | `app.db` `decisions` | Yes: time, role, flag, action, reason | The audit trail. |
| Anonymous usage count | The request | `app.db` `usage` | Yes: day, hashed visitor, count | IP is hashed, never stored. |

## What the product already does for trust
- Every number and NCT ID comes from SQL, never from the model (`docs/safety.md`).
- Fewer than 5 comparables: no flags, the reason is shown.
- AI output must quote a sentence found in the source text; hostile text cannot become a limit (`test_injection.py`).
- Daily and per-run AI cost caps; a run stops starting new calls after 40 s.
- The AI reader is off on the public site unless a user brings a key.

## What a regulated version would still need
| Area | Today | Needed |
|---|---|---|
| 21 CFR Part 11 audit trail | `decisions` has time, role, action, reason | Real user identity (role is a label now), tamper-evident storage, no deletes |
| Access control | None: anyone with the link can run and read a run | Sign-in, per-sponsor separation |
| Confidentiality | Drafts stored in clear in `app.db`, no expiry | Retention limit, delete on request, encryption at rest, a vendor agreement or a self-hosted model so drafts never go to a third party |
| GxP validation | Test suite (CI) and eval records | Intended-use statement, risk-based validation plan, change control for prompt and rule versions |
| Data integrity | Registry synced daily, all-or-nothing | Sync audit, version stamp on every run (partly there: prompt version, data date) |
| Model change control | Prompt versions logged (v5 to v7) | Re-run the eval before any model or prompt change goes live |

## Plain statement for a reviewer
Public data in, a confidential draft in, advice out. The draft is stored unencrypted and is sent to an LLM vendor only if the user opts in with their own key. Treat any draft you would not paste into a public tool as out of scope until the items above are done.
