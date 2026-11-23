"""Stage 1 - discover candidate documentation URLs for an app, then fetch them.

Sources (each URL is tagged with where it came from):
  hint     - URLs built from the hint in apps.yaml (+ a few standard guesses: developers./docs./pricing)
  search   - a search agent: Claude with its WebSearch tool, asked for the official pages for auth,
             access/pricing, API reference, rate limits, webhooks, OpenAPI and MCP.
             (Composio has no free web-search toolkit, so this is the documented fallback.)
  github   - GitHub repository search "<app> mcp" for community MCP servers (GitHub API).
  composio - the matching page in Composio's public toolkit catalog.
  crawl    - one hop: links on fetched pages whose text/URL mention auth/oauth/pricing/mcp/...
Serves: R7 (every evidence URL comes from here and is cached), R10 (agent, not hand).
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote_plus, urlparse

import requests

from . import composio_catalog, fetch, llm
from .common import DISCOVERY, env, log_jsonl, LOGS, read_json, write_json

DOMAIN = re.compile(r"\b((?:[a-z0-9-]+\.)+[a-z]{2,})(/[^\s)]*)?", re.I)
KEYWORDS = re.compile(r"auth|oauth|api[-_ ]?key|token|getting[-_ ]?started|quickstart|pricing|plans|"
                      r"rate[-_ ]?limit|webhook|mcp|openapi|swagger|sandbox|partner|developer|"
                      r"reference|scopes|app[-_ ]?review|marketplace|access", re.I)
GENERIC_HOSTS = {"github.com", "medium.com", "youtube.com", "stackoverflow.com", "reddit.com",
                 "twitter.com", "x.com", "linkedin.com", "npmjs.com", "pypi.org", "docs.composio.dev"}

SEARCH_SYSTEM = ("You are a meticulous API research assistant. Use web search to find OFFICIAL "
                 "documentation pages. Prefer the vendor's own domains. Output only JSON.")
SEARCH_PROMPT = """App: {app}  (category: {category}; hint: {hint})
Find the official pages a developer would read to build an integration with this app's API.
Search for, and return URLs for each purpose (skip a purpose if nothing exists):
 overview (what the product is), auth (authentication / OAuth / API keys), access (how a developer gets
 credentials: free developer account, sandbox, trial, paid plan, partner programme, app review, contact sales),
 pricing (if API access depends on plan), api_reference, rate_limits, webhooks, openapi (spec file),
 mcp_official (an MCP server published by the vendor), mcp_community (popular community MCP server repo).
If the app has no public API, return pages that show that (e.g. help article, partner page).
Return ONLY: {{"urls": [{{"url": "...", "purpose": "auth"}}], "notes": "one line on anything odd"}}  (max 14 urls)"""


def hint_urls(hint: str) -> list[str]:
    urls = []
    for m in DOMAIN.finditer(hint):
        host, path = m.group(1).lower(), m.group(2) or ""
        urls.append(f"https://{host}{path}")
        if not path and host.count(".") == 1:  # bare domain -> standard developer-portal guesses
            urls += [f"https://developers.{host}", f"https://developer.{host}", f"https://docs.{host}",
                     f"https://{host}/pricing"]
    return urls


def github_mcp_search(app: str) -> list[dict]:
    q = quote_plus(f"{re.sub(r'[()]', ' ', app)} mcp in:name,description")
    api = f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=5"
    headers = {"User-Agent": fetch.UA, "Accept": "application/vnd.github+json"}
    if env("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {env('GITHUB_TOKEN')}"
    try:
        r = requests.get(api, headers=headers, timeout=20)
        items = r.json().get("items", []) if r.status_code == 200 else []
    except Exception:
        items = []
    return [{"repo": i["full_name"], "url": i["html_url"], "stars": i["stargazers_count"],
             "description": (i.get("description") or "")[:160]} for i in items]


def search_agent(app: dict, model: str) -> tuple[list[dict], dict]:
    prompt = SEARCH_PROMPT.format(**app)
    try:
        out, meta = llm.ask_json(prompt, SEARCH_SYSTEM, model=model, web_search=True)
        urls = [u for u in out.get("urls", []) if isinstance(u, dict) and str(u.get("url", "")).startswith("http")]
        return urls[:14], meta | {"notes": out.get("notes", "")}
    except Exception as e:
        return [], {"error": str(e)[:200]}


def crawl_candidates(pages: list[dict], allowed_hosts: set[str], limit: int = 10) -> list[str]:
    seen, out = set(), []
    for rec in pages:
        for ln in rec.get("links", []):
            href = ln["href"]
            host = urlparse(href).netloc.lower()
            base = ".".join(host.split(".")[-2:])
            if base not in allowed_hosts or href in seen:
                continue
            seen.add(href)
            if KEYWORDS.search(ln.get("text", "")) or KEYWORDS.search(urlparse(href).path):
                out.append(href)
    # prefer the most specific-looking ones (auth/oauth/pricing/mcp first)
    pri = re.compile(r"oauth|auth|pricing|mcp|rate|access|partner|getting", re.I)
    out.sort(key=lambda u: 0 if pri.search(u) else 1)
    return out[:limit]


def discover_and_fetch(app: dict, model: str, use_search: bool = True, tag: str = "agent1",
                       extra: list[dict] | None = None) -> dict:
    """Run discovery for one app and fetch everything. Returns the discovery record (also saved)."""
    out_path = DISCOVERY / f"{app['id']:03d}_{tag}.json"
    urls: list[dict] = [{"url": u, "purpose": "hint", "source": "hint"} for u in hint_urls(app["hint"])]
    meta = {}
    if use_search:
        found, meta = search_agent(app, model)
        urls += [{"url": u["url"], "purpose": u.get("purpose", ""), "source": "search"} for u in found]
    if extra:
        urls += extra
    gh = github_mcp_search(app["app"])
    urls += [{"url": g["url"], "purpose": "mcp_community?", "source": "github"} for g in gh[:3]]
    comp = composio_catalog.lookup(app["app"])
    for r in (comp["exact"] or comp["candidates"][:2]):
        urls.append({"url": r["url"], "purpose": "composio_toolkit", "source": "composio"})

    # de-duplicate, fetch in parallel
    uniq, seen = [], set()
    for u in urls:
        if u["url"] not in seen:
            seen.add(u["url"]); uniq.append(u)
    with ThreadPoolExecutor(6) as ex:
        recs = list(ex.map(lambda u: fetch.fetch(u["url"]), uniq))
    for u, r in zip(uniq, recs):
        u["status"] = r.get("status"); u["ok"] = fetch.ok(r); u["js_rendered"] = r.get("js_rendered")

    # one-hop crawl inside the vendor's own domains
    allowed = set()
    for u in uniq:
        host = urlparse(u["url"]).netloc.lower()
        base = ".".join(host.split(".")[-2:])
        if u["ok"] and base not in GENERIC_HOSTS and u["source"] in ("hint", "search"):
            allowed.add(base)
    vendor_pages = [r for u, r in zip(uniq, recs) if u["ok"] and u["source"] in ("hint", "search")]
    more = [h for h in crawl_candidates(vendor_pages, allowed) if h not in seen]
    with ThreadPoolExecutor(6) as ex:
        more_recs = list(ex.map(fetch.fetch, more))
    for h, r in zip(more, more_recs):
        uniq.append({"url": h, "purpose": "crawl", "source": "crawl", "status": r.get("status"),
                     "ok": fetch.ok(r), "js_rendered": r.get("js_rendered")})

    rec = {"id": app["id"], "app": app["app"], "tag": tag, "urls": uniq, "github_mcp": gh,
           "composio": {"exact": [{k: r[k] for k in ("name", "slug", "tools", "auth", "url")} for r in comp["exact"]],
                        "candidates": [{k: r[k] for k in ("name", "slug", "tools", "auth", "url")} for r in comp["candidates"]]},
           "search_meta": meta}
    write_json(out_path, rec)
    log_jsonl(LOGS / "run_log.jsonl", {"stage": "discover", "agent": tag, "app": app["app"],
                                       "urls": len(uniq), "ok": sum(1 for u in uniq if u["ok"]),
                                       "cost_usd": meta.get("cost_usd", 0)})
    return rec


def load_discovery(app_id: int, tag: str = "agent1") -> dict | None:
    return read_json(DISCOVERY / f"{app_id:03d}_{tag}.json")
