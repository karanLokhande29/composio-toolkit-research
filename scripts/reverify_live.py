#!/usr/bin/env python3
"""Live re-verification (no API keys): for the chosen apps, re-fetch every evidence URL from the vendor
right now (bypassing the cache) and check the quoted snippet is still on the page.

  python scripts/reverify_live.py --apps 1-5

Writes reports/live_reverify.json and prints a summary. This is the GitHub Actions 'verify-only' mode.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402
from src.common import norm_ws, parse_ids  # noqa: E402
from src.fetch import UA, html_to_text  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apps", default="1-5")
    a = ap.parse_args()
    ids = set(parse_ids(a.apps))
    rows = [r for r in json.loads((ROOT / "data" / "results.json").read_text()) if r["id"] in ids]
    out, ok_n, total = [], 0, 0
    pages = {}
    for r in rows:
        for g in ("auth", "access", "api_surface", "mcp"):
            for e in r[g]["evidence"]:
                url = e["url"]
                if url not in pages:
                    try:
                        resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
                        t = resp.text
                        if "html" in resp.headers.get("content-type", ""):
                            title, t, _ = html_to_text(t, resp.url)
                            t = title + "\n" + t
                        pages[url] = (resp.status_code, t)
                    except Exception as ex:
                        pages[url] = (0, str(ex))
                code, text = pages[url]
                found = norm_ws(e["snippet"]) in norm_ws(text)
                total += 1; ok_n += found
                out.append({"app": r["app"], "group": g, "url": url, "status": code, "snippet_found_live": found,
                            "snippet": e["snippet"][:160]})
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "live_reverify.json").write_text(json.dumps({"checked": total, "found": ok_n, "items": out}, indent=1))
    print(f"live re-verify: {ok_n}/{total} evidence snippets still present on the vendor page")
    for o in out:
        if not o["snippet_found_live"]:
            print(f"  MISSING [{o['status']}] {o['app']} {o['group']} {o['url']}")


if __name__ == "__main__":
    main()
