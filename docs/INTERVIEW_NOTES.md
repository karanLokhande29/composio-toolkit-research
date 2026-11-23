# Interview notes: explain every component in plain words

## The one-paragraph story
Composio needs to know, for each app, how it authenticates, whether a developer can get credentials
without a gate, how big the API is, whether an MCP server exists, and whether a toolkit could ship today.
I built a small Python pipeline. It finds each app's docs pages, saves them, and asks an LLM to fill a fixed
schema while quoting the saved pages. Then three verification loops attack those answers. Loop 1 is plain
code that checks every quote really exists on the page. Loop 2 is a second, independent agent; it researches
each app again without seeing the first answer, and its disagreements are flagged. Loop 3 re-renders the
disputed pages in a headless browser and has a stronger model settle them, again with quotes checked in
code. Last, I hand-checked a stratified sample, and that sample is where the accuracy numbers come from.

## Components
- **apps.yaml**: the 100 apps from the brief, generated from the CSV in MASTER.md. It is the only app list.
- **fetch.py**: downloads a page with a clear user agent, at most 1 request per second per host, and saves
  it gzipped in `cache/` with the time it was fetched. The cache matters because it is proof: an answer can
  only cite a page we actually fetched, and anyone can re-check the quote offline. Pages built by JavaScript
  look nearly empty to a plain download, so Loop 3 can re-render them in Chromium (Playwright).
- **discover.py**: assembles candidate URLs:
  (a) URLs from the hint, plus standard guesses like developers./docs./pricing;
  (b) for apps 1–38, Claude with its web-search tool, asked for the official auth, access, pricing,
  reference, rate-limit, webhook and MCP pages;
  (c) for apps 39–100 (after I hit the usage limit), the model proposes official URLs from memory, and
  every one is fetched, so wrong guesses just 404 and can never become evidence;
  (d) a GitHub search for "<app> mcp" to find community MCP servers;
  (e) the app's page in Composio's toolkit catalog;
  (f) a one-hop crawl of links whose text mentions auth, oauth, pricing, MCP and similar.
- **composio_catalog.py**: Composio publishes its whole toolkit catalog as a markdown table
  (docs.composio.dev/toolkits.md, 1,841 toolkits), with each toolkit's auth schemes. I parse it with no API key,
  and it does two jobs: it answers "does Composio already have this toolkit?" deterministically, and it gives
  Composio's own auth schemes as an independent cross-check of our auth answer. With a `COMPOSIO_API_KEY`, the
  SDK's `toolkits.get(slug)` confirms the match. I checked the package name (`composio`, not the legacy
  `composio-core`) and the method names in the docs before writing this code.
- **extract.py**: builds one prompt per app. The prompt has the enum definitions (what counts as self_serve
  vs app_review vs partner_gated, and so on) plus excerpts of the cached pages. Each page is cut to its first
  lines plus every line containing auth, pricing, rate-limit or MCP keywords, so the context stays small. The
  rule is to answer only from these pages, quote 5–30 words verbatim, and use `unknown` with a reason if the
  pages don't say. The output is normalised to the schema, and the raw first answer is frozen as `pass1` so
  the loops can be measured against it.
- **llm.py**: one wrapper for all LLM calls. Locally it runs `claude -p` (headless Claude Code, using my
  login) with the tools turned off and a minimal system prompt. In CI it uses the Anthropic API. Models are
  set per stage in `.env`.
- **verify.py (Loop 1)**: no LLM involved.
  - Every evidence item must be in the cache with HTTP 200, and its quote must appear in the page after
    normalising whitespace, curly quotes and markdown asterisks.
  - Models often merge two table cells or drop a symbol. If at least 85% of the quote's words appear in the
    same order within a short window of the page, I replace the quote with the page's own text for that
    span. What's stored is then literally on the page.
  - If every quote for a field fails, the field becomes `unknown` (the evidence gate).
  - Rules: partner_gated/contact_sales + ready, blocked with no blocker, OAuth2 claimed with no OAuth quote,
    an MCP link that isn't an MCP page, and Composio's auth schemes disagreeing with ours.
- **second_agent.py (Loop 2)**: blind to pass 1, and independent in three ways.
  - URLs come from a different model (Sonnet).
  - The prompt is different: a question-by-question "sceptical reviewer".
  - The context is smaller and picked differently.
  - Its quotes go through the same Loop 1 check. Then I compare field by field: "hard" means a real
    contradiction (OAuth vs no OAuth, self-serve vs gated, different verdict); "soft" means the same bucket
    (free vs trial); "gap" means one side is unknown. Where pass 1 had `unknown` and agent 2 has a verified
    answer, agent 2 fills the gap.
- **browser_check.py (Loop 3)**: runs only on hard disagreements, rule flags and unknowns.
  - It renders the relevant pages in headless Chromium, which recovers JS-built docs.
  - A stronger model (Sonnet) sees both candidate answers with their quotes and must decide each field with
    a fresh quote.
  - That quote is checked by the Loop 1 code. If it checks out, the value is final. If not, the app is
    flagged `needs_human` and goes into my sample.
- **sample.py + review_server.py (Loop 4)**:
  - Fixed seed 20261123: 3 apps per category (30 apps) × 8 fields, plus the flagged fields of every app
    still unresolved.
  - A local page shows the pass-1 value, the final value, and the quote plus link; I click y/n.
  - The agent never fills these columns.
- **metrics.py**: accuracy comes only from my sheet.
  - Pass-1 accuracy: the share of rows where the pass-1 value was right.
  - Final accuracy: the share where the value after the automated loops was right.
  - My corrections are reported separately, not mixed in.
  - Every miss is listed, with the loop that fixed it, or "not caught".
- **analyze.py**: all patterns are counted in code from the final data. Each headline sentence is generated
  from those numbers and stores the key of the number it quotes; the requirements checker asserts the
  sentence contains that number.
- **build_page.py**: one HTML file with no external requests. Text a reviewer must read is static; the table
  and charts are small vanilla JS reading the embedded JSON. `results.json`, `patterns.json` and `llms.txt` are
  published next to it for agents.
- **check_requirements.py**: turns MASTER.md's R1–R24 into checks I can run any time. MANUAL items are
  never auto-passed.

## Likely questions
- **Why should I trust a value?** Because it has a quote, and code (not the model) checked that the quote is
  on the page we fetched. A field with no surviving quote is shown as unknown, not guessed. Then a second
  agent tried to disagree, and I hand-checked a sample.
- **Why a cheap model first?** It's what you'd do at Composio's scale (thousands of apps). The cheap model
  does the bulk; the stronger model is spent only where the loops find disagreement.
- **Why not just ask the LLM?** It answers from memory, which is stale for fast-changing things like MCP
  servers, pricing and app-review rules, and it can't show evidence. Grounding it in fetched pages plus
  verified quotes is the difference.
- **What did the human do?** Defined the taxonomy (what counts as gated), chose the tools and fallbacks under
  the usage limit, decided not to create paid accounts, and checked the sample. All of it is logged in
  `logs/human_interventions.md`.
- **What broke?** The Claude CLI hit my plan's usage limit mid-run. Web-search discovery was the expensive
  part (~$0.28/app), so apps 39–100 used cheaper discovery. Some docs are JS-only or behind logins
  (partner portals), and those fields stay unknown or rely on public pages. Snippet matching fails when a
  model merges table cells, which is why the 85% re-anchoring exists.
- **Composio's SDK?** Verified from the docs (package `composio`, `COMPOSIO_API_KEY`, `toolkits.get`). The
  keyless catalog is used for every app; the SDK path is optional.
- **What would you do next?** Authenticated probes for self-serve apps (actually call one endpoint), a bigger
  human sample, route discovery through Composio's search tools with a key, and run it weekly to track
  changes (new MCP servers, pricing changes).
