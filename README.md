# Precedent Check

Paste a draft trial design. Get the closest past trials from ClinicalTrials.gov, plus flags where your design looks unusual. Every number comes from SQL on the registry; the AI (optional) only reads eligibility text and rewords finished sentences. Every flag shows its **n** and the **NCT IDs** behind it. Fewer than 5 comparable trials means no flags, with an explanation.

**Live demo:** https://ct-precedent-agent.vercel.app (no key needed; AI reading is off unless you add your own key under "AI key").

## Run it locally (about 2 minutes)

Needs Python 3.11+ and Node 20+.

```bash
git clone https://github.com/aivijay137-builder/CTprecedent-agent.git
cd CTprecedent-agent
pip install -r requirements.txt
npm run setup        # installs front-end packages
npm start            # builds the UI, serves everything at http://127.0.0.1:8765
```

That's it. No database, no API key, no `.env` needed: out of the box it runs on **illustrative sample data** (a banner says so). Click **Population** in the sidebar to start.

For hot-reload while developing, run `npm run dev` instead.

### Optional
| Want | Do |
|---|---|
| AI reading of eligibility text | Click **AI key** in the app and paste any OpenAI-compatible key. It is sent per request, never stored or logged. |
| Real registry data | Build the store (`python sync/build_serving.py`, large download), then set `FIXTURES=false` and `DATA_DIR=<folder>`. See `.env.example`. |

## Tests

```bash
pip install -r requirements.txt
python -m pytest backend tests sync -q     # ~10 s, expected: 121 passed, 34 skipped
npm --prefix frontend run build            # type-check + build
```

The 34 skipped tests need the full registry store; they skip themselves when it is absent. CI runs the same two commands on every push.

**What the tests cover**
- **Sync:** weekday/weekend window rule, resume after a partial download, all-or-nothing transaction, watermark.
- **Flags:** fewer than 5 comparables gives no flags; every flag carries n and NCT IDs; thresholds at the edges.
- **Criteria reading:** cutoffs found in messy text (ranges, "or", units); each cutoff links back to its source sentence.
- **Key handling (BYOK):** key never appears in logs or errors; non-https and private-IP base URLs refused; a rejected key stops further calls; no fallback to a server key.
- **Packs:** invalid pack files rejected; router picks the right area on 9 real designs; with no pack chosen, results are identical to before (golden snapshot).
- **API:** rate limit, bad input, streaming progress.

## AI reader eval (eligibility text to cutoffs)
40 real eligibility texts, 120 labelled limits. Gold set labelled by Claude, expert review pending. Pass bars were fixed before the run (`Prompt_EVALS/DECISIONS.md` D30). Details: `Prompt_EVALS/RESULTS_TABLE.md`.

| | Bar | Rule reader (free) | AI reader, prompt v7 |
|---|---|---|---|
| Precision (loose) | >= 85% | 76.8% | 85.8% (was 92.5% on v6, so treat as a range) |
| Recall (strict) | >= 50% | 24.2% | 63.3% |
| Hostile text ignored | 100% | 8/8 | 8/8 |
| Every NCT ID real, n matches (5 designs) | 100% | n/a | 306/306, all match |
| Cost per design | < $0.05 | $0 | about $0.001 |
| Slowest call | < 40 s | instant | 357 s (fails) |

Verdict: the AI reader stays off by default until the slowest-call row passes. Safety rules and their tests: `docs/safety.md`.

## Design, evidence and trust
Public registry data in, a confidential draft design in, advice out. Not HIPAA (no patient data); the exposure is draft confidentiality.

- [`SYSTEM_CARD.md`](SYSTEM_CARD.md): intended use, measured performance, failure modes, human oversight
- [`CASE_STUDY.md`](CASE_STUDY.md): the problem, the decisions, what failed
- [`docs/HLD.md`](docs/HLD.md): architecture, model choice, a design for an optional agent layer
- [`docs/agent_design.md`](docs/agent_design.md): an optional agent design, with a built and scored baseline that shows the agent is not needed yet
- [`docs/user_flow.md`](docs/user_flow.md): the screens and choices, step by step
- [`docs/safety.md`](docs/safety.md): each safety rule and the test that proves it
- [`docs/compliance.md`](docs/compliance.md): data flow and what a regulated version would need
- [`docs/risk_register.md`](docs/risk_register.md): 10 scored risks
- [`docs/metrics.md`](docs/metrics.md): metric tree from model quality to outcome, measured vs target
- [`docs/production.md`](docs/production.md): cost per run, pilot plan, monitoring
- [`Prompt_EVALS/`](Prompt_EVALS/): reader eval results and the decision log
- [`product/`](product/): early discovery and the PRD

## Known limitations (honest list)
- **Population is often "not checked".** The AI reads only a few comparables in its 40 s window; without a key the free reader checks numeric cutoffs only.
- **The Sites flag fires on most designs**, so it carries little information yet.
- **No real user has tested it yet.** Task and outcome metrics have no data (`docs/metrics.md`).
- **Risk level is unvalidated** against expert judgement.
- **Therapeutic packs are unreviewed drafts.** In tests they changed 0 to 1 comparable on three designs and no flags. They are safe, not yet shown to help.
- **Registry data is a snapshot**, refreshed daily on the hosted version; local sample data is illustrative only.
- Ranking is text-similarity based; it can miss trials that use different wording for the same condition.

## Layout
`backend/` FastAPI app, engine, tests, eval and gold sets · `docs/` design and trust docs · `product/` PRD and discovery · `Prompt_EVALS/` reader eval and decision log · `frontend/` React + Vite · `sync/` daily registry sync · `sync-cron/` scheduler · `src/` data-prep scripts and pack tools · `Dockerfile`, `railway.json` deployment
