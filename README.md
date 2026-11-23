# Composio toolkit research agent: 100 apps

An agent that researches whether Composio could build an agent toolkit for an app: auth methods,
self-serve vs gated access, API surface, existing MCP servers, buildability verdict and main blocker. Every
answer comes with a docs URL and a verbatim quote. The dataset then goes through three automated
verification loops and a human-checked sample.

- **Live case study:** https://karanlokhande29.github.io/composio-toolkit-research/
- **Machine-readable:** [`site/results.json`](site/results.json) · [`site/patterns.json`](site/patterns.json) · [`site/llms.txt`](site/llms.txt)
- **Runnable trigger:** Actions → **research** → Run workflow (`verify-only` needs no keys)

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium        # for Loop 3 (headless browser)
cp .env.example .env                         # then edit .env
```

`.env` (see [`.env.example`](.env.example)):
- `LLM_BACKEND=claude_cli` uses your local `claude` login (Claude Code CLI) and needs no key.
  `LLM_BACKEND=anthropic` with `ANTHROPIC_API_KEY` uses the Anthropic API instead.
- `PASS1_MODEL` / `SECOND_MODEL` / `SECOND_URL_MODEL` / `ADJUDICATOR_MODEL` set the model per stage
  (aliases `haiku|sonnet|opus`).
- `GITHUB_TOKEN` is optional and raises the GitHub search rate limit (`gh auth token` works).
  `COMPOSIO_API_KEY` is optional and adds a Composio SDK check of each toolkit.

## How to run the agent

```bash
python run.py --apps 3 --stage all            # one app, end to end
python run.py --apps 1-10 --stage all         # a range
python run.py --apps 1-100 --stage all        # everything (resumable; cached pages are reused)
```

Stages can also run one at a time: `discover` → `extract` → `verify` (or `loop1`/`loop2`/`loop3`) → `analyze` → `page`.
After the human sample is filled in, run `--stage analyze` then `--stage page` again.

Requirements gate: `python scripts/check_requirements.py --write` (R1–R24 from `MASTER.md`).
Live evidence re-check (no keys): `python scripts/reverify_live.py --apps 1-100`.

## Architecture

```
apps.yaml ─► discover.py ─► fetch.py (cache/) ─► extract.py (pass 1) ─► verify.py (Loop 1)
              │ hint URLs, model/web-search URLs,     │ LLM fills MASTER §5 schema       │ quote-in-page, 200, schema,
              │ GitHub MCP search, Composio catalog,  │ quoting cached pages only;       │ consistency rules, Composio
              │ 1-hop crawl                           │ snapshot -> pass1                │ catalog cross-check
           ─► second_agent.py (Loop 2) ─► browser_check.py (Loop 3) ─► sample.py + review_server.py (Loop 4, human)
              independent re-research,      Playwright render + adjudicator,   stratified sample, fixed seed
              blind to pass 1               fresh quotes re-verified in code
           ─► metrics.py ─► analyze.py ─► build_page.py ─► site/index.html (+ results.json, patterns.json, llms.txt)
```

| Module | What it does |
|---|---|
| `src/llm.py` | One wrapper for every LLM call (Claude CLI or Anthropic SDK); parses JSON replies |
| `src/fetch.py` | Polite fetch (user agent, 1 req/s per host), gzip cache with timestamps, Playwright render |
| `src/discover.py` | Builds the candidate URL list per app and fetches it |
| `src/composio_catalog.py` | Parses Composio's public toolkit catalog; optional SDK confirmation |
| `src/extract.py` | Prompt + schema + definitions; normalises output; `pass1` snapshot |
| `src/verify.py` | Loop 1: deterministic checks and the evidence gate |
| `src/second_agent.py` | Loop 2: independent agent, field-level comparison |
| `src/browser_check.py` | Loop 3: headless browser + adjudicator on flagged fields |
| `src/sample.py`, `scripts/review_server.py` | Loop 4: human sample sheet and the local review UI |
| `src/metrics.py`, `src/analyze.py` | Accuracy and loop stats; patterns + headline sentences |
| `src/build_page.py` | The single self-contained HTML case study |

## Verification method

1. **Loop 1 (deterministic, code only):** each evidence URL must be in the cache with HTTP 200, and each
   quote must appear in that cached page (whitespace, quotes and markdown marks normalised). If a quote is
   close but not exact, it is re-anchored to the page's own wording when at least 85% of its words line up
   in order. Any field left with no surviving quote becomes `unknown`. Consistency rules and a Composio
   catalog cross-check raise flags.
2. **Loop 2 (independent second agent):** different URL discovery, a different prompt, and a different
   model for URL discovery. It is blind to pass 1. Field-level disagreements are recorded as hard, soft or
   gap.
3. **Loop 3 (browser):** hard disagreements, flags and unknowns get their pages re-rendered in headless
   Chromium. A stronger model then decides each field with a fresh quote, and that quote is checked in code
   again. Anything still unsettled is marked `needs_human`.
4. **Loop 4 (human):** a stratified sample with fixed seed `20261123` (3 apps per category, plus all
   flagged apps). Karan marks each pass-1 value and each final value right or wrong. The accuracy numbers
   come only from this sheet.

## Where a human was needed

See [`logs/human_interventions.md`](logs/human_interventions.md). It is also rendered on the page.

## Repo layout

See `MASTER.md` §6. `cache/` holds every fetched page (gzip) so that all evidence can be re-checked offline.

## Limitations

The full list is on the page, under **#limitations**. Discovery for apps 39–100 used model-proposed URLs
plus crawling instead of web search because of LLM usage limits. Nothing was tested with live credentials.
