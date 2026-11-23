"""Fetch + cache web pages politely.

* Every page is cached in cache/<sha1(url)[:16]>.json.gz with url, status, timestamp and the
  visible text (that text is what evidence snippets are checked against -> R7).
* Plain HTTP first (requests + BeautifulSoup). A headless-browser render (Playwright) is
  stored next to it as `browser_text` when `render=True` (used by Loop 3, browser_check.py).
* Per-host rate limit (1 request / host / second), a descriptive User-Agent, 20 s timeout.
Serves: R7 (cache = proof the URL was fetched), MASTER §4 rule 7 (reproducible & polite).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import threading
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .common import CACHE, ist_now

UA = ("Mozilla/5.0 (compatible; ComposioToolkitResearch/1.0; take-home research agent; "
      "+https://github.com/karanLokhande29/composio-toolkit-research)")
_host_locks: dict[str, threading.Lock] = {}
_host_last: dict[str, float] = {}
_glock = threading.Lock()
_browser_lock = threading.Lock()


def key(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def cache_path(url: str):
    return CACHE / f"{key(url)}.json.gz"


def load(url: str) -> dict | None:
    p = cache_path(url)
    if not p.exists():
        return None
    with gzip.open(p, "rt") as f:
        return json.load(f)


def _save(rec: dict) -> None:
    with gzip.open(cache_path(rec["url"]), "wt") as f:
        json.dump(rec, f, ensure_ascii=False)


def _polite_wait(url: str) -> None:
    host = urlparse(url).netloc
    with _glock:
        lock = _host_locks.setdefault(host, threading.Lock())
    with lock:
        gap = time.time() - _host_last.get(host, 0)
        if gap < 1.0:
            time.sleep(1.0 - gap)
        _host_last[host] = time.time()


def html_to_text(html: str, base_url: str) -> tuple[str, str, list[dict]]:
    soup = BeautifulSoup(html, "lxml")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    links = []
    for a in soup.find_all("a", href=True)[:800]:
        href = urljoin(base_url, a["href"]).split("#")[0]
        if href.startswith("http"):
            links.append({"href": href, "text": a.get_text(" ", strip=True)[:80]})
    for t in soup(["script", "style", "noscript", "svg", "template"]):
        t.decompose()
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{2,}", "\n", text)
    return title, text, links


def looks_js_rendered(text: str) -> bool:
    t = text.lower()
    return len(text) < 600 or "enable javascript" in t or "you need to enable javascript" in t


def fetch(url: str, force: bool = False) -> dict:
    """HTTP fetch with cache. Never raises; errors are recorded in the cache record."""
    if not force:
        cached = load(url)
        if cached is not None:
            return cached
    _polite_wait(url)
    rec = {"url": url, "fetched_at": ist_now().isoformat(timespec="seconds"), "method": "http"}
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en"}, timeout=20,
                         allow_redirects=True)
        rec.update(status=r.status_code, final_url=r.url)
        ctype = r.headers.get("content-type", "")
        if "html" in ctype or r.text.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
            title, text, links = html_to_text(r.text, r.url)
        else:  # markdown, JSON (OpenAPI / GitHub API), plain text
            title, text, links = "", r.text, []
        rec.update(title=title, text=text[:400_000], links=links[:600],
                   js_rendered=looks_js_rendered(text))
    except Exception as e:
        rec.update(status=0, error=str(e)[:300], text="", links=[], title="", js_rendered=False)
    _save(rec)
    return rec


def render(url: str) -> dict:
    """Loop 3: render with headless Chromium, add browser_text to the cache record."""
    rec = load(url) or fetch(url)
    if rec.get("browser_text"):
        return rec
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:  # each worker thread gets its own browser instance
            b = p.chromium.launch()
            page = b.new_page(user_agent=UA)
            resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)  # let client-side docs frameworks render
            html = page.content()
            b.close()
        title, text, links = html_to_text(html, url)
        rec.update(browser_text=text[:400_000], browser_status=resp.status if resp else 0,
                   browser_at=ist_now().isoformat(timespec="seconds"))
        if not rec.get("title"):
            rec["title"] = title
        if links:
            rec["links"] = (rec.get("links") or []) + links[:400]
    except Exception as e:
        rec.update(browser_error=str(e)[:300], browser_text="")
    _save(rec)
    return rec


def page_text(rec: dict) -> str:
    """All text we hold for a page (HTTP + browser render)."""
    return (rec.get("title") or "") + "\n" + (rec.get("text") or "") + "\n" + (rec.get("browser_text") or "")


def ok(rec: dict | None) -> bool:
    return bool(rec) and (rec.get("status") == 200 or rec.get("browser_status") == 200) and \
        len(page_text(rec).strip()) > 200
