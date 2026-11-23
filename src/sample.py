"""Loop 4 setup - draw the stratified human-review sample (MASTER §7).

Fixed, printed seed. 3 apps per category (30 apps) x 8 fields, plus - for every app still flagged
needs_human after Loop 3 - the flagged fields. Writes human_review/sample.csv (human columns BLANK)
and human_review/sample.md (checking guide). The agent never fills the human columns (MASTER §4 rule 3).
"""
from __future__ import annotations

import csv
import json
import random

from .common import ROOT, load_results
from .metrics import FIELDS, value

SEED = 20261123
OUT = ROOT / "human_review"
COLS = ["app_id", "app", "category", "field", "pass1_value", "final_value", "evidence_url", "evidence_snippet",
        "human_value", "pass1_correct", "final_correct", "note"]
GROUP = {"one_liner": "overview_evidence", "auth.methods": "auth", "access.status": "access", "api_surface.styles": "api_surface",
         "api_surface.breadth": "api_surface", "mcp": "mcp", "buildability.verdict": "access", "buildability.main_blocker": "access"}


def fmt(v) -> str:
    if isinstance(v, dict):  # mcp
        comm = ", ".join(v.get("community") or []) or "none"
        return f"official: {v.get('official') or 'none'} | community: {comm}"
    if isinstance(v, list):
        return ", ".join(map(str, v))
    return "" if v is None else str(v)


def evidence(rec: dict, field: str) -> list[dict]:
    g = GROUP[field]
    ev = rec.get(g) if g == "overview_evidence" else rec.get(g, {}).get("evidence", [])
    return ev or []


def draw() -> list[dict]:
    res = load_results()
    rng = random.Random(SEED)
    cats: dict[str, list[int]] = {}
    for r in res.values():
        cats.setdefault(r["category"], []).append(r["id"])
    picked = []
    for c in sorted(cats):
        picked += sorted(rng.sample(sorted(cats[c]), 3))
    rows = []
    for i in picked:
        r = res[i]
        for f in FIELDS:
            rows.append(row(r, f))
    extra = [r for r in res.values() if r.get("needs_human") and r["id"] not in picked]
    for r in extra:
        flagged = {u.split(":")[0].strip() for u in r.get("human_reason", "").split(";") if u.strip()}
        for f in [f for f in FIELDS if f in flagged or (f == "mcp" and "mcp.official" in flagged)] or ["access.status"]:
            rows.append(row(r, f))
    return rows, picked, [r["id"] for r in extra]


def row(r: dict, f: str) -> dict:
    ev = evidence(r, f)
    return {"app_id": r["id"], "app": r["app"], "category": r["category"], "field": f,
            "pass1_value": fmt(value(r["pass1"], f)), "final_value": fmt(value(r, f)),
            "evidence_url": ev[0]["url"] if ev else "", "evidence_snippet": ev[0]["snippet"][:300] if ev else "",
            "human_value": "", "pass1_correct": "", "final_correct": "", "note": ""}


GUIDE = """# Human review guide (Loop 4) - for Karan only

Seed: {seed}. Sample: 3 apps per category = {n_strat} apps x 8 fields, plus {n_extra} apps still flagged after Loop 3
(only their flagged fields). Total rows: {n_rows}. Apps: {apps}.

Run `python scripts/review_server.py` and open http://localhost:8765 . For every row, open the evidence link
(and the vendor's docs if needed) and mark **pass1_correct** and **final_correct** (y/n). If a value is wrong,
type the correct value in human_value. The agent never fills these columns.

What counts as correct (judge the value, not the wording):
- one_liner: describes what the product does; minor wording issues are fine.
- auth.methods: every scheme the public API accepts for third-party access is listed and nothing extra.
  A static personal token sent as `Authorization: Bearer` = bearer_token; a key in a header/query = api_key.
  Accept api_key vs bearer_token interchangeably if the doc itself blurs them; mark n if OAuth2 is missing/extra.
- access.status: how a random developer gets working credentials TODAY. free plan / free dev account / OSS = self_serve_free;
  only a time-limited trial = self_serve_trial; must buy a plan = paid_plan_required; workspace admin must enable = admin_approval;
  build/test free but vendor approval for production = app_review; partner programme = partner_gated; talk to sales = contact_sales.
- api_surface.styles: REST/GraphQL/SOAP etc. as documented. breadth: narrow (a few endpoints), moderate, broad (many resources).
- mcp: official = MCP server published by the vendor itself; community = third-party repos. Mark n if a vendor MCP exists but is missing,
  or if a listed URL is not an MCP server for this app.
- buildability.verdict / main_blocker: could Composio build a toolkit today, and what is the single biggest obstacle.
  Judge against the definitions above, not against your preference.
Fastest path: the evidence link first; if it doesn't settle it, the vendor's auth/getting-started page and pricing page.
"""


def run() -> None:
    OUT.mkdir(exist_ok=True)
    csv_path = OUT / "sample.csv"
    if csv_path.exists():
        existing = list(csv.DictReader(csv_path.open()))
        if any((r.get("pass1_correct") or r.get("final_correct")) for r in existing):
            print("sample.csv already has human answers - not overwriting"); return
    rows, picked, extra = draw()
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader(); w.writerows(rows)
    (OUT / "sample.md").write_text(GUIDE.format(seed=SEED, n_strat=len(picked), n_extra=len(extra), n_rows=len(rows),
                                                apps=", ".join(map(str, picked + extra))))
    (OUT / "sample_meta.json").write_text(json.dumps({"seed": SEED, "stratified_apps": picked, "flagged_apps": extra,
                                                      "rows": len(rows)}, indent=1))
    print(f"sample: seed {SEED}, {len(picked)} stratified + {len(extra)} flagged apps, {len(rows)} rows -> {csv_path}")
