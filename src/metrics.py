"""Metrics from logged data only (R14): coverage, what each loop did, cost/time, and - once Karan
has filled human_review/sample.csv - field-level accuracy for pass 1 vs after the automated loops.

Accuracy definitions (on the human sample):
  pass1 accuracy           = share of sampled (app, field) rows where Karan marked pass1_correct = y
  final (automated) acc.   = share where Karan marked final_correct = y  (final = after loops 1-3)
  after human corrections  = rows Karan corrected are replaced with his value -> reported as a count of
                             corrections, never mixed into the automated number.
A miss is any row with final_correct = n (and pass-1 misses are listed with the loop that fixed them).
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict

from .common import DATA, LOGS, ROOT, VLOG, load_results, write_json

SAMPLE = ROOT / "human_review" / "sample.csv"
FIELDS = ["one_liner", "auth.methods", "access.status", "api_surface.styles", "api_surface.breadth", "mcp",
          "buildability.verdict", "buildability.main_blocker"]


def value(rec: dict, field: str):
    if field == "one_liner":
        return rec.get("one_liner")
    if field == "mcp":
        m = rec["mcp"]
        return {"official": m.get("official"), "community": m.get("community", [])[:2]}
    g, k = field.split(".")
    return rec.get(g, {}).get(k)


def coverage(rows, which: str):
    out = {}
    for f in ("auth.methods", "access.status", "api_surface.breadth"):
        vals = [value(r if which == "final" else r["pass1"], f) for r in rows]
        unk = sum(v in ("unknown", ["unknown"], None) for v in vals)
        out[f] = {"filled": len(vals) - unk, "unknown": unk}
    return out


def loop_stats(rows):
    l1 = {"evidence_exact": 0, "evidence_repaired": 0, "evidence_dropped": 0, "flags": Counter(), "fields_changed": 0, "apps_changed": 0}
    l2 = {"hard": Counter(), "soft": Counter(), "gap": Counter(), "fields_filled": 0, "apps_with_hard": 0}
    l3 = {"apps": 0, "fields_examined": 0, "fields_changed": 0, "unresolved": 0, "changed_by_field": Counter()}
    for r in rows:
        for c in r["verification"].get("checks", []):
            if c["loop"] == 1:
                e = c["evidence"]
                l1["evidence_exact"] += e["exact"]; l1["evidence_repaired"] += e["repaired"]; l1["evidence_dropped"] += e["dropped"]
                for f in c["flags"]:
                    l1["flags"][f["rule"]] += 1
                l1["fields_changed"] += len(c["changed"]); l1["apps_changed"] += bool(c["changed"])
            elif c["loop"] == 2:
                l2["fields_filled"] += len(c["changed"]); l2["apps_with_hard"] += bool(c.get("hard"))
            elif c["loop"] == 3:
                l3["apps"] += 1; l3["fields_examined"] += len(c["fields"]); l3["fields_changed"] += len(c["changed"])
                l3["unresolved"] += len(c["unresolved"])
                for f in c["changed"]:
                    l3["changed_by_field"][f] += 1
        for d in r["verification"].get("disagreements", []):
            l2[d["level"]][d["field"]] += 1
    for d in (l1, l2, l3):
        for k, v in list(d.items()):
            if isinstance(v, Counter):
                d[k] = dict(v.most_common())
    total_ev = l1["evidence_exact"] + l1["evidence_repaired"] + l1["evidence_dropped"]
    l1["evidence_total"] = total_ev
    l1["evidence_verified_pct"] = round(100 * (l1["evidence_exact"] + l1["evidence_repaired"]) / total_ev, 1) if total_ev else 0
    return l1, l2, l3


def changed_by_loops(rows):
    keyf = ["auth.methods", "access.status", "api_surface.styles", "api_surface.breadth", "buildability.verdict",
            "buildability.main_blocker"]
    apps, fields = 0, Counter()
    for r in rows:
        ch = [f for f in keyf if value(r, f) != value(r["pass1"], f)]
        if value(r, "mcp")["official"] != value(r["pass1"], "mcp")["official"]:
            ch.append("mcp.official")
        apps += bool(ch)
        for f in ch:
            fields[f] += 1
    return {"apps_changed": apps, "apps_changed_pct": round(100 * apps / len(rows)) if rows else 0, "by_field": dict(fields.most_common())}


def which_loop(rec: dict, field: str) -> str:
    """Name the loop(s) whose logged `changed` list contains this field (for the misses table)."""
    names = {1: "loop 1 (deterministic)", 2: "loop 2 (second agent)", 3: "loop 3 (browser + adjudicator)"}
    hits = []
    for c in rec["verification"].get("checks", []):
        ch = c.get("changed", [])
        if any(x == field or x.startswith(field.split(".")[0] + ".") and field == "mcp" for x in ch) or field in ch:
            hits.append(names[c["loop"]])
    return ", ".join(hits) or "none"


def accuracy(results):
    if not SAMPLE.exists():
        return {"status": "no_sheet"}
    rows = list(csv.DictReader(SAMPLE.open()))
    filled = [r for r in rows if r.get("pass1_correct", "").strip().lower() in ("y", "n") and r.get("final_correct", "").strip().lower() in ("y", "n")]
    if not rows or len(filled) < len(rows):
        return {"status": "pending_human", "rows": len(rows), "filled": len(filled)}
    yes = lambda r, k: r[k].strip().lower() == "y"
    per_field, per_cat = defaultdict(lambda: [0, 0, 0]), defaultdict(lambda: [0, 0, 0])
    hits, misses, fixed, broke = [], [], [], []
    for r in filled:
        rec = results[int(r["app_id"])]
        for d in (per_field[r["field"]], per_cat[rec["category"]]):
            d[0] += 1; d[1] += yes(r, "pass1_correct"); d[2] += yes(r, "final_correct")
        item = {"app": r["app"], "field": r["field"], "pass1": r["pass1_value"], "final": r["final_value"],
                "human": r.get("human_value", ""), "note": r.get("note", "")}
        if yes(r, "final_correct"):
            hits.append(item)
            if not yes(r, "pass1_correct"):
                fixed.append(item | {"caught_by": which_loop(rec, r["field"])})
        else:
            misses.append(item | {"caught_by": "not caught" if not yes(r, "pass1_correct") else "regressed by " + which_loop(rec, r["field"])})
            if yes(r, "pass1_correct"):
                broke.append(item)
    n = len(filled)
    p1 = sum(yes(r, "pass1_correct") for r in filled) / n
    fa = sum(yes(r, "final_correct") for r in filled) / n
    return {"status": "computed", "rows": n, "apps": len({r["app_id"] for r in filled}),
            "overall": {"pass1": round(p1, 4), "final_automated": round(fa, 4),
                        "human_corrections": len(misses), "after_human": 1.0},
            "per_field": {k: {"n": v[0], "pass1": round(v[1] / v[0], 3), "final": round(v[2] / v[0], 3)} for k, v in per_field.items()},
            "per_category": {k: {"n": v[0], "pass1": round(v[1] / v[0], 3), "final": round(v[2] / v[0], 3)} for k, v in per_cat.items()},
            "hits": hits, "misses": misses, "fixed_by_loops": fixed, "regressed_by_loops": broke}


def cost_time():
    p = LOGS / "run_log.jsonl"
    if not p.exists():
        return {}
    tot, secs, calls = 0.0, 0.0, Counter()
    for ln in p.open():
        d = json.loads(ln)
        tot += d.get("cost_usd") or 0
        secs += d.get("seconds") or 0
        calls[f"{d.get('stage')}:{d.get('agent')}"] += 1
    return {"llm_cost_usd_reported": round(tot, 2), "llm_seconds": round(secs), "calls": dict(calls)}


def run() -> dict:
    results = load_results()
    rows = [results[k] for k in sorted(results)]
    l1, l2, l3 = loop_stats(rows)
    m = {"n_apps": len(rows),
         "coverage": {"pass1": coverage(rows, "pass1"), "final": coverage(rows, "final")},
         "loop1": l1, "loop2": l2, "loop3": l3,
         "changed_by_automated_loops": changed_by_loops(rows),
         "needs_human": [{"id": r["id"], "app": r["app"], "reason": r["human_reason"]} for r in rows if r.get("needs_human")],
         "resolved_by": dict(Counter(r["verification"].get("resolved_by", "agent") for r in rows)),
         "cost_time": cost_time(),
         "accuracy": accuracy(results)}
    write_json(DATA / "metrics.json", m)
    print(f"metrics: changed by loops {m['changed_by_automated_loops']['apps_changed']} apps; accuracy status {m['accuracy']['status']}")
    return m
