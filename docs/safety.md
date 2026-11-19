# Safety rules: what the product refuses to do, and where that is enforced

| Rule | Where | Check |
|---|---|---|
| Every number and NCT ID comes from SQL on the registry, never from the model | `backend/engine.py` | `backend/eval_grounding.py` (all shown IDs exist, each `n` equals its evidence list) |
| Fewer than 5 comparables: say "insufficient", show no flags | `engine.py:550` | `test_real.py` |
| An AI-read limit must quote a sentence found in the source text, or it is marked invalid | `readers.quote_ok` | `test_phase_c.py` |
| A quoted sentence that addresses the reader ("ignore the earlier rules", `min_age`-style key names) is never a criterion, even if it is in the text | `readers.looks_injected`, prompt v7 injection rule | `test_injection.py` (model faked to obey) and `eval_reader --edge` (8 hostile cases, live model) |
| AI only rewords finished sentences; code refuses a reword that adds anything not in the evidence | `engine.py` (writer step) | `test_phase_c.py` |
| The user decides each flag (accept or defer); the AI never closes one | `main.py` decision endpoint | `test_real.py` |
| The user's API key is never stored or logged; private-IP URLs are refused | `backend/byok.py` | `test_byok.py` |
| The AI reader is off by default until every pass bar in `Prompt_EVALS/DECISIONS.md` D30 passes | `LLM_ENABLED` | `Prompt_EVALS/RESULTS_TABLE.md` |

## Known limits
- The injection filter is a word list. A reworded injection can pass it. Upgrade: a second model pass that classifies each source sentence.
- The hostile set is 8 hand-written cases, written by the same author as the filter.
- No LLM confidence threshold: the reader gives no confidence, so none is applied.
- Gold labels were made by Claude; expert review is pending.
