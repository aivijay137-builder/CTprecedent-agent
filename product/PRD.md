# Respiratory Trial Insights Platform — Product Requirements Document

**Date:** 2026-11-06
**Author:** Product Team
**Status:** Draft
**Version:** 1.0

Basis: Part 1 (stakeholders), Part 5 (thin slices), Part 7 (respiratory scope). Lung cancer is out of scope. Numbers come from those parts; prices and targets marked [HYPOTHESIS] are untested.

---

## 1. Executive Summary

### Problem Statement
Respiratory trial data on ClinicalTrials.gov is public but unusable for decisions. Stop reasons, site overlap, eligibility cutoffs, date drift and posted results are buried in free text and raw fields. Small sponsors, CROs, sites, investors, consultants and academic offices each need a different narrow answer, and today get it from enterprise tools (Citeline, Trialtrove) priced for large pharma, or from manual searches.

### Proposed Solution
One common respiratory data layer (the Part 7 Brief scope, 44,577 studies: core respiratory disease plus respiratory infections) with role-specific value layers built one stakeholder at a time. Phase 2 adds a RAG query layer: plain-language questions answered from SQL plus text retrieval, with every claim cited to an NCT record.

### Business Impact
- Gives small sponsors and consultants a self-serve alternative to enterprise databases [HYPOTHESIS: price points $49 to $250/month, anchored on DataLookout, RTTNews, BiopharmIQ].
- Avoids costly protocol mistakes: a Phase III amendment costs up to $535,000 and 45% are judged avoidable (Tufts 2016, cited in Part 5).
- Builds a proprietary weekly snapshot archive; history cannot be rebuilt later, so the data advantage grows with time.

### Key Milestones
| Milestone | Target |
|---|---|
| Common data layer live (Layer 0) | Week 4 |
| First value layer (small biotech) in pilot | Week 8 |
| Layers 2 to 4 (CRO, consultant, academic) | Week 16 |
| Layers 5 to 7 (pharma CI, investor, site) | Week 28 |
| RAG query layer (Phase 2) beta | Week 36 |

### Success Metrics
| Metric | Current | Target |
|---|---|---|
| Pilot users per layer who say output changed a decision | 0 | 3 to 5 per role [HYPOTHESIS] |
| Weekly snapshots archived | 0 | 1 per week, unbroken, from Week 1 |
| Insights traceable to a source record | n/a | 100% |
| RAG answers matching dashboard counts (benchmark set) | n/a | 95%+ |
| Paying users after Layer 1 pilot | 0 | 5 [HYPOTHESIS] |

---

## 2. Problem Definition

### 2.1 Customer Problem
- **Who:** Seven groups from Part 1: small biotech, mid/large pharma, CRO, trial site, investor, consultant, academic sponsor.
- **What:** They cannot cheaply see why trials stop, who competes for the same patients, how strict comparable trials were, or when dates move.
- **When:** At protocol design, feasibility, bid defense, board prep, catalyst watching, and results deadlines.
- **Where:** Spreadsheets, ClinicalTrials.gov search, enterprise databases.
- **Why:** The registry has no change history or explanations; the useful signals are free text and scattered fields.
- **Impact:** 33.7% of stopped non-cancer trials stopped for enrollment (Part 3); only 40.9% of trials due to report did so on time (DeVito 2020).

### 2.2 Market Opportunity
- **Market size:** Not sized. No TAM/SAM/SOM was produced in Parts 1 to 9; do not quote one. Proxy: 934 industry sponsors started interventional non-cancer respiratory/infectious trials since 2023, 515 of them with 5 or fewer trials (Part 5 self-serve pool).
- **Current solutions:** Citeline/Trialtrove (price unpublished), IQVIA, TriNetX, DataLookout, BioPharmCatalyst, manual CT.gov.
- **Gap:** Explanations (the "why"), small-team pricing, and role-specific outputs.
- **Why now:** Registry data is complete and free; LLMs make free-text extraction cheap enough for a one-person build.

### 2.3 Business Case
- **Revenue potential:** Unproven. Willingness to pay is "not found" for most roles (Part 5).
- **Strategic alignment:** Proprietary snapshot history plus classified stop reasons are the defensible assets.
- **Risk of inaction:** Every week without snapshots is history lost permanently.

---

## 3. Solution Overview

### 3.1 What We're Building
Three layers:
- **Layer 0, common data layer:** scope table, clean entities, derived fields, weekly snapshots, entity pages (trial, sponsor, drug, condition, site), API.
- **Layer 1, stakeholder value layers:** built one at a time, each only adding views and report templates.
- **Layer 2, RAG query layer (Phase 2):** SQL for counts and filters, vector search over free text, answers with NCT citations.

### 3.2 In Scope
| Feature | Priority | Description |
|---|---|---|
| Scope table (Part 7 rules, lung cancer excluded) | P0 | 44,577 studies with category flags and primary category |
| Entity cleaning | P0 | Sponsor parent merge, facility and city normalisation, drug names |
| Weekly snapshot archive | P0 | Full pull every week; enables diffs |
| Derived fields | P0 | Stop cause, date drift, result-posted flag, parsed eligibility cutoffs |
| Entity pages and API | P0 | Trial, sponsor, drug, condition, site |
| Layer: small biotech | P0 | "Why did similar trials fail" report |
| Layer: CRO | P1 | City crowding map |
| Layer: consultant | P1 | Weekly indication brief |
| Layer: academic | P1 | Results-due tracker |
| Layer: pharma CI | P1 | Explained stop and exit alerts (needs snapshots) |
| Layer: investor | P2 | Catalyst slip tracker (needs snapshots) |
| Layer: site | P2 | Study fit note |
| RAG query layer | P1 (Phase 2) | Natural-language questions with cited answers |

### 3.3 Out of Scope
- Lung cancer and mesothelioma (separate market, per decision).
- Smoking and tobacco studies (Part 7 adjacent group).
- Predictive models (date or stop prediction) until base rates exist from snapshots.
- Patient-facing features, EHR integration, non-ClinicalTrials.gov registries (EU CTIS, WHO ICTRP) in v1.

### 3.4 MVP Definition
- **Core features:** Layer 0 plus the small-biotech report on 3 conditions (COPD, asthma, bronchiectasis).
- **Success criteria:** 3 pilot users in the role say the report would have changed a decision.
- **MVP target:** Week 8.
- **Learning goals:** Will users trust auto-selected comparables? Does stop-cause classification hold on the new scope?

---

## 4. User Stories & Requirements

### 4.1 User Stories

**Small biotech.** As a head of clinical operations, I want to paste my draft design and see comparable trials, how they ended and three flagged risks, so that I fix problems before submitting.
- [ ] 10 to 30 comparables listed with outcome and stop reason
- [ ] Each risk links to NCT records
- [ ] "Not found" shown where the registry is silent

**CRO.** As a feasibility lead, I want the number of recruiting trials for a condition per city, with sponsors and eligibility overlap, so that I can shortlist sites and countries.
- [ ] Crowding score per city
- [ ] Facility names merged across spellings
- [ ] Export to spreadsheet

**Consultant.** As a strategy consultant, I want a weekly indication brief as a slide and text, so that I can drop it into a client deck.
- [ ] New trials, stops by cause, phase mix, sponsor moves
- [ ] Slide image plus editable text

**Academic.** As a results disclosure manager, I want my institution's completed trials with results due and not posted, so that I can chase PIs.
- [ ] 12-month deadline computed from primary completion date
- [ ] Candidates flagged for applicability; user confirms

**Pharma CI.** As a CI analyst, I want an alert when a rival trial stops, slips or shrinks, with the reason and sources, so that I brief leaders quickly.
- [ ] Watchlist by sponsor, drug, condition
- [ ] Reason quoted from the record, with source tier label

**Investor.** As a biotech fund analyst, I want to see when a primary completion date moved and the sponsor's slip history, so that I time catalysts.

**Site.** As a research coordinator, I want a one-page note on an incoming trial: local competing trials, comparable outcomes, questions to ask the sponsor.

**RAG (Phase 2).** As any user, I want to ask a plain-language question and get an answer with NCT citations, so that I don't need to learn filters.
- [ ] Counts match the dashboards
- [ ] Every claim cites a record; unanswerable questions say so

### 4.2 Functional Requirements
| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR1 | Build and version the Part 7 scope table; exclude lung cancer | P0 | Rule-based; precision unmeasured, add a measured audit |
| FR2 | Count multi-condition studies once for totals, and show mentions separately | P0 | Prevents dashboard/RAG mismatch |
| FR3 | Run full CT.gov pull weekly and store each dated snapshot | P0 | Needed for diffs; start Week 1 |
| FR4 | Classify stop reasons into causes (enrollment, business, safety, funding, other) | P0 | Reuse `p3_classify.py`; re-run on new scope (Part 7 note) |
| FR5 | Merge sponsor names to parent company | P0 | Known split, e.g. Merck variants |
| FR6 | Normalise facility and city names | P0 | Hardest matching problem |
| FR7 | Parse eligibility text into structured cutoffs (age, lung function) | P1 | Start with 3 conditions; validate by hand |
| FR8 | Compute date drift and stale-live flag | P1 | Live trials past primary completion date |
| FR9 | Entity pages with search and filters | P0 | |
| FR10 | Watchlists and email alerts | P1 | Layer 5 |
| FR11 | Export to CSV and slide image | P1 | Consultants and CROs |
| FR12 | Every insight shows source records and confidence or "not found" | P0 | Registry lag risk |
| FR13 | RAG: route a question to SQL, vector search or both | P1 | Phase 2 |
| FR14 | RAG: answers cite NCT IDs and refuse when the record is silent | P1 | Phase 2 |

### 4.3 Non-Functional Requirements
- **Performance:** Entity page loads under 2 seconds at P95 [HYPOTHESIS]; RAG answer under 15 seconds.
- **Scalability:** 44,577 studies now; tolerate full registry (609,811) without redesign.
- **Security:** User accounts, per-user watchlists; no patient data (registry is aggregate public data).
- **Reliability:** Snapshot job monitored; a missed week is alerted, since gaps are unrecoverable.
- **Usability:** Works on desktop and mobile web; plain-language labels, with the Part 1 glossary terms explained inline.
- **Compliance:** Respect ClinicalTrials.gov terms of use; display data-as-of date on every page.

---

## 5. Go-to-Market Strategy

### Launch Plan
- **Beta:** Concierge pilots, 3 customers per layer, hand-checked reports (Part 5 next steps).
- **Full launch:** Per layer after pilot proof; no big-bang launch.
- **Channels:** LinkedIn outreach to titles from Part 1; conference lists (ATS, ERS, SCOPE, DIA, SCRS) per Part 5.
- **Support:** Short docs, sample outputs, glossary.

### Pricing
All [HYPOTHESIS], from Part 5 anchors (STAT+ $39, DataLookout $49, RTTNews $99, BiopharmIQ $250/team): alerts $49 to $250/month; protocol report $300 to $1,000 each; feasibility pack $300 to $1,000 or $250/month; site tool $29 to $99/month; institution tracker $50 to $200/month. Test in interviews before fixing.

---

## 6. Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Registry lag and wrong records mislead users | High | High | Show data date, confidence, "not found"; link every claim |
| Facility/sponsor name matching errors | High | Med | Manual review of top sponsors and sites; measure match rate |
| Category rules wrong (only spot-checked) | Med | High | Audit a random sample, record precision per category |
| Willingness to pay unproven, weakest for sites | High | High | Concierge pilots and paid-intent test before building each layer |
| No history until snapshots accumulate | Certain | Med | Start snapshots now; sequence history-dependent layers last |
| RAG hallucinates or gives counts differing from dashboards | Med | High | Citation-required answers, shared definitions, benchmark question set |
| Eligibility parsing errors | Med | Med | Hand-check sample; show parsed value beside original text |

---

## 7. Timeline & Milestones

| Milestone | Date | Deliverables | Success Criteria |
|---|---|---|---|
| Snapshots start | Week 1 | Weekly pull job running | First two snapshots stored |
| Layer 0 | Week 4 | Scope table, entity cleaning, derived fields, entity pages | Counts match Part 7 totals (44,577 less lung cancer overlap) |
| Layer 1a: small biotech | Week 8 | Failure report on 3 conditions | 3 pilot users: changed a decision |
| Layers 1b to 1d | Week 16 | CRO map, consultant brief, academic tracker | 3 pilots each |
| Layers 1e to 1g | Week 28 | Alerts, slip tracker, site note | Enough snapshot history (about 8+ weeks) for diffs |
| Phase 2: RAG | Week 36 | Query layer over all views | 95%+ match on benchmark set |

Timeline assumes one person using an LLM, per Part 5, and is aggressive if interviews run in parallel.

---

## 8. Team & Resources

| Role | Allocation |
|---|---|
| Product / research (interviews, pilots) | 1 person, part-time |
| Engineering (data layer, views, RAG) | 1 person, full-time with LLM tools |
| Design | Contract, as needed |
| QA / data audit | Founder plus pilot users |

**Budget:** Not estimated. Costs are mainly LLM calls, hosting and storage for weekly snapshots; size once Layer 0 is built.

---

## 9. Open Questions
1. Internal tool or product to sell? This decides accounts, billing and polish.
2. What is the measured precision of the Part 7 category rules?
3. Which layer gets the first paying pilot, and at what price?
4. Does ClinicalTrials.gov terms of use allow the planned commercial redistribution of derived data?
5. Part 1 lists 7 stakeholder groups (not 6); confirm all 7 are in scope or drop one.
6. Include EU and WHO registries later, and when?

## 10. Assumptions Made
- Format chosen: Full PRD, because it is a new multi-stakeholder product.
- Scope is Part 7 Brief scope with lung cancer removed; all other Part 7 definitions unchanged.
- Build order follows the agreed layer plan: biotech, CRO, consultant, academic, pharma CI, investor, site.
- One-person build speed from Part 5; timelines are estimates, not commitments.
- All prices, target metrics and performance numbers marked [HYPOTHESIS] are placeholders to validate.
- No market size, revenue or budget figures exist in the earlier parts, so none are given.
