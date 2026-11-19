# From prototype to pilot

Numbers come from `llm_log` in `app.db` (Groq, `openai/gpt-oss-120b`, free tier) unless marked **estimate**. Real paid prices will differ; re-measure on the model you deploy.

## Cost per task (AI reader on)
| Call | Measured avg tokens (in / out) | Measured cost per call |
|---|---|---|
| Read the user's criteria (`parse_design`) | 1,378 / 924 | about $0.0007 |
| Read a comparable's eligibility text (`extract_targets`) | 2,305 / 2,152 | about $0.0016 |
| Reword a flag (`write_flags`) | 467 / 494 | about $0.0004 |

One check is 1 criteria read, up to 60 comparable reads (the per-run cap; fewer when the cache has them), and a few rewords. **Estimate: about $0.005 typical, $0.10 worst case.** With the AI off: $0.

| Volume | Cost, AI reader on (estimate, typical to worst case) | Notes |
|---|---|---|
| 100 checks | $0.50 to $10 | Worst case exceeds the $0.50 daily cap |
| 10,000 checks | $50 to $1,000 | The cache cuts repeat comparables; worst case assumes none |
| 1,000,000 checks | $5k to $100k | Needs a cheaper model for comparable reads, or pre-parsing the whole registry once (already done for COPD) |

The free-tier limits are the real ceiling today: 63 rate-limit errors across about 215 calls, and some calls waited 331 to 643 s.

## Pilot plan (suggested)
| | |
|---|---|
| Who | 3 to 5 feasibility or design leads, one therapeutic area (respiratory) |
| How long | 2 weeks, each running their real drafts or a past protocol |
| Before | Close R02 and R05 in `risk_register.md`: retention limit, delete, a visible note that drafts are stored |
| Measure | Time from paste to decision; flags accepted vs deferred; runs ending "insufficient"; one question per user: "did it tell you something you did not know?" |
| Success | At least 3 of 5 users find one useful flag; no flag with a wrong NCT ID or n |
| Stop | Any wrong NCT ID or n; any report that a draft was seen by someone else |

## Monitoring
| What | How | Alert when |
|---|---|---|
| Data freshness | `/api/health` last sync date | Older than 3 days |
| AI cost and errors | `llm_log` (cost, status, seconds) | Daily spend near the cap; error share over 20% |
| Slow calls | `llm_log.seconds` | Any call over 60 s |
| Grounding | `python -m backend.eval_grounding` on a schedule | Any unknown ID |
| Reader quality | `python -m backend.eval_reader --llm` before any prompt or model change | Any pass bar in D30 fails |
| Usage | `usage` table now; a `usage_events` table is Phase C | n/a |

## Failure modes
| Failure | What the user sees | What happens |
|---|---|---|
| Registry being synced | "Being updated, try again in a minute" | Run refused, nothing wrong shown |
| LLM down, rate-limited or key rejected | A message; the check used the free reader | Fallback models, then the rule reader |
| AI returns invalid JSON or a quote not in the text | That limit is dropped or marked invalid | Never shown as a fact |
| Fewer than 5 comparables | "Insufficient", no flags | By design |
| Daily AI budget used up | AI off until UTC midnight | Free reader still works |
| Sync cron silently fails | Footer date goes stale | Gap: no alert yet (R04) |
