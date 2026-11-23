"""Independent AI audit of the review sample (used because the human check was skipped - see logs).

A model that produced none of the answers (AUDIT_MODEL, default opus) judges every row of
human_review/sample.csv: is the pass-1 value right, is the final value right, and what is the correct value.
It reads the cached docs pages behind both agents' evidence. Output goes to human_review/ai_audit.csv -
the human columns in sample.csv are NEVER written by this code (MASTER §4 rule 3).
On the page these numbers are labelled "AI auditor, not human".
"""
from __future__ import annotations

import csv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import extract, fetch, llm
from .common import ROOT, env, load_results

SAMPLE = ROOT / "human_review" / "sample.csv"
OUT = ROOT / "human_review" / "ai_audit.csv"
SYSTEM = ("You are a strict, independent auditor of an API research dataset. You did not produce these answers. "
          "Judge each value against the provided vendor pages and your own knowledge of the vendor's public docs. Output only JSON.")
PROMPT = """App: {app} ({category}; hint {hint}).
For each row judge whether the PASS-1 value and the FINAL value are correct under these definitions.
{definitions}
Correctness rules: one_liner correct if it describes the product. auth.methods correct if it lists the schemes the public API accepts
(api_key vs bearer_token may be interchangeable if docs blur them; missing or extra OAuth2 = wrong). access.status: how a random developer
gets working credentials today. mcp: official must be the vendor's own MCP server (null if none exists); community entries must be MCP servers for this app.
Rows:
{rows}

Vendor pages (fetched by the crawler):
{pages}

Return ONLY {{"judgements": [{{"field": "...", "pass1_correct": "y|n", "final_correct": "y|n", "correct_value": "short", "basis": "pages|knowledge", "why": "one short sentence"}}]}}"""


def audit_app(app_id: int, rows: list[dict], rec: dict) -> list[dict]:
    urls = []
    for g in ("auth", "access", "api_surface", "mcp"):
        urls += [e["url"] for e in rec[g].get("evidence", [])]
        urls += [e["url"] for e in (rec["verification"].get("agent2", {}).get(g) or {}).get("evidence", [])]
    urls += [e["url"] for e in rec.get("overview_evidence", [])]
    seen, pages, budget = set(), [], 30000
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        r = fetch.load(u)
        if not fetch.ok(r):
            continue
        ex = extract.excerpt(fetch.page_text(r).strip(), 4000)
        if budget - len(ex) < 0:
            break
        budget -= len(ex); pages.append((u, ex))
    rtxt = "\n".join(json.dumps({"field": r["field"], "pass1": r["pass1_value"], "final": r["final_value"]}, ensure_ascii=False) for r in rows)
    out, meta = llm.ask_json(PROMPT.format(app=rec["app"], category=rec["category"], hint=rec["hint"], definitions=extract.DEFINITIONS,
                                           rows=rtxt, pages=extract.render_pages(pages)), SYSTEM, model=env("AUDIT_MODEL", "opus"))
    j = {x.get("field"): x for x in out.get("judgements", []) if isinstance(x, dict)}
    res = []
    for r in rows:
        x = j.get(r["field"], {})
        res.append({**{k: r[k] for k in ("app_id", "app", "category", "field", "pass1_value", "final_value", "evidence_url")},
                    "auditor_value": x.get("correct_value", ""), "pass1_correct": str(x.get("pass1_correct", "")).lower()[:1],
                    "final_correct": str(x.get("final_correct", "")).lower()[:1], "basis": x.get("basis", ""), "why": x.get("why", ""),
                    "auditor": meta.get("model", "")})
    return res


def run(workers: int = 8) -> None:
    rows = list(csv.DictReader(SAMPLE.open()))
    res = load_results()
    by_app: dict[int, list[dict]] = {}
    for r in rows:
        by_app.setdefault(int(r["app_id"]), []).append(r)
    out = []
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(audit_app, i, rs, res[i]): i for i, rs in by_app.items()}
        for f in as_completed(futs):
            try:
                out += f.result()
                print(f"  audit [{futs[f]:3d}] done")
            except Exception as e:
                print("  audit error", futs[f], e)
    out.sort(key=lambda r: (int(r["app_id"]), r["field"]))
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader(); w.writerows(out)
    print(f"ai audit: {len(out)} rows -> {OUT}")


if __name__ == "__main__":
    run()
