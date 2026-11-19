# Part 2: Workflow junctures

Evidence rules as in Part 1. Anything without a source is [HYPOTHESIS] or [ASSUMPTION]. Frustrations with a cited source are marked "Evidence". Prices quoted from your earlier research (STAT+ $39/month, DataLookout $49/month, RTTNews $99/month, BiopharmIQ $250/month for a team) are carried over and not re-verified; the DataLookout page I opened shows a free plan up to $149/month ([DataLookout via search](https://datalookout.com/free-clinical-trial-tracker)), which differs from $49, so check it.

New terms: **PDUFA date** is the date by which the FDA has promised a decision on a drug application. **Readout** is when a trial's results become known. **Primary completion date** is when the last patient has their last visit for the main question. **Amendment** is a formal change to the trial plan (the protocol).

## 2.1 The swimlane: who touches what

Legend: P = primary owner of the work at this stage, S = supporting or consuming, blank = rarely.

| Stage | Small-biotech clin ops | Small-biotech BD / CI | Pharma CI / portfolio | CRO feasibility | CRO proposal / BD | Site coordinator / director | Investor analyst | Consultant | Academic PI / disclosure |
|---|---|---|---|---|---|---|---|---|---|
| 1. Asset / indication selection | | P | P | | | | S | P | S |
| 2. Competitive landscaping | S | P | P | S | S | | P | P | |
| 3. Protocol design | P | S | S | S | | | | S | P |
| 4. Feasibility and site selection | S | | S | P | S | P | | S | |
| 5. Study start-up | P | | | S | | P | | | P |
| 6. Recruitment | P | | | S | | P | | | P |
| 7. Mid-study monitoring (own and rivals) | S | P | P | | | S | P | | |
| 8. Amendments | P | S | S | | | S | S | | P |
| 9. Readout and results | S | P | P | | | | P | S | S |
| 10. Results reporting | S | | | | | | | | P |
| 11. Licensing, M&A, investment | S | P | P | | | | P | P | |

This table is my reading of the job postings in Part 1 and is a [HYPOTHESIS] about who owns each step. The postings support: CI and portfolio owning landscapes and go/no-go ([Monte Rosa](https://jobs.recruiter.com/jobs/8449663266-associate-director-portfolio-strategy-and-analysis)), feasibility leads owning competing-trial landscape ([Allucent](https://app.joinrise.co/jobs/allucent-global-feasibility-manager-x8ov)), disclosure managers owning results posting, and analysts owning catalyst tracking ([Insight Global](https://insightglobal.com/jobs/find_a_job/job-513993)).

## 2.2 Stage by stage

For each stage the eight questions are answered for the stakeholders who matter most. "Explained answer" means: what changed, the most likely why, what it means for this reader, what to do next.

### Stage 1: Asset or indication selection

| Question | Answer |
|---|---|
| Trigger | A new target or molecule, a licensing offer, a yearly portfolio review [HYPOTHESIS] |
| Decision | Go/no-go on pursuing an indication. Output: memo and slide (Novartis posting asks for a "US go/no-go position and critical success factors", [source](https://www.novartis.com.cn/careers/career-search/job/details/req-10056011-director-portfolio-and-pipeline-strategy-immunology)) |
| How done today | Portfolio and CI staff pull competitor pipelines from paid databases and ClinicalTrials.gov, then write the memo. Time per memo: not found |
| Frustrations | No sourced evidence found. [HYPOTHESIS] Pipeline snapshots go stale and hide why rivals stopped |
| Unanswered "why" | "Which trials in this space were stopped, and was it the drug or the operations?" |
| Explained answer | One page: count of comparable trials by status, share stopped for non-science reasons, three named lessons. Format: slide or memo. Speed: days is acceptable |
| Value | Time saved only; the risk avoided is a wrong go/no-go whose cost is unquantified here. Skip pricing it |
| Willingness to pay | Enterprise databases already paid for. Evidence for a cheap tool: weak |

### Stage 2: Competitive landscaping

| Question | Answer |
|---|---|
| Trigger | Board meeting, financing, partnership talk, new indication, or a competitor news item [HYPOTHESIS] |
| Decision | A landscape deck: who is running what, at which phase, where |
| How done today | Analysts search ClinicalTrials.gov one sponsor at a time and copy into spreadsheets; or use paid platforms. Both described by a vendor with an interest in the claim ([DataLookout](https://datalookout.com/clinical-trial-landscape-analysis)). Independent time data: not found |
| Frustrations | Vendor claim only: manual checking takes 30 to 60 minutes per week per competitor ([DataLookout](https://datalookout.com/track-competitor-clinical-trials)). Treat as marketing. ClinicalTrials.gov API was changed in 2023 and 2024, breaking pipelines, per the same vendor family |
| Unanswered "why" | "Why did this rival add a cohort or move a date?" |
| Explained answer | Weekly one-pager for one indication: what moved, probable reason, who it hurts. Format: email or deck slide |
| Value | Arithmetic [ASSUMPTION]: if an analyst tracks 10 competitors at the vendor's 30 to 60 min/week each, that is 5 to 10 hours/week. At an assumed fully loaded $100/hour, that is $500 to $1,000/week. This only holds if the vendor's time claim is true |
| Willingness to pay | Strongest evidence: DataLookout lists $0 to $149/month ([search result](https://datalookout.com/free-clinical-trial-tracker)); your earlier research lists BiopharmIQ at $250/month for a team |

### Stage 3: Protocol design

| Question | Answer |
|---|---|
| Trigger | A new trial plan being drafted |
| Decision | Eligibility, endpoints, sample size, comparators |
| How done today | Clinical development and regulatory write it; look at similar trials. Citeline markets protocol design support ([Citeline-Risklick, Jan 2026](https://business.mammothtimes.com/mammothtimes/article/gnwcq-2026-1-13-citeline-risklick-partnership-creates-smarter-protocols-from-design-to-optimization)) |
| Frustrations | Evidence: 57% of 836 protocols had at least one substantial amendment, 45% of those amendments judged avoidable; median direct cost $141,000 (phase II) and $535,000 (phase III); studies with amendments ran about 3 months longer ([Tufts CSDD 2016, summarized in search](https://www.pharmavoice.com/news/2016-03-clinical-trial-amendments/613018/)) |
| Unanswered "why" | "Why did similar trials with these criteria stall or get amended?" |
| Explained answer | Table of comparable trials with eligibility strictness, enrollment outcome, and stop reasons, plus 3 flagged risks. Format: document or in Claude via MCP |
| Value | Arithmetic from sourced numbers: one avoided phase III amendment is worth up to $535,000 direct cost. Not every avoided amendment is due to a missed lookup, so the share the tool could prevent is unknown [ASSUMPTION: below 10%] |
| Willingness to pay | Higher than other stages because dollars are large, but the buyer is bigger sponsors; small-sponsor evidence: not found |

### Stage 4: Feasibility and site selection

| Question | Answer |
|---|---|
| Trigger | An RFP, or a sponsor choosing countries and sites. CRO proposals typically assemble landscape and feasibility inside about 10 working days ([PharmaLive](https://www.pharmalive.com/efficiencies-and-adjacencies-important-considerations-for-effective-clinical-cro-partnerships/)) |
| Decision | Which countries and sites, and how fast enrollment will go. Output: site list, enrollment scenarios, country scorecard (ICON posting) |
| How done today | Feasibility leads use Citeline, IQVIA, TriNetX, ClinicalTrials.gov and send questionnaires to sites ([ICON](https://careers-iconplc.icims.com/jobs/122083/feasibility-lead/job)) |
| Frustrations | Evidence: 49% of sites say feasibility survey burden increased over five years ([Advarra 2023 via search](https://advarra.com/?p=60891)). Sponsors and sites distrust the questionnaire ([Inato study](https://www.outsourcing-pharma.com/Article/2024/05/20/study-digs-deep-on-clinical-trials-to-find-out-what-sponsors-want)). Site performance is uneven: about 11% of sites enrolled no patients and about 37% under-enrolled in a Tufts 2013 analysis of 150+ studies ([Fierce Biotech via search](https://www.fiercebiotech.com/r-d/pharma-fumbles-recruitment-game-as-clinical-trials-miss-goals)) |
| Unanswered "why" | "Why do trials in this indication stall at certain sites, and who else is competing for the same patients there?" |
| Explained answer | Per candidate site: how many competing trials are recruiting for the same condition nearby, what happened to past trials at that site. Format: spreadsheet or in-chat table. Speed: hours |
| Value | If 11% of selected sites enroll zero patients, then for a 50-site trial about 5 sites are dead weight. Cost per dead site: not found [ASSUMPTION needed] |
| Willingness to pay | Feasibility vendors are already paid by CROs (ICON posting). Price: not found |

### Stage 5: Study start-up

| Question | Answer |
|---|---|
| Trigger | A sponsor awards the study; sites are being activated |
| Decision | Which sites to activate first, contracts and approvals |
| How done today | Start-up specialists prepare regulatory submissions and site documents ([ICON start-up posting](https://careers.iconplc.com/job/study-start-up-feasibility-specialist-home-based-us-in-united-states-jid-38489)) |
| Frustrations | Not specific to trial-change tracking. [HYPOTHESIS] Little value from CT.gov data here |
| Unanswered "why" | Mostly operational, not answerable from CT.gov |
| Explained answer | Not a priority stage for this product |
| Value / WTP | Skip |

### Stage 6: Recruitment

| Question | Answer |
|---|---|
| Trigger | Enrollment behind plan |
| Decision | Add sites, relax criteria, extend timeline |
| How done today | Sponsors and CROs add sites, run outreach; Tufts reports that reaching enrollment targets typically meant nearly doubling original timelines in the 2013 study, while a 2020 Tufts update found enrollment timelines equal to or shorter than planned in 77% of studies ([Tufts via search](https://www.fiercebiotech.com/biotech/new-research-from-tufts-center-for-study-of-drug-development-characterizes-effectiveness)). The two figures measure different things |
| Frustrations | Evidence in the Tufts figures above. Direct frustration quotes: not found. Where to find: ACRP and SCRS conference talks |
| Unanswered "why" | "Is a new competing trial pulling patients from my sites?" |
| Explained answer | Alert: "Two new trials opened within 50 miles of three of your sites, both targeting the same condition" |
| Value | Faster response to competing recruitment. Arithmetic: not computable without per-day trial delay cost [ASSUMPTION needed] |
| Willingness to pay | Not found |

### Stage 7: Mid-study monitoring (own trials and rivals')

| Question | Answer |
|---|---|
| Trigger | A rival's status, date, enrollment or site list changes |
| Decision | React or ignore. Brief the leadership team |
| How done today | CI analysts monitor with ClinicalTrials.gov and paid databases ([Novartis posting](https://www.novartis.com/careers/career-search/job/details/req-10084887-senior-analyst-enterprise-competitive-intelligence)). Small teams: email alerts from ClinicalTrials.gov or DataLookout |
| Frustrations | Evidence: DataLookout positions itself against ClinicalTrials.gov's built-in notifications, which it says have no phase or sponsor filtering (vendor claim). Registry data can lag reality: readout timing from ClinicalTrials.gov should be checked against company disclosures (noted in an investor-tool search result) |
| Unanswered "why" | "Why did they cut enrollment, slip the date, or drop an arm?" This is the core product question. DataLookout shows what changed, not why (your earlier research) |
| Explained answer | Alert with what changed, a ranked list of likely reasons with confidence, what it means for the reader, and a next step. Format: email, Slack, in-chat |
| Value | Arithmetic [ASSUMPTION]: one early signal about a rival that shifts a financing or partnership date is worth more than a year of the subscription, but I have no sourced case. Do not price on this until interviews supply an example |
| Willingness to pay | Closest paid analogues: DataLookout up to $149/month, BiopharmIQ $250/month (your research), BioPharmCatalyst Trial Insights (price: not found) |

### Stage 8: Amendments

| Question | Answer |
|---|---|
| Trigger | A record's eligibility, endpoints or arms change on ClinicalTrials.gov |
| Decision | Own team: whether to amend. Rival's team: what their amendment signals |
| How done today | Own trials via regulatory and clinical ops. Rivals via CI |
| Frustrations | Evidence: amendments are common (57%) and expensive (see Stage 3). ClinicalTrials.gov keeps record history but this local snapshot does not (single snapshot, no change history) |
| Unanswered "why" | "Why did the sponsor loosen eligibility? Slow enrollment? Safety? A new FDA comment?" |
| Explained answer | Diff of the field plus a classification of the probable reason using the trial's own enrollment trend and the sponsor's recent disclosures |
| Value / WTP | As Stage 3 and 7 |

### Stage 9: Readout and results

| Question | Answer |
|---|---|
| Trigger | Primary completion date passes; company press release |
| Decision | Investors: buy, sell, hold. Pharma CI: update the landscape |
| How done today | Analysts track catalysts with models and filings ([Insight Global posting](https://insightglobal.com/jobs/find_a_job/job-513993)). Tools such as BioPharmCatalyst offer trial insight ([release](https://www.businesswire.com/news/home/20240711495417/en)) |
| Frustrations | Evidence: registry timing can lag company disclosures, so readout dates need cross-checking |
| Unanswered "why" | "Why did the date slip, and is a slip a bad sign?" |
| Explained answer | Date-slip alert with sponsor history of slips and the rate at which similar slips preceded termination (computed in Part 3) |
| Value | Investors: a mispriced position. Arithmetic needs a position size; not computable without a case [ASSUMPTION needed] |
| Willingness to pay | Retail and small-fund investors already pay for catalyst tools (BioPharmCatalyst; price not found) |

### Stage 10: Results reporting

| Question | Answer |
|---|---|
| Trigger | A results deadline approaches. The rule is 12 months after primary completion for applicable trials |
| Decision | File results in the required format |
| How done today | Disclosure staff track due dates and remind PIs ([university posting seen in search](https://www.ziprecruiter.com/Jobs/Clinical-Trial-Transparency-Manager)) |
| Frustrations | Evidence: 40.9% of 4,209 due trials reported on time; academic and government sponsors worst (DeVito, Lancet 2020, via [TCTMD](https://www.tctmd.com/news/most-clinical-trial-sponsors-fail-report-data-mandated-fda)). Enforcement letters in March 2026 per a secondary source, unverified |
| Unanswered "why" | Not a "why" problem; a "when and how" problem |
| Explained answer | Due-date tracker plus a draft results record. Format: spreadsheet and draft file |
| Value | Avoid civil monetary penalties. Penalty size: not found; check FDAAA 801 text |
| Willingness to pay | Universities pay for compliance staff; tool price: not found |

### Stage 11: Licensing, M&A and investment

| Question | Answer |
|---|---|
| Trigger | A deal opportunity or diligence request |
| Decision | Value the asset; flag red flags |
| How done today | BD and corporate development with consultants; VC associates do scientific and clinical diligence ([General Atlantic](https://mozibox.com/jobs/345180), [Aditum Bio](https://job-boards.greenhouse.io/aditumbio/jobs/4421669005)) |
| Frustrations | Not found with direct quotes. Where to find: BD interviews |
| Unanswered "why" | "Is this program quietly being wound down?" |
| Explained answer | Diligence pack on one asset: its trial history, every date slip, enrollment changes, stop reasons for sister trials |
| Value | Avoid a bad deal. Size: not computable without a case |
| Willingness to pay | Diligence is episodic and high stakes, so price tolerance is probably higher per use but lower in frequency [HYPOTHESIS] |

## 2.3 Ranking of junctures

Scoring: each factor 1 (low) to 5 (high). Score = frequency x pain x willingness to pay x "can CT.gov answer the why". The scores are my judgement [HYPOTHESIS] except the last factor, which is anchored on Part 3: 60% of stop reasons are stated in the record, 16 to 20% need outside sources, 20 to 24% stay unexplained, and anything that needs change history needs the weekly snapshots described in Part 3, section 3.0. Re-score after interviews.

| Rank | Juncture | Frequency | Pain | Willingness to pay | CT.gov can answer the why | Score | Reason for the scores |
|---|---|---|---|---|---|---|---|
| 1 | 7. Mid-study monitoring of rivals | 5 | 4 | 4 | 3 | 240 | Weekly habit. Paid analogues exist (DataLookout up to $149/mo, BiopharmIQ $250/mo). 60% of stops carry a stated reason, but timing needs history |
| 2 | 2. Competitive landscaping | 4 | 3 | 4 | 4 | 192 | Board and financing cycles. Data is in the record, no history needed |
| 3 | 9. Readout and date slips (investors) | 4 | 3 | 4 | 3 | 144 | Catalyst tools are already bought. Slip needs history, dates lag company news |
| 3 | 4. Feasibility and site selection | 3 | 4 | 3 | 4 | 144 | Sites and competing trials are in the record. Buyers are CRO feasibility leads who already pay data vendors |
| 5 | 3. Protocol design | 2 | 5 | 3 | 4 | 120 | Big dollars (Tufts amendment costs) but rare event per buyer. Eligibility, outcomes and stop reasons are all in the record |
| 5 | 10. Results reporting | 3 | 4 | 2 | 5 | 120 | Fully answerable, but a "when and how" problem, not "why", and buyers are budget-poor academics |
| 7 | 11. Licensing, M&A, investment | 2 | 4 | 3 | 3 | 72 | Episodic, high stakes. Strong only with history plus outside sources |
| 8 | 6. Recruitment | 3 | 3 | 2 | 3 | 54 | Own-trial problem. Tools sold to sponsors already |
| 9 | 8. Amendments | 3 | 3 | 2 | 2 | 36 | Requires history; the reason lives in the sponsor's files |
| 9 | 1. Asset and indication selection | 2 | 3 | 2 | 3 | 36 | Enterprise tools already own this |
| n/a | 5. Study start-up | | | | | | Operational, not a CT.gov problem. Skipped |

Top five for Part 4: stages 7, 2, 9, 4, 3. Stage 10 is the first runner-up and is used in Part 5 because it is the most buildable.
