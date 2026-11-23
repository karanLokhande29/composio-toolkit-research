# Human interventions log

Every point where a human (Karan) was needed, or a decision was made by a human rather than the agent.
The page's #human-needed section is rendered from this file (R11).

| when (IST) | app | what the human did | why the agent could not |
|---|---|---|---|
| 2026-11-23 15:49 | - | Wrote the field definitions (what counts as self_serve vs app_review vs partner_gated, verdict rules) used in every prompt | Taxonomy is a product decision, not something to infer from docs |
| 2026-11-23 15:49 | - | Chose the free search fallback: Claude WebSearch for discovery (DuckDuckGo blocked automated queries; Composio has no free web-search toolkit and no COMPOSIO_API_KEY was used) | Tool/account choice |
| 2026-11-23 15:49 | - | Decided not to create paid or trial accounts for any app; gates are reported from public docs only | Assignment rule: no paid accounts |
| 2026-11-23 16:27 | - | Decided to switch discovery for apps 39-100 from web search to model-proposed URLs + crawl, and run agent 2 on haiku with sonnet URL discovery | Claude plan usage limit hit mid-run; deadline + no-cost constraint |
| 2026-11-23 16:27 | - | GitHub token lacks the `workflow` scope, so the Actions trigger cannot be pushed by the agent; Pages deployed from gh-pages branch instead. Karan must run `gh auth refresh -s workflow` | Only the account owner can grant OAuth scopes |
