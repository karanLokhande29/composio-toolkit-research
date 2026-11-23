"""Composio's own toolkit catalog, used two ways:

1. Keyless (always): parse the public catalog https://docs.composio.dev/toolkits.md
   (one row per toolkit: name, slug, #tools, auth schemes). This answers
   "does Composio already have a toolkit?" and gives Composio's own auth schemes,
   which Loop 1 uses as an independent cross-check of our auth answer.
2. With COMPOSIO_API_KEY (optional): confirm via the official Python SDK,
   `Composio().toolkits.get(slug)` (signature verified in
   https://docs.composio.dev/reference/sdk-reference/python/toolkits.md).
Serves: R8 (composio_existing_toolkit), R10 (Composio used where possible), R12 (cross-check).
"""
from __future__ import annotations

import re

from . import fetch
from .common import env

CATALOG_URL = "https://docs.composio.dev/toolkits.md"
ROW = re.compile(r"^\|\s*\[([^\]]+)\]\((/toolkits/[^)]+)\)\s*\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([^|]*)\|")
_catalog: list[dict] | None = None


def norm(s: str) -> str:
    s = re.sub(r"\(.*?\)", " ", s.lower())
    return re.sub(r"[^a-z0-9]", "", s)


def catalog() -> list[dict]:
    global _catalog
    if _catalog is None:
        rec = fetch.fetch(CATALOG_URL)
        rows = []
        for line in rec.get("text", "").splitlines():
            m = ROW.match(line.strip())
            if m:
                name, path, slug, tools, triggers, auth = m.groups()
                rows.append({"name": name, "slug": slug, "tools": int(tools), "triggers": int(triggers),
                             "auth": [a.strip() for a in auth.split(",") if a.strip()],
                             "url": "https://docs.composio.dev" + path, "row": line.strip()})
        _catalog = rows
    return _catalog


def lookup(app_name: str) -> dict:
    """Exact normalised match first, then candidates sharing the main token (LLM picks among them)."""
    cat = catalog()
    n = norm(app_name)
    exact = [r for r in cat if norm(r["name"]) == n or norm(r["slug"]) == n]
    first = re.split(r"[\s(.]", app_name.strip())[0].lower()
    cands = [r for r in cat if first and len(first) > 2 and first in r["name"].lower()][:8]
    return {"exact": exact[:3], "candidates": cands, "catalog_url": CATALOG_URL, "catalog_size": len(cat)}


def sdk_confirm(slug: str) -> dict | None:
    """Optional: confirm a toolkit with the Composio SDK when COMPOSIO_API_KEY is set."""
    if not env("COMPOSIO_API_KEY"):
        return None
    try:
        from composio import Composio
        tk = Composio().toolkits.get(slug.lower())
        return {"slug": slug, "sdk_ok": True, "raw": str(tk)[:500]}
    except Exception as e:  # documented fallback: catalog page is still the evidence
        return {"slug": slug, "sdk_ok": False, "error": str(e)[:200]}
