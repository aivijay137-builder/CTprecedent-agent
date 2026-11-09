# Protocol Precedent Agent (Step 1)
Run from this folder. `pip install -r requirements.txt` first; fill `.env` (LLM_BASE_URL, LLM_API_KEY, LLM_MODEL).

- `python src/adapters.py`   prints 3 test briefs (NCT -> Design Brief)
- `python src/build_copd.py` builds copd_trials / copd_excluded in precedent.duckdb, prints summary, writes data/copd_sample.csv
- `python -m pytest tests`   runs tests

Files: src/brief.py = schema; src/adapters.py = NCT adapter; src/build_copd.py = COPD table; src/llm.py = the single LLM entry point (any OpenAI-compatible provider); src/extract.py = Step 2 (not built yet).
