"""Patterns across the 100 apps, computed only from data/results.json (final values).

Writes data/patterns.json. Every headline sentence is generated from these numbers, and each headline
carries the dotted `key` of the number it quotes, so scripts/check_requirements.py can assert the
number in the sentence equals the number in patterns.json (R9).
"""
from __future__ import annotations

from collections import Counter, defaultdict

from .common import DATA, load_results, write_json

BUCKET = {"self_serve_free": "self-serve", "self_serve_trial": "self-serve", "paid_plan_required": "paid plan",
          "admin_approval": "gated", "app_review": "gated", "partner_gated": "gated", "contact_sales": "gated",
          "unknown": "unknown"}
OUTREACH_ACCESS = {"partner_gated", "contact_sales"}


def pct(a, b):
    return round(100 * a / b) if b else 0


def run() -> dict:
    rows = list(load_results().values())
    n = len(rows)
    cats = sorted({r["category"] for r in rows}, key=lambda c: min(r["id"] for r in rows if r["category"] == c))

    auth = Counter(m for r in rows for m in set(r["auth"]["methods"]))
    oauth_any = sum("oauth2" in r["auth"]["methods"] for r in rows)
    key_any = sum(bool(set(r["auth"]["methods"]) & {"api_key", "bearer_token", "basic"}) for r in rows)
    both = sum("oauth2" in r["auth"]["methods"] and bool(set(r["auth"]["methods"]) & {"api_key", "bearer_token", "basic"}) for r in rows)
    key_only = sum("oauth2" not in r["auth"]["methods"] and bool(set(r["auth"]["methods"]) & {"api_key", "bearer_token", "basic"}) for r in rows)

    access = Counter(r["access"]["status"] for r in rows)
    buckets = Counter(BUCKET[r["access"]["status"]] for r in rows)
    by_cat = {}
    for c in cats:
        rs = [r for r in rows if r["category"] == c]
        b = Counter(BUCKET[r["access"]["status"]] for r in rs)
        v = Counter(r["buildability"]["verdict"] for r in rs)
        by_cat[c] = {"n": len(rs), **{k: b.get(k, 0) for k in ("self-serve", "paid plan", "gated", "unknown")},
                     "self_serve_pct": pct(b.get("self-serve", 0), len(rs)),
                     "ready": v.get("ready", 0), "ready_with_caveats": v.get("ready_with_caveats", 0), "blocked": v.get("blocked", 0),
                     "oauth2": sum("oauth2" in r["auth"]["methods"] for r in rs),
                     "mcp_official": sum(bool(r["mcp"]["official"]) for r in rs)}
    ranked = sorted(by_cat.items(), key=lambda kv: (-kv[1]["self_serve_pct"], kv[0]))

    blockers = Counter(r["buildability"]["main_blocker"] for r in rows if r["buildability"]["main_blocker"] != "none")
    verdicts = Counter(r["buildability"]["verdict"] for r in rows)
    mcp_off = sum(bool(r["mcp"]["official"]) for r in rows)
    mcp_comm_only = sum(not r["mcp"]["official"] and bool(r["mcp"]["community"]) for r in rows)
    mcp_none = n - mcp_off - mcp_comm_only
    comp_yes = sum(r["buildability"].get("composio_existing_toolkit") == "yes" for r in rows)
    styles = Counter(s for r in rows for s in r["api_surface"]["styles"])
    app_types = Counter(r.get("app_type", "other") for r in rows)

    def brief(r):
        return {"id": r["id"], "app": r["app"], "category": r["category"], "access": r["access"]["status"],
                "verdict": r["buildability"]["verdict"], "blocker": r["buildability"]["main_blocker"],
                "composio_toolkit": r["buildability"].get("composio_existing_toolkit"), "mcp_official": bool(r["mcp"]["official"]),
                "rationale": r["buildability"]["rationale"]}

    easy = [brief(r) for r in rows if r["buildability"]["verdict"] == "ready" and BUCKET[r["access"]["status"]] == "self-serve"
            and r["api_surface"]["breadth"] in ("moderate", "broad")]
    easy_new = [e for e in easy if e["composio_toolkit"] != "yes"]
    outreach = [brief(r) for r in rows if r["access"]["status"] in OUTREACH_ACCESS
                or r["buildability"]["main_blocker"] in ("partner_gate", "no_public_api")]
    review = [brief(r) for r in rows if r["access"]["status"] == "app_review" or r["buildability"]["main_blocker"] == "app_review"]
    paid = [brief(r) for r in rows if r["access"]["status"] == "paid_plan_required" or r["buildability"]["main_blocker"] == "paid_plan"]
    unknowns = [brief(r) for r in rows if r["access"]["status"] == "unknown" or r["auth"]["methods"] == ["unknown"]]
    non_saas = [brief(r) | {"app_type": r.get("app_type")} for r in rows if r.get("app_type") in ("cli_or_library", "third_party_api_wrapper")]

    top_blocker, top_blocker_n = (blockers.most_common(1)[0] if blockers else ("none", 0))
    best_cat, worst_cat = ranked[0], ranked[-1]
    pat = {
        "n_apps": n,
        "auth_distribution": dict(auth.most_common()),
        "auth_summary": {"oauth2_any": oauth_any, "key_or_token_any": key_any, "both": both, "key_only": key_only,
                         "oauth2_pct": pct(oauth_any, n), "key_or_token_pct": pct(key_any, n), "both_pct": pct(both, n)},
        "access_distribution": dict(access.most_common()),
        "access_buckets": dict(buckets),
        "self_serve_pct": pct(buckets.get("self-serve", 0), n),
        "gated_n": buckets.get("gated", 0),
        "access_by_category": by_cat,
        "category_rank_self_serve": [c for c, _ in ranked],
        "best_category": {"name": best_cat[0], "self_serve_pct": best_cat[1]["self_serve_pct"]},
        "worst_category": {"name": worst_cat[0], "self_serve_pct": worst_cat[1]["self_serve_pct"]},
        "blocker_frequency": dict(blockers.most_common()),
        "top_blocker": {"name": top_blocker, "n": top_blocker_n},
        "verdicts": dict(verdicts),
        "ready_n": verdicts.get("ready", 0), "caveats_n": verdicts.get("ready_with_caveats", 0), "blocked_n": verdicts.get("blocked", 0),
        "mcp_coverage": {"official": mcp_off, "community_only": mcp_comm_only, "none_found": mcp_none},
        "composio_coverage": {"has_toolkit": comp_yes, "no_toolkit": n - comp_yes},
        "api_styles": dict(styles.most_common()),
        "app_types": dict(app_types.most_common()),
        "easy_wins": easy, "easy_wins_n": len(easy),
        "easy_wins_without_composio_toolkit": easy_new, "easy_new_n": len(easy_new),
        "needs_outreach": outreach, "outreach_n": len(outreach),
        "needs_app_review": review, "review_n": len(review),
        "needs_paid_plan": paid, "paid_n": len(paid),
        "unknowns": unknowns, "non_saas": non_saas,
    }
    rest_n = styles.get("rest", 0)
    gql_n = styles.get("graphql", 0)
    pat["rest_n"], pat["graphql_n"] = rest_n, gql_n
    H = []

    def h(text, key):
        H.append({"text": text, "key": key})

    if oauth_any >= key_any:
        h(f"OAuth2 is the dominant auth pattern: {oauth_any} of {n} apps support it, and {both} offer both OAuth2 and a static key/token "
          f"- so most toolkits need an OAuth app registration, with keys as the quick single-tenant path.", "auth_summary.oauth2_any")
    else:
        h(f"Static keys/tokens are the most common auth: {key_any} of {n} apps accept an API key or token, {oauth_any} support OAuth2, "
          f"and {both} offer both - so most toolkits can start on API-key auth and add OAuth for multi-tenant use.", "auth_summary.key_or_token_any")
    h(f"Getting credentials is mostly self-serve: {pat['self_serve_pct']}% of apps let a developer get working credentials alone "
      f"(free or trial); {buckets.get('gated', 0)} are gated by an admin, app review, partner programme or sales.", "self_serve_pct")
    h(f"Gating clusters by category: {best_cat[0]} is the most self-serve ({best_cat[1]['self_serve_pct']}%), "
      f"{worst_cat[0]} the least ({worst_cat[1]['self_serve_pct']}%).", "worst_category.self_serve_pct")
    h(f"The most common blocker is '{top_blocker.replace('_', ' ')}' ({top_blocker_n} apps); "
      f"{verdicts.get('ready', 0)} apps are ready today, {verdicts.get('ready_with_caveats', 0)} ready with caveats, {verdicts.get('blocked', 0)} blocked.", "top_blocker.n")
    h(f"MCP is already mainstream: {mcp_off} vendors ship an official MCP server and {mcp_comm_only} more have only community servers.", "mcp_coverage.official")
    h(f"Composio already has toolkits for {comp_yes} of the {n}; {len(easy_new)} self-serve, ready apps have no Composio toolkit yet - the cheapest net-new wins.", "easy_new_n")
    pat["headlines"] = H
    write_json(DATA / "patterns.json", pat)
    print(f"analyze: {len(H)} headlines; easy wins {len(easy)}, outreach {len(outreach)}")
    return pat
