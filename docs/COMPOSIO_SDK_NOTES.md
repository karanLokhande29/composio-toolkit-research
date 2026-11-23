# Composio SDK notes (verified against current docs, 23 Nov 2026)

Every fact below was read from the official docs before any Composio code was written (MASTER §4 rule 2).

| Fact | Value | Source |
|---|---|---|
| Python package | `composio` (NOT `composio-core`, which is the legacy v1 SDK) | https://docs.composio.dev/docs/quickstart.md |
| Install | `pip install composio` (Python 3.11-3.15) | https://docs.composio.dev/docs/quickstart.md |
| Env var | `COMPOSIO_API_KEY` (from dashboard → Settings → API keys) | https://docs.composio.dev/docs/quickstart.md |
| Client | `from composio import Composio; composio = Composio()` | https://docs.composio.dev/reference/api-reference/toolkits.md (SDK notes section) |
| Sessions (recommended for agents) | `session = composio.create(user_id=...)`; `session.tools()` | same |
| Toolkits API | `composio.toolkits.list(...)`, `composio.toolkits.get(slug)`, `get_many(slugs)` | https://docs.composio.dev/reference/sdk-reference/python/toolkits.md |
| Tool execution | `composio.tools.execute(slug, arguments, user_id=...)` (legacy direct path; sessions preferred) | https://docs.composio.dev/reference/sdk-reference/python/tools.md |
| REST toolkits endpoint | `GET https://backend.composio.dev/api/v3.1/toolkits` with `x-api-key` header (returns 401 without a key - tested) | https://docs.composio.dev/reference/api-reference/toolkits.md |
| Public catalog (no key) | `https://docs.composio.dev/toolkits.md` - table of 1,841 toolkits with slug, #tools, #triggers, auth schemes, managed-OAuth flag; per-toolkit page `https://docs.composio.dev/toolkits/<slug>.md` | fetched directly |

## How this project uses Composio

1. **Always (keyless):** `src/composio_catalog.py` parses the public catalog. It decides
   `composio_existing_toolkit` deterministically (exact name/slug match, or the slug the extractor picked from
   the candidate list) and records the catalog row as evidence. Composio's own auth schemes for that toolkit
   are used in Loop 1 as an independent cross-check of our auth answer.
2. **Optional (with `COMPOSIO_API_KEY`):** `sdk_confirm()` calls `Composio().toolkits.get(slug)`.

## Free-account search/scrape toolkits

The catalog's search toolkits (Brave Search, SearchAPI, Search1API, You.com, Firecrawl, ...) all need the
*provider's* API key (`API_KEY` auth), and there is no Composio-native free web search toolkit documented
(`/toolkits/composio_search` returns "Page not found"). **Fallback used:** Claude's built-in WebSearch tool via
the `claude` CLI for apps 1-38; model-proposed official URLs, each verified by fetching, for apps 39-100 (budget).
With a Composio key + a search provider key, `discover.search_agent` is the single place to swap in a
Composio search tool.
