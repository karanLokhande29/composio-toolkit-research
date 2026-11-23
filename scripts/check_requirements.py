#!/usr/bin/env python3
"""Continuous requirements check (MASTER.md §3).

  python scripts/check_requirements.py                # all phases
  python scripts/check_requirements.py --phase 3      # only phases <= 3 are "reached"; later -> NOT_YET
  python scripts/check_requirements.py --apps 1-5     # scope the data checks (pilot)
  python scripts/check_requirements.py --write        # also rewrite REQUIREMENTS_STATUS.md
  python scripts/check_requirements.py --selftest

Prints a table (ID, status, detail), writes reports/requirements_check.json and exits non-zero if any
reached AUTO check FAILs. MANUAL items are never self-certified: they show MANUAL_PENDING.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
IST = timezone(timedelta(hours=5, minutes=30))

# R-ID -> (phase in which it becomes checkable, title)
REQ = {
    "R1": (0, "All 100 apps present, ids 1-100, unique"),
    "R2": (1, "Category + one-line description"),
    "R3": (1, "Auth method(s) or unknown+reason"),
    "R4": (1, "Access status or unknown+reason"),
    "R5": (1, "API surface: styles, breadth, MCP"),
    "R6": (1, "Buildability verdict + blocker + rationale"),
    "R7": (1, "Evidence URL fetched + snippet in cached page"),
    "R8": (1, "'And more' fields captured"),
    "R9": (6, "Patterns computed in code; headlines cite patterns.json"),
    "R10": (1, "Research by agent; Composio used where possible"),
    "R11": (1, "Human interventions logged + shown on page"),
    "R12": (3, "Verification loops 1-3 implemented with logs"),
    "R13": (4, "Human cross-check sheet filled by Karan"),
    "R14": (5, "Accuracy pass1 vs final from logged data, hits+misses"),
    "R15": (7, "One self-contained HTML page, mobile"),
    "R16": (7, "Page sections present in order"),
    "R17": (7, "Embedded JSON + results.json, patterns.json, llms.txt"),
    "R18": (7, "Honesty: misses/unresolved/failures on page"),
    "R19": (2, "No paid accounts; gated apps with evidence"),
    "R20": (1, "docs/INTERVIEW_NOTES.md explains components"),
    "R21": (8, "Deployed, live URL returns 200"),
    "R22": (8, "README: setup, .env.example, run, architecture, verification"),
    "R23": (9, "Submitted before 23:00 IST"),
    "R24": (0, "No secrets committed"),
}
MANUAL_ONLY = {"R10", "R19", "R23"}
SECTIONS = ["headline", "wins-outreach", "matrix", "agent", "human-needed", "verification", "proof", "process", "limitations"]


def norm(s: str) -> str:
    s = s.replace(" ", " ").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"[`*]|\\_", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def load_cache(url: str):
    import hashlib
    p = ROOT / "cache" / f"{hashlib.sha1(url.encode()).hexdigest()[:16]}.json.gz"
    if not p.exists():
        return None
    with gzip.open(p, "rt") as f:
        return json.load(f)


def page_text(rec) -> str:
    return (rec.get("title") or "") + "\n" + (rec.get("text") or "") + "\n" + (rec.get("browser_text") or "")


def results(ids):
    p = ROOT / "data" / "results.json"
    if not p.exists():
        return None
    rows = json.loads(p.read_text())
    return [r for r in rows if not ids or r["id"] in ids]


def ev_ok(e) -> bool:
    rec = load_cache(e.get("url", ""))
    if not rec or not (rec.get("status") == 200 or rec.get("browser_status") == 200):
        return False
    return norm(e.get("snippet", "")) in norm(page_text(rec)) if e.get("snippet") else False


def check_data(rid, rows, expected_n):
    if rows is None:
        return "FAIL", "data/results.json missing"
    bad = []
    for r in rows:
        if rid == "R2":
            if not r.get("category") or not r.get("one_liner"):
                bad.append(r["app"])
        elif rid == "R3":
            m = r["auth"]["methods"]
            if not m or (m == ["unknown"] and not r.get("unknown_reasons", {}).get("auth")):
                bad.append(r["app"])
        elif rid == "R4":
            s = r["access"]["status"]
            if not s or (s == "unknown" and not r.get("unknown_reasons", {}).get("access")):
                bad.append(r["app"])
        elif rid == "R5":
            a = r["api_surface"]
            if not a.get("styles") or not a.get("breadth") or "official" not in r["mcp"] or "community" not in r["mcp"]:
                bad.append(r["app"])
        elif rid == "R6":
            b = r["buildability"]
            if not b.get("verdict") or not b.get("main_blocker") or not b.get("rationale"):
                bad.append(r["app"])
        elif rid == "R7":
            for g, field in (("auth", "methods"), ("access", "status"), ("api_surface", "breadth")):
                val = r[g][field]
                if val in ("unknown", ["unknown"]):
                    continue
                if not any(ev_ok(e) for e in r[g]["evidence"]):
                    bad.append(f"{r['app']}:{g}")
            if (r["mcp"]["official"] or r["mcp"]["community"]) and not (any(ev_ok(e) for e in r["mcp"]["evidence"]) or r["mcp"]["community"]):
                bad.append(f"{r['app']}:mcp")
            if not any(ev_ok(e) for e in r["buildability"].get("composio_evidence", [])) and \
                    r["buildability"].get("composio_existing_toolkit") == "yes":
                bad.append(f"{r['app']}:composio")
        elif rid == "R8":
            a, b = r["api_surface"], r["buildability"]
            if not all(k in a for k in ("openapi_spec_url", "webhooks", "rate_limit_note")) or "dev_sandbox" not in r["access"] \
                    or b.get("composio_existing_toolkit") not in ("yes", "no", "unknown"):
                bad.append(r["app"])
    n = len(rows)
    if rid in ("R2", "R3", "R4", "R5", "R6", "R7", "R8") and n < expected_n:
        return "FAIL", f"only {n}/{expected_n} apps in results.json"
    if bad:
        return "FAIL", f"{len(bad)} problems: {', '.join(bad[:8])}"
    return "PASS", f"{n} apps ok"


def human_rows():
    p = ROOT / "human_review" / "sample.csv"
    if not p.exists():
        return None
    return list(csv.DictReader(p.open()))


def run(phase: int, ids, live_url: str | None):
    out = {}
    rows = results(ids)
    expected = len(ids) if ids else 100
    for rid, (ph, title) in REQ.items():
        if ph > phase:
            out[rid] = ("NOT_YET", f"phase {ph} not reached")
            continue
        if rid in MANUAL_ONLY:
            out[rid] = ("MANUAL_PENDING", "Karan must confirm")
            continue
        try:
            out[rid] = globals()["c_" + rid](rows, expected, phase, live_url) if "c_" + rid in globals() else check_data(rid, rows, expected)
        except Exception as e:
            out[rid] = ("FAIL", f"checker error: {e}")
    return out


def c_R1(rows, expected, phase, live):
    import yaml
    apps = yaml.safe_load((ROOT / "apps.yaml").read_text())
    ids = [a["id"] for a in apps]
    ok = sorted(ids) == list(range(1, 101)) and len(set(ids)) == 100
    detail = "apps.yaml 100 unique ids"
    if ok and rows is not None and phase >= 2:
        rids = [r["id"] for r in rows]
        if len(rids) != len(set(rids)):
            return "FAIL", "duplicate ids in results.json"
        detail += f"; results.json {len(rids)} unique"
    return ("PASS" if ok else "FAIL"), detail


def c_R9(rows, expected, phase, live):
    p = ROOT / "data" / "patterns.json"
    if not p.exists():
        return "FAIL", "data/patterns.json missing"
    pat = json.loads(p.read_text())
    need = ["auth_distribution", "access_by_category", "blocker_frequency", "mcp_coverage", "easy_wins", "needs_outreach", "headlines"]
    miss = [k for k in need if k not in pat]
    if miss:
        return "FAIL", f"missing keys {miss}"
    for h in pat["headlines"]:
        val = pat
        for k in h["key"].split("."):
            val = val[k]
        if str(val) not in h["text"] and f"{val}" not in h["text"]:
            return "FAIL", f"headline number not found in text: {h['key']}={val}"
    return "PARTIAL" if False else "PASS", f"{len(pat['headlines'])} headlines map to patterns.json (MANUAL: insight quality)"


def c_R11(rows, expected, phase, live):
    p = ROOT / "logs" / "human_interventions.md"
    if not p.exists():
        return "FAIL", "missing"
    n = sum(1 for ln in p.read_text().splitlines() if ln.startswith("| 20"))
    if n == 0:
        return "FAIL", "no entries"
    if phase >= 7:
        html = (ROOT / "site" / "index.html")
        if not html.exists() or 'id="human-needed"' not in html.read_text():
            return "FAIL", "not shown on page"
    return "PASS", f"{n} entries (MANUAL: completeness)"


def c_R12(rows, expected, phase, live):
    p = ROOT / "logs" / "verification_log.jsonl"
    if not p.exists():
        return "FAIL", "verification_log.jsonl missing"
    loops = {}
    for ln in p.open():
        try:
            loops[json.loads(ln).get("loop")] = loops.get(json.loads(ln).get("loop"), 0) + 1
        except Exception:
            pass
    miss = [l for l in (1, 2, 3) if not loops.get(l)]
    if miss:
        return "FAIL", f"no log lines for loop(s) {miss}"
    return "PASS", f"log lines per loop {dict(sorted(loops.items()))}"


def c_R13(rows, expected, phase, live):
    hr = human_rows()
    if hr is None:
        return "FAIL", "human_review/sample.csv missing"
    blanks = [r for r in hr if not (r.get("pass1_correct") or "").strip() or not (r.get("final_correct") or "").strip()]
    if blanks:
        return "MANUAL_PENDING", f"sheet generated: {len(hr)} rows, {len(blanks)} still blank (Karan to fill)"
    apps = {r["app_id"] for r in hr}
    return "PASS", f"{len(hr)} rows over {len(apps)} apps filled by Karan"


def c_R14(rows, expected, phase, live):
    p = ROOT / "data" / "metrics.json"
    if not p.exists():
        return "FAIL", "metrics.json missing"
    m = json.loads(p.read_text())
    acc = m.get("accuracy")
    if not acc or acc.get("status") != "computed":
        return "MANUAL_PENDING", "waiting for human sheet"
    if "misses" not in acc or "hits" not in acc:
        return "FAIL", "hits/misses not listed"
    return "PASS", f"pass1 {acc['overall']['pass1']:.1%} -> automated {acc['overall']['final_automated']:.1%}"


def _html():
    p = ROOT / "site" / "index.html"
    return p.read_text() if p.exists() else None


def c_R15(rows, expected, phase, live):
    h = _html()
    if h is None:
        return "FAIL", "site/index.html missing"
    ext = re.findall(r'<(?:script|link)[^>]+(?:src|href)="(https?://[^"]+)"', h)
    if ext:
        return "FAIL", f"external runtime deps: {ext[:3]}"
    if 'name="viewport"' not in h:
        return "FAIL", "no viewport meta"
    return "PASS", f"self-contained, {len(h)//1024} KB (MANUAL: 2-minute readability)"


def c_R16(rows, expected, phase, live):
    h = _html()
    if h is None:
        return "FAIL", "page missing"
    pos = [h.find(f'id="{s}"') for s in SECTIONS]
    if -1 in pos:
        return "FAIL", f"missing sections {[s for s, p in zip(SECTIONS, pos) if p == -1]}"
    if pos != sorted(pos):
        return "FAIL", "sections out of order"
    return "PASS", "all 9 section ids in order"


def c_R17(rows, expected, phase, live):
    h = _html()
    if h is None or '<script type="application/json" id="data">' not in h:
        return "FAIL", "embedded JSON missing"
    miss = [f for f in ("results.json", "patterns.json", "llms.txt") if not (ROOT / "site" / f).exists()]
    return ("FAIL", f"missing {miss}") if miss else ("PASS", "embedded JSON + 3 files")


def c_R18(rows, expected, phase, live):
    h = _html()
    if h is None:
        return "FAIL", "page missing"
    need = ['id="misses"', 'id="unresolved"', 'id="failures"']
    miss = [n for n in need if n not in h]
    return ("FAIL", f"missing honesty blocks {miss}") if miss else ("PASS", "misses/unresolved/failures blocks present (MANUAL: honesty)")


def c_R20(rows, expected, phase, live):
    p = ROOT / "docs" / "INTERVIEW_NOTES.md"
    if not p.exists() or len(p.read_text()) < 500:
        return "FAIL", "missing or too short"
    return "PASS", f"{len(p.read_text().split())} words (MANUAL: Karan can explain)"


def c_R21(rows, expected, phase, live):
    url = live or (ROOT / "site" / "LIVE_URL").read_text().strip() if (ROOT / "site" / "LIVE_URL").exists() or live else None
    if not url:
        return "FAIL", "no live URL recorded in site/LIVE_URL"
    import requests
    try:
        code = requests.get(url, timeout=20).status_code
    except Exception as e:
        return "FAIL", f"{url}: {e}"
    return ("PASS" if code == 200 else "FAIL"), f"{url} -> {code}"


def c_R22(rows, expected, phase, live):
    p = ROOT / "README.md"
    if not p.exists():
        return "FAIL", "README missing"
    t = p.read_text().lower()
    need = ["setup", ".env.example", "run.py", "architecture", "verification"]
    miss = [n for n in need if n not in t]
    if not (ROOT / ".env.example").exists():
        miss.append(".env.example file")
    return ("FAIL", f"missing {miss}") if miss else ("PASS", "all README sections present")


def c_R24(rows, expected, phase, live):
    gi = (ROOT / ".gitignore").read_text() if (ROOT / ".gitignore").exists() else ""
    if ".env" not in gi.split():
        return "FAIL", ".env not in .gitignore"
    try:
        tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    except Exception:
        tracked = []
    if ".env" in tracked:
        return "FAIL", ".env is tracked by git"
    pat = re.compile(r"(sk-ant-[A-Za-z0-9_-]{20,}|gh[opsu]_[A-Za-z0-9]{30,}|ak_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})")
    hits = []
    for f in tracked:
        p = ROOT / f
        if p.is_file() and p.stat().st_size < 3_000_000 and p.suffix not in (".gz",):
            try:
                if pat.search(p.read_text(errors="ignore")):
                    hits.append(f)
            except Exception:
                pass
    hist = subprocess.run(["git", "log", "-p", "--all"], cwd=ROOT, capture_output=True, text=True).stdout if tracked else ""
    if pat.search(hist or ""):
        hits.append("git history")
    return ("FAIL", f"possible secrets in {hits}") if hits else ("PASS", f".env ignored; {len(tracked)} tracked files + history scanned clean")


def write_status(res):
    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M")
    lines = ["# REQUIREMENTS_STATUS", "", "Generated by `python scripts/check_requirements.py --write`. MANUAL items are never self-certified.", "",
             "| ID | requirement | status | evidence / detail | last checked (IST) |", "|---|---|---|---|---|"]
    for rid, (st, det) in res.items():
        lines.append(f"| {rid} | {REQ[rid][1]} | {st} | {det.replace('|', '/')} | {now} |")
    (ROOT / "REQUIREMENTS_STATUS.md").write_text("\n".join(lines) + "\n")


def selftest():
    assert norm("A  `b`\n**c**") == "a b c"
    assert c_R1(None, 100, 0, None)[0] == "PASS"
    print("selftest ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", type=int, default=9)
    ap.add_argument("--apps", default="")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--live-url")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    from src.common import parse_ids, clock_line
    ids = parse_ids(a.apps) if a.apps else None
    res = run(a.phase, ids, a.live_url)
    print(clock_line())
    print(f"{'ID':<5}{'STATUS':<16}DETAIL")
    for rid, (st, det) in res.items():
        print(f"{rid:<5}{st:<16}{det[:110]}")
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "requirements_check.json").write_text(json.dumps(
        {"checked_at": datetime.now(IST).isoformat(timespec="seconds"), "phase": a.phase,
         "results": {k: {"status": s, "detail": d} for k, (s, d) in res.items()}}, indent=1))
    if a.write:
        write_status(res)
    fails = [k for k, (s, _) in res.items() if s == "FAIL"]
    if fails:
        print("FAIL:", fails)
        sys.exit(1)


if __name__ == "__main__":
    main()
