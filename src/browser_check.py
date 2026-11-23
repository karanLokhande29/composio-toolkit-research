"""Loop 3 - headless browser + adjudicator, only on what the earlier loops flagged.

Targets per app: fields with a hard disagreement (Loop 2), Loop 1 rule flags, fields still `unknown`,
and any evidence/discovery page that looked JS-rendered to the plain HTTP fetch.
1. Render the relevant pages with headless Chromium (Playwright) - this recovers docs that are
   built client-side and were empty to `requests`.
2. An adjudicator model (ADJUDICATOR_MODEL) sees the two candidate answers with their evidence and the
   rendered page text, and must answer each disputed field with a fresh verbatim snippet.
3. The snippet is checked deterministically (same code as Loop 1). Verified -> the value becomes final,
   resolved_by="browser". Not verifiable -> needs_human=true with the reason (goes to Karan's sample).
Serves: R12 (browser loop), R11/R13 (needs_human feeds the human sample).
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import discover, extract, fetch, llm, verify
from .common import RAW, VLOG, env, load_results, log_jsonl, save_results, write_json

SYSTEM = "You are the final adjudicator for an API research dataset. Use only the provided pages. Output only JSON."
PROMPT = """App: {app} ({category}; hint {hint})
Two independent research agents disagree or could not verify some fields. Decide each field below from the pages.

{definitions}

{evidence_rules}

DISPUTED FIELDS (candidate answers, with their evidence):
{disputes}

PAGES (rendered with a headless browser where needed):
{pages}

Return ONLY:
{{"decisions": [{{"field": "<field name exactly as above>", "value": <value in the schema's type: list for auth.methods / api_surface.styles, string otherwise, null allowed for mcp.official>,
   "evidence": [{{"url": "...", "snippet": "verbatim"}}], "reason": "one sentence"}}]}}
If the pages cannot settle a field, return value "unknown" and say why in reason."""

FIELD_GROUP = {"auth.methods": "auth", "access.status": "access", "api_surface.styles": "api_surface",
               "api_surface.breadth": "api_surface", "mcp.official": "mcp", "buildability.verdict": "buildability",
               "buildability.main_blocker": "buildability"}


def targets(rec: dict) -> list[str]:
    v = rec["verification"]
    f = {d["field"] for d in v.get("disagreements", []) if d["level"] in ("hard", "gap")}
    for c in v.get("checks", []):
        if c.get("loop") == 1:
            for fl in c.get("flags", []):
                if fl["rule"] not in ("composio_toolkit_corrected_to_yes",):
                    f.update(x for x in fl["fields"] if x in FIELD_GROUP)
    if rec["auth"]["methods"] == ["unknown"]:
        f.add("auth.methods")
    if rec["access"]["status"] == "unknown":
        f.add("access.status")
    if rec["api_surface"]["breadth"] == "unknown":
        f.add("api_surface.breadth")
    return sorted(f)


def get(rec: dict, field: str):
    g, k = field.split(".")
    return rec[g][k]


def put(rec: dict, field: str, value) -> None:
    g, k = field.split(".")
    rec[g][k] = value


def pages_for(rec: dict, fields: list[str]) -> list[str]:
    urls = []
    a2 = rec["verification"].get("agent2", {})
    for f in fields:
        g = FIELD_GROUP[f]
        if g == "buildability":
            g = "access"
        for src in (rec, a2):
            for e in (src.get(g, {}) or {}).get("evidence", []):
                urls.append(e["url"])
    for tag in ("agent1", "agent2"):
        d = discover.load_discovery(rec["id"], tag) or {"urls": []}
        for u in d["urls"]:
            if u.get("purpose") in ("auth", "access", "pricing", "api_reference", "mcp_official") or u.get("js_rendered"):
                urls.append(u["url"])
    seen, out = set(), []
    for u in urls:
        if u not in seen and "docs.composio.dev/toolkits.md" not in u:
            seen.add(u); out.append(u)
    return out[:8]


def adjudicate(rec: dict) -> dict | None:
    fields = targets(rec)
    if not fields:
        return None
    urls = pages_for(rec, fields)
    for u in urls:
        fetch.render(u)
    pages = []
    budget = 70000
    for u in urls:
        r = fetch.load(u)
        if not fetch.ok(r):
            continue
        ex = extract.excerpt(fetch.page_text(r).strip(), 7000)
        if budget - len(ex) < 0:
            break
        budget -= len(ex); pages.append((u, ex))
    a2 = rec["verification"].get("agent2", {})
    disputes = []
    for f in fields:
        g = FIELD_GROUP[f]
        disputes.append(json.dumps({"field": f, "agent1": get(rec, f) if g in rec else None,
                                    "agent2": (a2.get(g) or {}).get(f.split(".")[1]),
                                    "agent1_evidence": rec.get(g, {}).get("evidence", [])[:3] if g != "buildability" else [],
                                    "agent2_evidence": (a2.get(g) or {}).get("evidence", [])[:3] if g != "buildability" else []},
                                   ensure_ascii=False))
    prompt = PROMPT.format(app=rec["app"], category=rec["category"], hint=rec["hint"], definitions=extract.DEFINITIONS,
                           evidence_rules=extract.EVIDENCE_RULES, disputes="\n".join(disputes),
                           pages=extract.render_pages(pages))
    out, meta = llm.ask_json(prompt, SYSTEM, model=env("ADJUDICATOR_MODEL", "sonnet"))
    write_json(RAW / f"{rec['id']:03d}_adjudicator.json", {"fields": fields, "pages": [u for u, _ in pages], "meta": meta, "output": out})
    return {"fields": fields, "out": out, "pages": [u for u, _ in pages], "meta": meta}


def apply(rec: dict, res: dict) -> tuple[list[str], list[str]]:
    changed, unresolved = [], []
    decisions = {d.get("field"): d for d in res["out"].get("decisions", []) if isinstance(d, dict)}
    for f in res["fields"]:
        d = decisions.get(f)
        g = FIELD_GROUP[f]
        if not d or d.get("value") in ("unknown", None, [], ["unknown"]) and f != "mcp.official":
            unresolved.append(f"{f}: {(d or {}).get('reason', 'no decision')}")
            continue
        ev = verify.verify_evidence(d.get("evidence", []), rec["app"], g, loop=3)
        if not ev:
            unresolved.append(f"{f}: adjudicator evidence did not verify")
            continue
        val = d["value"]
        if f in ("auth.methods", "api_surface.styles"):
            val = sorted(set(v.lower() for v in (val if isinstance(val, list) else [val])))
        if f == "mcp.official" and val and not verify.mcp_url_ok(val, rec["app"]) and \
                not any(val in e["snippet"] for e in ev):
            unresolved.append(f"{f}: MCP URL could not be verified"); continue
        old = get(rec, f)
        if old != val:
            put(rec, f, val); changed.append(f)
        if g != "buildability":
            rec[g]["evidence"] = ev + [e for e in rec[g]["evidence"] if e["url"] not in {x["url"] for x in ev}][:2]
        else:
            rec["buildability"]["rationale"] = d.get("reason") or rec["buildability"]["rationale"]
        log_jsonl(VLOG, {"loop": 3, "app": rec["app"], "check": "adjudicate", "field": f, "old": old, "new": val,
                         "reason": d.get("reason", "")})
    return changed, unresolved


def run(ids: list[int], workers: int = 3) -> None:
    results = load_results()
    todo = [results[i] for i in ids if i in results and targets(results[i])]
    print(f"loop3: browser + adjudicator on {len(todo)} apps")
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(adjudicate, r): r for r in todo}
        for fut in as_completed(futs):
            rec = futs[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = None
                rec["needs_human"], rec["human_reason"] = True, f"loop3 error: {str(e)[:120]}"
            v = rec["verification"]
            v["checks"] = [c for c in v["checks"] if c.get("loop") != 3]
            if res:
                changed, unresolved = apply(rec, res)
                v["checks"].append({"loop": 3, "fields": res["fields"], "changed": changed, "unresolved": unresolved,
                                    "rendered_pages": res["pages"]})
                v["resolved_by"] = "browser" if not unresolved else "unresolved"
                rec["needs_human"] = bool(unresolved)
                rec["human_reason"] = "; ".join(unresolved)[:400]
                print(f"  loop3 [{rec['id']:3d}] {rec['app']:<26} fields={res['fields']} changed={changed} unresolved={len(unresolved)}")
            save_results(results)
