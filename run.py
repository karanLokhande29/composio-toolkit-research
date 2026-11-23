#!/usr/bin/env python3
"""CLI for the research agent.

  python run.py --apps 1-5 --stage discover     # find + fetch docs pages (agent 1)
  python run.py --apps 1-5 --stage extract      # pass 1 extraction -> data/results.json (+ pass1 snapshot)
  python run.py --apps 1-100 --stage verify     # loops 1-3 (deterministic, second agent, browser)
  python run.py --stage analyze                 # patterns.json + metrics.json
  python run.py --stage page                    # site/index.html + machine-readable files
  python run.py --apps 1-100 --stage all        # everything above, in order
Resumable: discover/extract skip apps already done unless --force.
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from src import discover, extract
from src.common import clock_line, env, load_apps, load_results, parse_ids, save_results


def stage_discover(apps, force, workers):
    model = env("PASS1_MODEL", "haiku")
    todo = [a for a in apps if force or not discover.load_discovery(a["id"])]
    print(f"discover: {len(todo)} apps to do ({len(apps) - len(todo)} cached)")

    def one(a):
        d = discover.discover_and_fetch(a, model=model, use_search=env("DISCOVERY_SEARCH", "0") == "1")
        return a, d

    with ThreadPoolExecutor(workers) as ex:
        for fut in as_completed([ex.submit(one, a) for a in todo]):
            try:
                a, d = fut.result()
                ok = sum(1 for u in d["urls"] if u["ok"])
                print(f"  [{a['id']:3d}] {a['app']:<28} urls={len(d['urls']):2d} ok={ok:2d}")
            except Exception as e:
                print("  discover error:", e)


def stage_extract(apps, force, workers):
    model = env("PASS1_MODEL", "haiku")
    results = load_results()
    todo = [a for a in apps if force or a["id"] not in results or results[a["id"]].get("_meta", {}).get("error")]
    print(f"extract: {len(todo)} apps to do")

    def one(a):
        disc = discover.load_discovery(a["id"])
        if not disc:
            disc = discover.discover_and_fetch(a, model=model, use_search=env("DISCOVERY_SEARCH", "0") == "1")
        rec = extract.extract(a, disc, model=model)
        if rec["_meta"].get("error"):  # retry once
            rec = extract.extract(a, disc, model=model)
        rec["pass1"] = extract.snapshot(rec)          # honest first pass, never edited later
        rec["verification"] = {"checks": [], "disagreements": [], "resolved_by": "agent", "human_checked": False}
        rec["needs_human"], rec["human_reason"] = False, ""
        return rec

    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(one, a) for a in todo]
        for fut in as_completed(futs):
            rec = fut.result()
            results[rec["id"]] = rec
            save_results(results, only=[rec["id"]])
            m = rec["_meta"]
            print(f"  [{rec['id']:3d}] {rec['app']:<28} auth={','.join(rec['auth']['methods']):<18} "
                  f"access={rec['access']['status']:<18} verdict={rec['buildability']['verdict']:<18} "
                  f"pages={m['pages_used']} {m.get('seconds')}s ${m.get('cost_usd') or 0:.3f} {'ERR ' + m['error'] if m.get('error') else ''}")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--apps", default="1-100")
    p.add_argument("--stage", default="all",
                   choices=["discover", "fetch", "extract", "verify", "loop1", "loop2", "loop3", "analyze", "page", "all"])
    p.add_argument("--force", action="store_true")
    p.add_argument("--workers", type=int, default=int(env("WORKERS", "6")))
    args = p.parse_args(argv)
    apps = load_apps(parse_ids(args.apps))
    print(clock_line())
    t0 = time.time()
    st = args.stage
    if st in ("discover", "fetch", "all"):
        stage_discover(apps, args.force, args.workers)
    if st in ("extract", "all"):
        stage_extract(apps, args.force, args.workers)
    if st in ("verify", "loop1", "all"):
        from src import verify
        verify.run_loop1([a["id"] for a in apps])
    if st in ("verify", "loop2", "all"):
        from src import second_agent
        second_agent.run([a["id"] for a in apps], workers=args.workers)
    if st in ("verify", "loop3", "all"):
        from src import browser_check
        browser_check.run([a["id"] for a in apps], workers=max(2, args.workers // 2))
    if st in ("analyze", "all"):
        from src import analyze, metrics
        metrics.run(); analyze.run()
    if st in ("page", "all"):
        from src import build_page
        build_page.run()
    print(f"done in {time.time() - t0:.0f}s | {clock_line()}")


if __name__ == "__main__":
    sys.exit(main())
