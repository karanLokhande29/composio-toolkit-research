"""Loop 2 - an independent second agent, blind to pass 1.

Independent on three axes, so its mistakes should not correlate with agent 1's:
  * different discovery: no web search. A stronger model proposes official URLs from its own
    knowledge, plus hint URLs, a one-hop crawl, GitHub MCP search and Composio catalog page.
  * different prompt: question-by-question "sceptical reviewer" framing.
  * different model: SECOND_MODEL (default sonnet) vs PASS1_MODEL (default haiku).
Its evidence goes through the same deterministic snippet check (Loop 1 code) before comparing.
Field-level comparison -> verification.disagreements. Where agent 1 ended `unknown` (e.g. after the
evidence gate) and agent 2 has a verified answer, agent 2's answer fills the gap (resolved_by=agent).
Serves: R12 (independent second agent), R14 (changes per loop are logged).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from . import discover, extract, llm, verify
from .common import RAW, VLOG, env, load_apps, load_results, log_jsonl, read_json, save_results, write_json

URL_SYSTEM = "You are an API documentation expert. Output only JSON."
URL_PROMPT = """List the official documentation URLs you are confident exist for the API of: {app} ({hint}).
Cover: overview, authentication, how developers get access/credentials (sandbox, partner programme, pricing),
API reference, rate limits, webhooks, MCP server. Only vendor-owned URLs.
Return ONLY {{"urls": [{{"url": "...", "purpose": "auth"}}]}} (max 10)."""

PROMPT_B = """You are a sceptical reviewer double-checking an integration feasibility report for: {app}
(category: {category}; hint: {hint}). Answer each question ONLY from the pages below.
Q1 What does the product do (one sentence)? What kind of thing is it (SaaS, open-source, CLI tool, wrapper)?
Q2 Which authentication schemes does its API accept?
Q3 Could a random developer, today, get working credentials without paying, being approved, or talking to sales?
   If not, what exactly stands in the way?
Q4 What API styles are documented, how broad is the API, is there an OpenAPI spec, webhooks, a rate-limit statement?
Q5 Does the vendor publish an MCP server? Is there a community MCP server repo for it?
Q6 Could Composio build an agent toolkit for it today? Main blocker?

{definitions}

{evidence_rules}

{composio}

PAGES:
{pages}

{schema}"""

SOFT_BUCKET = {"self_serve_free": "self", "self_serve_trial": "self", "paid_plan_required": "paid",
               "admin_approval": "gated", "app_review": "gated", "partner_gated": "gated",
               "contact_sales": "gated", "unknown": "unknown"}


def _authkind(methods):
    m = set(methods)
    return {"oauth2": "oauth2" in m, "key_or_token": bool(m & {"api_key", "bearer_token", "basic", "jwt"})}


def compare(a: dict, b: dict) -> list[dict]:
    """Field-level comparison. 'hard' disagreements go to Loop 3; 'soft' are just logged."""
    out = []

    def add(field, va, vb, level):
        out.append({"field": field, "agent1": va, "agent2": vb, "level": level})

    ka, kb = _authkind(a["auth"]["methods"]), _authkind(b["auth"]["methods"])
    if "unknown" in a["auth"]["methods"] or "unknown" in b["auth"]["methods"]:
        if a["auth"]["methods"] != b["auth"]["methods"]:
            add("auth.methods", a["auth"]["methods"], b["auth"]["methods"], "gap")
    elif ka != kb:
        add("auth.methods", a["auth"]["methods"], b["auth"]["methods"], "hard")
    elif set(a["auth"]["methods"]) != set(b["auth"]["methods"]):
        add("auth.methods", a["auth"]["methods"], b["auth"]["methods"], "soft")
    sa, sb = a["access"]["status"], b["access"]["status"]
    if sa != sb:
        lvl = "gap" if "unknown" in (sa, sb) else ("soft" if SOFT_BUCKET[sa] == SOFT_BUCKET[sb] else "hard")
        add("access.status", sa, sb, lvl)
    st_a = set(a["api_surface"]["styles"]) & {"rest", "graphql", "soap"}
    st_b = set(b["api_surface"]["styles"]) & {"rest", "graphql", "soap"}
    if st_a != st_b:
        add("api_surface.styles", sorted(st_a), sorted(st_b), "hard" if not (st_a & st_b) else "soft")
    ba, bb = a["api_surface"]["breadth"], b["api_surface"]["breadth"]
    if ba != bb:
        lvl = "gap" if "unknown" in (ba, bb) else ("hard" if {ba, bb} == {"narrow", "broad"} else "soft")
        add("api_surface.breadth", ba, bb, lvl)
    if bool(a["mcp"]["official"]) != bool(b["mcp"]["official"]):
        add("mcp.official", a["mcp"]["official"], b["mcp"]["official"], "hard")
    if a["buildability"]["verdict"] != b["buildability"]["verdict"]:
        add("buildability.verdict", a["buildability"]["verdict"], b["buildability"]["verdict"], "hard")
    if a["buildability"]["main_blocker"] != b["buildability"]["main_blocker"]:
        add("buildability.main_blocker", a["buildability"]["main_blocker"], b["buildability"]["main_blocker"], "hard")
    return out


def research(app: dict) -> dict:
    """Agent 2's own discovery + extraction, cached in data/raw/<id>_agent2_record.json."""
    cached = read_json(RAW / f"{app['id']:03d}_agent2_record.json")
    if cached and not cached.get("_meta", {}).get("error"):
        return cached
    model = env("SECOND_MODEL", "haiku")
    # its own URL list comes from a different (stronger) model than agent 1's discovery
    extra, _ = discover.knowledge_urls(app, env("SECOND_URL_MODEL", "sonnet"))
    disc = discover.discover_and_fetch(app, model=model, use_search=False, tag="agent2", extra=extra)
    rec = extract.extract(app, disc, model=model, prompt_template=PROMPT_B, tag="agent2",
                          system="You are a sceptical integration reviewer. Use only the provided pages. Output only JSON.",
                          budget=int(env("SECOND_BUDGET_CHARS", "30000")))
    for g in verify.GROUPS:   # same deterministic evidence check as Loop 1
        rec[g]["evidence"] = verify.verify_evidence(rec[g]["evidence"], app["app"], g, loop=2)
        if not rec[g]["evidence"] and g != "mcp":
            verify.gate_value(rec, g, "agent2: evidence did not verify")
    write_json(RAW / f"{app['id']:03d}_agent2_record.json", rec)
    return rec


def apply(rec: dict, b: dict) -> list[str]:
    """Fill agent-1 gaps with agent-2 verified answers. Returns changed fields."""
    changed = []
    if rec["auth"]["methods"] == ["unknown"] and b["auth"]["methods"] != ["unknown"] and b["auth"]["evidence"]:
        rec["auth"]["methods"], rec["auth"]["evidence"] = b["auth"]["methods"], b["auth"]["evidence"]
        changed.append("auth.methods")
    if rec["access"]["status"] == "unknown" and b["access"]["status"] != "unknown" and b["access"]["evidence"]:
        rec["access"].update(status=b["access"]["status"], evidence=b["access"]["evidence"], notes=b["access"]["notes"])
        changed.append("access.status")
    if rec["api_surface"]["breadth"] == "unknown" and b["api_surface"]["breadth"] != "unknown" and b["api_surface"]["evidence"]:
        rec["api_surface"].update(breadth=b["api_surface"]["breadth"], styles=b["api_surface"]["styles"],
                                  evidence=b["api_surface"]["evidence"])
        changed.append("api_surface.breadth")
    for k in ("openapi_spec_url", "webhooks"):
        if rec["api_surface"].get(k) in (None, "") and b["api_surface"].get(k) not in (None, ""):
            rec["api_surface"][k] = b["api_surface"][k]
    if not rec["mcp"]["community"] and b["mcp"]["community"]:
        good = [c for c in b["mcp"]["community"] if isinstance(c, str) and verify.mcp_url_ok(c, rec["app"])]
        if good:
            rec["mcp"]["community"] = good; changed.append("mcp.community")
    return changed


def run(ids: list[int], workers: int = 6) -> None:
    results = load_results()
    apps = [a for a in load_apps(ids) if a["id"] in results]
    print(f"loop2: second agent on {len(apps)} apps")

    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(research, a): a for a in apps}
        for fut in as_completed(futs):
            a = futs[fut]
            try:
                b = fut.result()
            except Exception as e:
                print("  loop2 error", a["app"], e); continue
            rec = results[a["id"]]
            dis = compare(rec, b)
            changed = apply(rec, b)
            v = rec["verification"]
            v["disagreements"] = dis
            v["agent2"] = {k: b[k] for k in ("auth", "access", "api_surface", "mcp", "buildability", "one_liner", "app_type")}
            v["checks"] = [c for c in v["checks"] if c.get("loop") != 2]
            v["checks"].append({"loop": 2, "model": b["_meta"].get("model"), "changed": changed,
                                "hard": [d["field"] for d in dis if d["level"] == "hard"]})
            for d in dis:
                log_jsonl(VLOG, {"loop": 2, "app": a["app"], "check": "disagreement", **d})
            save_results(results, only=[a["id"]])
            print(f"  loop2 [{a['id']:3d}] {a['app']:<26} hard={[d['field'] for d in dis if d['level']=='hard']} "
                  f"soft={len([d for d in dis if d['level']=='soft'])} filled={changed}")
