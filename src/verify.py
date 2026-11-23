"""Loop 1 - deterministic verification (no LLM involved).

For every evidence item:   URL was fetched (in cache) and returned 200; the snippet appears in the
                           cached page text (normalised whitespace/quotes/markdown marks).
                           If not exact, a token-level repair looks for the same words in order in the
                           page; if >=85% of the words line up, the snippet is replaced by the page's
                           OWN text for that span (so what we store is always literally in the page).
Evidence gate:             a field whose evidence all fails is set to `unknown` (reason recorded) -
                           an unverifiable claim is treated as no claim.
Schema + consistency rules (MASTER §7): gate-vs-ready, blocked-without-blocker, oauth2 with no OAuth
                           evidence, api_key with no key/token evidence, MCP URL not an MCP repo/docs page,
                           Composio catalog cross-check (toolkit exists? Composio's auth schemes vs ours).
Every check is appended to logs/verification_log.jsonl.
Serves: R7, R12, R3-R6 (schema), R8 (composio_existing_toolkit set deterministically).
"""
from __future__ import annotations

import re

from . import composio_catalog, fetch
from .common import VLOG, load_results, log_jsonl, norm_ws, save_results
from .extract import ENUMS

GROUPS = ("auth", "access", "api_surface", "mcp")
_tok_cache: dict[str, tuple[list[str], list[str], dict]] = {}


def _tokens(url: str, text: str):
    if url not in _tok_cache:
        flat = re.sub(r"\s+", " ", text.replace(" ", " ")).strip()
        orig = flat.split(" ")
        normed = [re.sub(r"[^\w]", "", norm_ws(t)) for t in orig]
        index: dict[str, list[int]] = {}
        for i, t in enumerate(normed):
            if t:
                index.setdefault(t, []).append(i)
        _tok_cache[url] = (orig, normed, index)
    return _tok_cache[url]


def _lcs_positions(window: list[str], s: list[str]) -> list[int]:
    """Indices in `window` that take part in the longest common subsequence with `s`."""
    n, m = len(window), len(s)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            dp[i][j] = dp[i + 1][j + 1] + 1 if window[i] == s[j] else max(dp[i + 1][j], dp[i][j + 1])
    i = j = 0
    pos = []
    while i < n and j < m:
        if window[i] == s[j]:
            pos.append(i); i += 1; j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    return pos


def check_snippet(url: str, snippet: str) -> dict:
    """Return {'url_ok', 'exact', 'repaired', 'snippet'} for one evidence item."""
    rec = fetch.load(url)
    if rec is None:  # model cited a page we had not fetched: fetch it now so the claim can still be checked
        rec = fetch.fetch(url)
    url_ok = fetch.ok(rec)
    res = {"url": url, "url_ok": url_ok, "exact": False, "repaired": False, "snippet": snippet}
    if not url_ok or not snippet or len(snippet.split()) < 3:
        return res
    text = fetch.page_text(rec)
    if norm_ws(snippet) in norm_ws(text):
        res["exact"] = True
        return res
    orig, normed, index = _tokens(url + str(len(text)), text)
    s = [t for t in (re.sub(r"[^\w]", "", norm_ws(x)) for x in snippet.split()) if t]
    if len(s) < 3:
        return res
    anchors = [(k, t) for k, t in enumerate(s) if len(t) >= 4][:4]
    best, best_pos, best_start = 0.0, [], 0
    for k, tok in anchors:
        for i in index.get(tok, [])[:200]:
            start = max(0, i - k - 2)
            window = normed[start : start + len(s) + 8]
            pos = _lcs_positions(window, s)
            score = len(pos) / len(s)
            if score > best:
                best, best_pos, best_start = score, pos, start
    if best >= 0.85 and best_pos:
        a, b = best_start + best_pos[0], best_start + best_pos[-1] + 1
        res.update(repaired=True, snippet=" ".join(orig[a:b]), score=round(best, 2))
    return res


def verify_evidence(items: list[dict], app: str, group: str, loop: int = 1) -> list[dict]:
    """Keep only evidence that verifies (exact or repaired). Logs every check."""
    kept = []
    for e in items:
        r = check_snippet(e.get("url", ""), e.get("snippet", ""))
        status = "exact" if r["exact"] else "repaired" if r["repaired"] else ("bad_url" if not r["url_ok"] else "not_found")
        log_jsonl(VLOG, {"loop": loop, "app": app, "group": group, "check": "evidence", "result": status,
                         "url": e.get("url"), "snippet": e.get("snippet", "")[:200]})
        if status in ("exact", "repaired"):
            kept.append({"url": e["url"], "snippet": r["snippet"], "check": status})
    return kept


def mcp_url_ok(url: str, app: str) -> bool:
    """An MCP link must be a fetched page that actually talks about MCP (repo or docs page)."""
    if not url or not url.startswith("http"):
        return False
    if url.startswith(("https://mcp.", "http://mcp.")) or "/mcp" in url and not fetch.ok(fetch.load(url) or {}):
        # bare MCP endpoints (e.g. https://mcp.vendor.com/mcp) are not browsable pages; accept them only
        # when some other fetched evidence page mentions the same URL (checked by caller via evidence).
        return False
    rec = fetch.load(url) or fetch.fetch(url)
    if not fetch.ok(rec):
        return False
    t = norm_ws(fetch.page_text(rec))
    return "mcp" in t or "model context protocol" in t


def gate_value(rec: dict, group: str, reason: str) -> list[str]:
    """Evidence gate: no verified evidence -> unknown. Returns the list of changed fields."""
    changed = []
    if group == "auth" and rec["auth"]["methods"] != ["unknown"]:
        rec["auth"]["methods"] = ["unknown"]; changed.append("auth.methods")
    if group == "access" and rec["access"]["status"] != "unknown":
        rec["access"]["status"] = "unknown"; changed.append("access.status")
    if group == "api_surface" and rec["api_surface"]["breadth"] != "unknown":
        rec["api_surface"]["breadth"] = "unknown"; changed.append("api_surface.breadth")
    if changed:
        rec.setdefault("unknown_reasons", {})[group] = reason
    return changed


def consistency(rec: dict) -> list[dict]:
    flags = []
    a, b = rec["access"]["status"], rec["buildability"]
    if a in ("partner_gated", "contact_sales") and b["verdict"] == "ready":
        flags.append({"rule": "gate_vs_ready", "fields": ["access.status", "buildability.verdict"]})
    if b["verdict"] == "blocked" and b["main_blocker"] == "none":
        flags.append({"rule": "blocked_without_blocker", "fields": ["buildability.main_blocker"]})
    if b["verdict"] == "ready" and b["main_blocker"] not in ("none",):
        flags.append({"rule": "ready_with_blocker", "fields": ["buildability.verdict", "buildability.main_blocker"]})
    ev = " ".join(norm_ws(e["snippet"]) for e in rec["auth"]["evidence"])
    if "oauth2" in rec["auth"]["methods"] and "oauth" not in ev and "authorization code" not in ev:
        flags.append({"rule": "oauth2_without_oauth_evidence", "fields": ["auth.methods"]})
    if "api_key" in rec["auth"]["methods"] and not re.search(r"key|token", ev):
        flags.append({"rule": "api_key_without_key_evidence", "fields": ["auth.methods"]})
    if rec["api_surface"]["styles"] == ["none"] and b["verdict"] == "ready":
        flags.append({"rule": "ready_without_api", "fields": ["api_surface.styles", "buildability.verdict"]})
    for k, allowed in (("access.status", ENUMS["access"]), ("buildability.verdict", ENUMS["verdict"]),
                       ("buildability.main_blocker", ENUMS["blocker"]), ("api_surface.breadth", ENUMS["breadth"])):
        g, f = k.split(".")
        if rec[g][f] not in allowed:
            flags.append({"rule": "schema_enum", "fields": [k]})
    if not rec.get("one_liner"):
        flags.append({"rule": "schema_missing_one_liner", "fields": ["one_liner"]})
    return flags


def composio_check(rec: dict) -> list[dict]:
    """Set composio_existing_toolkit from Composio's own catalog; cross-check auth schemes."""
    flags = []
    look = composio_catalog.lookup(rec["app"])
    b = rec["buildability"]
    slug = (b.get("composio_slug") or "").upper()
    match = look["exact"][:1] or [r for r in look["candidates"] if r["slug"] == slug][:1]
    if match:
        m = match[0]
        if b.get("composio_existing_toolkit") != "yes":
            flags.append({"rule": "composio_toolkit_corrected_to_yes", "fields": ["buildability.composio_existing_toolkit"]})
        b.update(composio_existing_toolkit="yes", composio_slug=m["slug"],
                 composio_evidence=[{"url": composio_catalog.CATALOG_URL, "snippet": m["row"], "check": "exact"}],
                 composio_auth=m["auth"], composio_tools=m["tools"])
        ours = set(rec["auth"]["methods"])
        theirs = {x.lower() for x in m["auth"]}
        if "oauth2" in theirs and "oauth2" not in ours:
            flags.append({"rule": "composio_has_oauth2_we_do_not", "fields": ["auth.methods"]})
        if "api_key" in theirs and not ours & {"api_key", "bearer_token"}:
            flags.append({"rule": "composio_has_api_key_we_do_not", "fields": ["auth.methods"]})
    else:
        if b.get("composio_existing_toolkit") == "yes":
            flags.append({"rule": "composio_toolkit_not_in_catalog", "fields": ["buildability.composio_existing_toolkit"]})
        b.update(composio_existing_toolkit="no", composio_slug=None,
                 composio_evidence=[{"url": composio_catalog.CATALOG_URL,
                                     "snippet": f"Composio supports {look['catalog_size']} toolkits", "check": "catalog_absence"}])
    return flags


def loop1_record(rec: dict) -> dict:
    """Run every deterministic check on one record (mutates it). Returns a summary for metrics."""
    app = rec["app"]
    changed, flags, ev_stats = [], [], {"exact": 0, "repaired": 0, "dropped": 0}
    st = rec["api_surface"]["styles"]
    if len(st) > 1 and "none" in st:  # schema hygiene: 'none' only when there is no API at all
        rec["api_surface"]["styles"] = [x for x in st if x != "none"]
    for g in GROUPS:
        before = len(rec[g]["evidence"])
        rec[g]["evidence"] = verify_evidence(rec[g]["evidence"], app, g)
        for e in rec[g]["evidence"]:
            ev_stats[e["check"]] += 1
        ev_stats["dropped"] += before - len(rec[g]["evidence"])
        if not rec[g]["evidence"] and g != "mcp":
            ch = gate_value(rec, g, "loop1: no evidence snippet could be verified in the fetched pages")
            changed += ch
            if ch:
                flags.append({"rule": "evidence_gate", "fields": ch})
    rec["overview_evidence"] = verify_evidence(rec.get("overview_evidence", []), app, "overview")
    # MCP links must be real MCP pages
    m = rec["mcp"]
    ev_urls = " ".join(e["snippet"] + " " + e["url"] for e in m["evidence"])
    if m["official"] and not (mcp_url_ok(m["official"], app) or m["official"] in ev_urls):
        log_jsonl(VLOG, {"loop": 1, "app": app, "group": "mcp", "check": "mcp_official_url", "result": "fail", "url": m["official"]})
        m["official"] = None; changed.append("mcp.official"); flags.append({"rule": "mcp_url_not_mcp_page", "fields": ["mcp.official"]})
    good = [c for c in m["community"] if isinstance(c, str) and mcp_url_ok(c, app)]
    if len(good) != len(m["community"]):
        log_jsonl(VLOG, {"loop": 1, "app": app, "group": "mcp", "check": "mcp_community_url", "result": "dropped",
                         "dropped": [c for c in m["community"] if c not in good]})
        m["community"] = good; changed.append("mcp.community")
    flags += composio_check(rec)
    flags += consistency(rec)
    for f in flags:
        log_jsonl(VLOG, {"loop": 1, "app": app, "check": "rule", "result": f["rule"], "fields": f["fields"]})
    v = rec.setdefault("verification", {"checks": [], "disagreements": [], "resolved_by": "agent", "human_checked": False})
    v["checks"] = [c for c in v.get("checks", []) if c.get("loop") != 1]
    v["checks"].append({"loop": 1, "evidence": ev_stats, "flags": flags, "changed": changed})
    return {"app": app, "changed": changed, "flags": flags, "evidence": ev_stats}


def run_loop1(ids: list[int]) -> list[dict]:
    results = load_results()
    out = []
    for i in ids:
        if i not in results:
            continue
        r = results[i]
        # always restart Loop 1 from the pass-1 snapshot so re-runs are idempotent
        for k, v in __import__("copy").deepcopy(r["pass1"]).items():
            r[k] = v
        s = loop1_record(r)
        out.append(s)
        print(f"  loop1 [{i:3d}] {r['app']:<26} ev exact={s['evidence']['exact']} repaired={s['evidence']['repaired']} "
              f"dropped={s['evidence']['dropped']} flags={[f['rule'] for f in s['flags']]} changed={s['changed']}")
    save_results(results)
    return out
