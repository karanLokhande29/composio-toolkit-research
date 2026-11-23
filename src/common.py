"""Shared helpers: paths, app list, results I/O, time, logging.

Serves: R1 (apps.yaml is the single list), R7/R12 (logs), everything else indirectly.
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = ROOT / "cache"
LOGS = ROOT / "logs"
SITE = ROOT / "site"
DISCOVERY = DATA / "discovery"
RAW = DATA / "raw"            # raw LLM outputs per agent, for audit
RESULTS = DATA / "results.json"
VLOG = LOGS / "verification_log.jsonl"

IST = timezone(timedelta(hours=5, minutes=30))
DEADLINE = datetime(2026, 11, 23, 23, 0, tzinfo=IST)

for d in (DATA, CACHE, LOGS, DISCOVERY, RAW):
    d.mkdir(parents=True, exist_ok=True)

try:  # .env is optional; never print its values
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:  # pragma: no cover
    pass

_lock = threading.Lock()


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def ist_now() -> datetime:
    return datetime.now(IST)


def clock_line() -> str:
    now = ist_now()
    left = DEADLINE - now
    h, m = divmod(int(left.total_seconds()) // 60, 60)
    return f"IST now {now:%H:%M} | deadline 23:00 | {h}h{m:02d}m left"


def load_apps(ids: list[int] | None = None) -> list[dict]:
    apps = yaml.safe_load((ROOT / "apps.yaml").read_text())
    if ids:
        s = set(ids)
        apps = [a for a in apps if a["id"] in s]
    return apps


def parse_ids(spec: str) -> list[int]:
    """'1-5,9,12-14' -> [1,2,3,4,5,9,12,13,14]"""
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return sorted(set(out))


def load_results() -> dict[int, dict]:
    if RESULTS.exists():
        return {r["id"]: r for r in json.loads(RESULTS.read_text())}
    return {}


def save_results(by_id: dict[int, dict], only: list[int] | None = None) -> None:
    """Write results. With `only`, merge just those ids into what is on disk (safe for parallel runs)."""
    import fcntl
    with _lock, open(DATA / ".results.lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        if only is not None:
            disk = load_results()
            disk.update({k: by_id[k] for k in only if k in by_id})
            by_id = disk
        rows = [by_id[k] for k in sorted(by_id)]
        tmp = RESULTS.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
        tmp.replace(RESULTS)


def log_jsonl(path: Path, obj: dict) -> None:
    obj = {"ts": ist_now().isoformat(timespec="seconds"), **obj}
    with _lock, open(path, "a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def log_human(what: str, why: str, app: str = "-") -> None:
    """Append a human-intervention line (R11)."""
    p = LOGS / "human_interventions.md"
    with _lock, open(p, "a") as f:
        f.write(f"| {ist_now():%Y-%m-%d %H:%M} | {app} | {what} | {why} |\n")


def norm_ws(s: str) -> str:
    """Normalise for snippet matching: unify quotes/dashes, collapse whitespace, lowercase."""
    s = s.replace(" ", " ").replace("’", "'").replace("‘", "'")
    s = s.replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    s = re.sub(r"[`*]|\\_", "", s)  # markdown emphasis/code marks are formatting, not words
    return re.sub(r"\s+", " ", s).strip().lower()


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False))


def read_json(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default
