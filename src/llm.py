"""One small wrapper around the LLM so every stage calls it the same way.

Two interchangeable backends (chosen by LLM_BACKEND in .env):
  * claude_cli  - shells out to `claude -p` (Claude Code headless). Used locally: no API key needed
                  beyond the developer's Claude login. Supports Claude's server-side WebSearch tool.
  * anthropic   - the official `anthropic` Python SDK with ANTHROPIC_API_KEY. Used in GitHub Actions.

Model aliases (haiku/sonnet/opus) are set per stage in .env so pass 1, the second agent and the
adjudicator can deliberately use different models (MASTER §7 Loop 2 "different model").
Serves: R10 (agent does the research), R12 (different model for loop 2).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time

from .common import env

MODEL_IDS = {  # alias -> API model id for the anthropic backend
    "haiku": "claude-haiku-5-5",
    "sonnet": "claude-sonnet-5-5",
    "opus": "claude-opus-5-5",
}


def backend() -> str:
    b = env("LLM_BACKEND")
    if b:
        return b
    return "anthropic" if env("ANTHROPIC_API_KEY") and not shutil.which("claude") else "claude_cli"


def _extract_json(text: str):
    """Pull the first JSON object out of a model reply (tolerates ```json fences / prose)."""
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start : end + 1])


def ask_json(prompt: str, system: str, model: str = "haiku", web_search: bool = False,
             timeout: int = 420, retries: int = 1) -> tuple[dict, dict]:
    """Send one prompt, return (parsed_json, meta). meta has cost/duration for the metrics."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            if backend() == "anthropic":
                return _ask_anthropic(prompt, system, model, web_search, timeout)
            return _ask_cli(prompt, system, model, web_search, timeout)
        except Exception as e:  # retry once on parse/timeout errors
            last_err = e
            time.sleep(3)
    raise RuntimeError(f"LLM failed after retries: {last_err}")


def _ask_cli(prompt, system, model, web_search, timeout):
    cmd = ["claude", "-p", "--model", model, "--output-format", "json",
           "--system-prompt", system, "--setting-sources", "", "--strict-mcp-config",
           "--no-session-persistence"]
    if web_search:
        cmd += ["--tools", "WebSearch", "--allowedTools", "WebSearch"]
    else:
        cmd += ["--tools", ""]
    t0 = time.time()
    p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout)
    out = json.loads(p.stdout)
    if out.get("is_error"):
        raise RuntimeError(f"claude cli error: {out.get('result')}")
    meta = {"backend": "claude_cli", "model": model, "cost_usd": out.get("total_cost_usd", 0),
            "seconds": round(time.time() - t0, 1), "turns": out.get("num_turns")}
    return _extract_json(out["result"]), meta


def _ask_anthropic(prompt, system, model, web_search, timeout):
    import anthropic  # imported lazily so the CLI backend has no hard dependency

    client = anthropic.Anthropic(timeout=timeout)
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}] if web_search else []
    t0 = time.time()
    kwargs = dict(model=MODEL_IDS.get(model, model), max_tokens=8000, system=system,
                  messages=[{"role": "user", "content": prompt}])
    if tools:
        kwargs["tools"] = tools
    msg = client.messages.create(**kwargs)
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    meta = {"backend": "anthropic", "model": model, "seconds": round(time.time() - t0, 1),
            "input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens}
    return _extract_json(text), meta
