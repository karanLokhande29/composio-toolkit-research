"""Stage 2 - read the cached pages and fill the MASTER §5 schema with an LLM.

The model only sees text we fetched ourselves (from cache/), and for every answer it must quote a
snippet copied verbatim from one of those pages. Whether the snippet really exists is checked in
code (verify.py, Loop 1) - the model is never trusted on that.
`pass1` is a snapshot of the raw first-pass answer, taken before any verification loop.
Serves: R2-R8 (the fields), R7 (evidence), R10 (agent), R14 (pass1 snapshot for accuracy).
"""
from __future__ import annotations

import copy
import re

from . import fetch, llm
from .common import LOGS, RAW, log_jsonl, write_json

ENUMS = {
    "auth": {"oauth2", "api_key", "basic", "bearer_token", "jwt", "other", "unknown"},
    "access": {"self_serve_free", "self_serve_trial", "paid_plan_required", "admin_approval",
               "app_review", "partner_gated", "contact_sales", "unknown"},
    "styles": {"rest", "graphql", "soap", "websocket", "sdk_only", "cli_or_library_only", "none"},
    "breadth": {"narrow", "moderate", "broad", "unknown"},
    "verdict": {"ready", "ready_with_caveats", "blocked"},
    "blocker": {"none", "partner_gate", "paid_plan", "app_review", "admin_scope", "no_public_api",
                "cli_only", "other"},
    "app_type": {"saas", "open_source_self_hostable", "cli_or_library", "third_party_api_wrapper",
                 "cloud_platform", "other"},
}

DEFINITIONS = """DEFINITIONS (use exactly these enum values)
auth.methods: oauth2 | api_key | basic | bearer_token (personal/static access token sent as Bearer) | jwt | other | unknown
access.status - how a developer gets working API credentials:
  self_serve_free     anyone can sign up and get credentials at no cost (free plan, free developer account/sandbox, or open-source self-host)
  self_serve_trial    self-serve, but only during a time-limited free trial; continued use needs payment
  paid_plan_required  API is only available on a paid plan (self-serve purchase, no sales call)
  admin_approval      a workspace/org admin must enable the API or approve the app/token
  app_review          you can build/test yourself, but production or multi-customer use needs vendor review/verification (e.g. developer token approval, app review)
  partner_gated       requires joining a partner programme or signing an agreement with the vendor
  contact_sales       API access only through sales / enterprise contract
  unknown             the pages do not say (give the reason)
api_surface.styles: rest | graphql | soap | websocket | sdk_only | cli_or_library_only | none
api_surface.breadth: narrow (a handful of endpoints / one job) | moderate | broad (many resources, hundreds of endpoints) | unknown
mcp.official: URL of an MCP server published by the vendor itself, else null. mcp.community: URLs of third-party MCP server repos (only if they are clearly for this app).
buildability.verdict: ready (self-serve credentials + documented API: a toolkit could be built today) |
  ready_with_caveats (buildable but with friction: paid plan, app review for production, admin scopes, narrow API, CLI only) |
  blocked (cannot build without outreach/partnership, or there is no public API)
buildability.main_blocker: none | partner_gate | paid_plan | app_review | admin_scope | no_public_api | cli_only | other
app_type: saas | open_source_self_hostable | cli_or_library | third_party_api_wrapper | cloud_platform | other
  (Do not force CLI tools / OSS libraries / third-party wrappers into the SaaS mould - classify honestly.)
composio_existing_toolkit: yes only if a Composio toolkit page for THIS app is among the pages, else no."""

EVIDENCE_RULES = """EVIDENCE RULES (most important)
- Every evidence item is {"url": <one of the PAGE urls above, exactly>, "snippet": <text copied EXACTLY, character for character, from that page>}.
- Snippets are 5-30 words, one contiguous passage from a single line of the page text shown. Do not paraphrase, do not join lines, do not add ellipses.
- If the pages do not support an answer, use "unknown" (or null) and put the reason in unknown_reasons. Never guess from memory."""

SCHEMA = """Return ONLY this JSON:
{"one_liner": "what the app does, one sentence",
 "app_type": "...",
 "auth": {"methods": [], "oauth_grant_types": [], "notes": "", "evidence": [{"url": "", "snippet": ""}]},
 "access": {"status": "", "dev_sandbox": true|false|null, "notes": "", "evidence": []},
 "api_surface": {"styles": [], "breadth": "", "openapi_spec_url": null, "webhooks": true|false|null, "rate_limit_note": "", "evidence": []},
 "mcp": {"official": null, "community": [], "evidence": []},
 "buildability": {"verdict": "", "main_blocker": "", "rationale": "one sentence", "composio_existing_toolkit": "yes|no", "composio_slug": null},
 "overview_evidence": [{"url": "", "snippet": ""}],
 "confidence": 0.0,
 "unknown_reasons": {"auth": "", "access": "", "api_surface": "", "mcp": ""}}"""

PROMPT_A = """You are researching whether Composio can build an agent toolkit for this app.
APP: {app}   CATEGORY: {category}   HINT: {hint}

{definitions}

{evidence_rules}

{composio}

PAGES (fetched by our crawler; the only allowed evidence sources):
{pages}

{schema}"""

LINE_KW = re.compile(r"oauth|api[ -]?key|access token|bearer|basic auth|authenticat|authoriz|client[ _]id|"
                     r"secret|scope|free|trial|plan|pricing|paid|partner|contact (us|sales)|enterprise|review|"
                     r"approv|admin|sandbox|developer account|rate limit|requests per|webhook|graphql|rest|"
                     r"openapi|swagger|mcp|model context|endpoint|sdk|cli", re.I)


def excerpt(text: str, budget: int = 5000) -> str:
    """Keep the start of the page plus every keyword line (+/-1 line of context), up to budget."""
    if len(text) <= budget:
        return text
    lines = text.split("\n")
    keep = set(range(min(8, len(lines))))
    for i, ln in enumerate(lines):
        if LINE_KW.search(ln):
            keep.update({i - 1, i, i + 1})
    out, size = [], 0
    for i in sorted(k for k in keep if 0 <= k < len(lines)):
        ln = lines[i][:600]
        if size + len(ln) > budget:
            break
        out.append(ln); size += len(ln) + 1
    return "\n".join(out)


PURPOSE_RANK = {"auth": 0, "access": 1, "pricing": 2, "api_reference": 3, "mcp_official": 4, "overview": 5,
                "rate_limits": 6, "webhooks": 7, "openapi": 8, "composio_toolkit": 9, "mcp_community": 10,
                "hint": 11, "crawl": 12, "mcp_community?": 13}


def select_pages(disc: dict, max_pages: int = 14, total_budget: int = 80000, per_page: int = 5500) -> list[tuple[str, str]]:
    cands = [u for u in disc["urls"] if u.get("ok")]
    cands.sort(key=lambda u: PURPOSE_RANK.get(u.get("purpose", ""), 12))
    chosen, used, seen_text = [], 0, set()
    for u in cands:
        rec = fetch.load(u["url"])
        if not rec:
            continue
        text = fetch.page_text(rec).strip()
        sig = text[:300]
        if sig in seen_text:  # skip duplicates (redirects to the same page)
            continue
        seen_text.add(sig)
        ex = excerpt(text, per_page)
        if used + len(ex) > total_budget:
            continue
        chosen.append((u["url"], ex)); used += len(ex)
        if len(chosen) >= max_pages:
            break
    return chosen


def composio_block(disc: dict) -> str:
    c = disc.get("composio", {})
    rows = c.get("exact") or c.get("candidates") or []
    if not rows:
        return "COMPOSIO CATALOG: no toolkit with a matching name in Composio's public catalog (1,800+ toolkits)."
    lines = [f"- {r['name']} (slug {r['slug']}, {r['tools']} tools, auth {','.join(r['auth'])}) {r['url']}" for r in rows]
    label = "exact name match" if c.get("exact") else "name candidates (may be a different product)"
    return "COMPOSIO CATALOG (" + label + "):\n" + "\n".join(lines)


def render_pages(pages: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"=== PAGE {i+1}: {url}\n{text}" for i, (url, text) in enumerate(pages))


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def normalise(out: dict, app: dict) -> dict:
    """Coerce the model output into the MASTER §5 schema (enums lower-cased, missing keys filled)."""
    def enum(v, allowed, default):
        v = str(v or "").strip().lower().replace(" ", "_").replace("-", "_")
        return v if v in allowed else default

    a, ac, s, m, b = (out.get(k) or {} for k in ("auth", "access", "api_surface", "mcp", "buildability"))
    methods = [enum(x, ENUMS["auth"], "other") for x in _as_list(a.get("methods"))] or ["unknown"]
    rec = {
        "id": app["id"], "app": app["app"], "category": app["category"], "hint": app["hint"],
        "one_liner": (out.get("one_liner") or "").strip(),
        "app_type": enum(out.get("app_type"), ENUMS["app_type"], "other"),
        "auth": {"methods": sorted(set(methods)), "oauth_grant_types": _as_list(a.get("oauth_grant_types")),
                 "notes": a.get("notes") or "", "evidence": _as_list(a.get("evidence"))},
        "access": {"status": enum(ac.get("status"), ENUMS["access"], "unknown"),
                   "dev_sandbox": ac.get("dev_sandbox"), "notes": ac.get("notes") or "",
                   "evidence": _as_list(ac.get("evidence"))},
        "api_surface": {"styles": sorted({enum(x, ENUMS["styles"], "none") for x in _as_list(s.get("styles"))}) or ["none"],
                        "breadth": enum(s.get("breadth"), ENUMS["breadth"], "unknown"),
                        "openapi_spec_url": s.get("openapi_spec_url"), "webhooks": s.get("webhooks"),
                        "rate_limit_note": s.get("rate_limit_note") or "", "evidence": _as_list(s.get("evidence"))},
        "mcp": {"official": m.get("official") or None, "community": [c for c in _as_list(m.get("community")) if c],
                "evidence": _as_list(m.get("evidence"))},
        "buildability": {"verdict": enum(b.get("verdict"), ENUMS["verdict"], "ready_with_caveats"),
                         "main_blocker": enum(b.get("main_blocker"), ENUMS["blocker"], "other"),
                         "rationale": b.get("rationale") or "",
                         "composio_existing_toolkit": enum(b.get("composio_existing_toolkit"), {"yes", "no", "unknown"}, "unknown"),
                         "composio_slug": b.get("composio_slug")},
        "overview_evidence": _as_list(out.get("overview_evidence")),
        "confidence": float(out.get("confidence") or 0),
        "unknown_reasons": out.get("unknown_reasons") or {},
    }
    # evidence items must be dicts with url+snippet
    for grp in ("auth", "access", "api_surface", "mcp"):
        rec[grp]["evidence"] = [e for e in rec[grp]["evidence"] if isinstance(e, dict) and e.get("url") and e.get("snippet")]
    rec["overview_evidence"] = [e for e in rec["overview_evidence"] if isinstance(e, dict) and e.get("url") and e.get("snippet")]
    return rec


FIELDS = ("one_liner", "app_type", "auth", "access", "api_surface", "mcp", "buildability", "overview_evidence",
          "confidence", "unknown_reasons")


def snapshot(rec: dict) -> dict:
    return copy.deepcopy({k: rec[k] for k in FIELDS if k in rec})


def extract(app: dict, disc: dict, model: str, prompt_template: str = PROMPT_A, tag: str = "agent1",
            system: str = "You are a careful API research analyst. You answer only from the provided pages and output only JSON.") -> dict:
    pages = select_pages(disc)
    prompt = prompt_template.format(app=app["app"], category=app["category"], hint=app["hint"],
                                    definitions=DEFINITIONS, evidence_rules=EVIDENCE_RULES,
                                    composio=composio_block(disc), pages=render_pages(pages), schema=SCHEMA)
    try:
        out, meta = llm.ask_json(prompt, system, model=model)
        err = None
    except Exception as e:
        out, meta, err = {}, {}, str(e)[:300]
    write_json(RAW / f"{app['id']:03d}_{tag}.json", {"meta": meta, "error": err, "pages": [u for u, _ in pages], "output": out})
    rec = normalise(out, app)
    rec["_meta"] = {"agent": tag, "model": model, "pages_used": len(pages), "error": err, **{k: meta.get(k) for k in ("cost_usd", "seconds")}}
    log_jsonl(LOGS / "run_log.jsonl", {"stage": "extract", "agent": tag, "app": app["app"], "pages": len(pages),
                                       "error": err, "cost_usd": meta.get("cost_usd"), "seconds": meta.get("seconds")})
    return rec
