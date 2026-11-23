# Where things stand (paused: Claude plan usage limit hit at ~15:51 IST)

Done: repo scaffold, apps.yaml (100), fetch/cache, discovery, pass-1 extraction, Loop 1 (deterministic),
Loop 2 (second agent), Loop 3 (browser + adjudicator), analyze.py, metrics.py, requirements checker.
Pilot 1-5 passes R1-R8. Discovery done for apps 1-38 (39-50 deleted: their search failed under the limit).

Resume (after the limit resets, or with ANTHROPIC_API_KEY + LLM_BACKEND=anthropic in .env):
  .venv/bin/python run.py --apps 6-100 --stage discover --workers 4
  .venv/bin/python run.py --apps 6-100 --stage extract --workers 4
  .venv/bin/python run.py --apps 1-100 --stage verify --workers 4
  .venv/bin/python run.py --stage analyze
Still to write: src/sample.py + review UI (human sheet), src/build_page.py, README.md,
docs/INTERVIEW_NOTES.md, docs/COMPOSIO_SDK_NOTES.md, .github/workflows/research.yml, deploy to GitHub Pages.
Usage-saving idea: search.brave.com HTML returns results to plain HTTP -> can replace the WebSearch
agent in discovery (biggest LLM cost); run agent 2 on haiku if sonnet budget is tight.
