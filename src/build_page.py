"""Render the single self-contained case-study page: site/index.html (+ results.json, patterns.json, llms.txt).

Static HTML for everything a reviewer (or an agent) must read - headline patterns, wins/outreach, agent,
human-needed, verification, proof, process, limitations - and a small vanilla-JS layer for the
interactive findings matrix and charts, driven by the JSON embedded in <script id="data">.
No external requests at runtime (R15). Section ids/order per MASTER §8 (R16).
"""
from __future__ import annotations

import html
import json
import re

from .common import DATA, LOGS, ROOT, SITE, ist_now, load_results, read_json

REPO = "https://github.com/karanLokhande29/composio-toolkit-research"
LIVE = "https://karanlokhande29.github.io/composio-toolkit-research/"
ACTIONS = REPO + "/actions/workflows/research.yml"
E = html.escape

LABEL = {
    "self_serve_free": "Self-serve (free)", "self_serve_trial": "Self-serve (trial)", "paid_plan_required": "Paid plan",
    "admin_approval": "Admin approval", "app_review": "App review", "partner_gated": "Partner-gated",
    "contact_sales": "Contact sales", "unknown": "Unknown", "ready": "Ready", "ready_with_caveats": "Ready w/ caveats",
    "blocked": "Blocked", "none": "None", "partner_gate": "Partner gate", "paid_plan": "Paid plan",
    "admin_scope": "Admin scope", "no_public_api": "No public API", "cli_only": "CLI only", "other": "Other",
    "oauth2": "OAuth2", "api_key": "API key", "basic": "Basic", "bearer_token": "Bearer token", "jwt": "JWT",
}


def L(v):
    return LABEL.get(v, str(v).replace("_", " "))


def human_table() -> list[list[str]]:
    p = LOGS / "human_interventions.md"
    rows = []
    for ln in p.read_text().splitlines() if p.exists() else []:
        if ln.startswith("| 20"):
            rows.append([c.strip() for c in ln.strip().strip("|").split("|")])
    return rows


def phase_rows() -> list[list[str]]:
    p = LOGS / "phase_log.md"
    return [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in (p.read_text().splitlines() if p.exists() else [])
            if ln.startswith("| 20")]


def li(items: list[dict], extra) -> str:
    return "".join(f'<li><b>{E(i["app"])}</b> <span class="muted">· {E(i["category"])}</span>{extra(i)}</li>' for i in items)


def pct(x):
    return f"{100 * x:.0f}%"


def verification_html(m: dict, pat: dict) -> str:
    acc = m.get("accuracy", {})
    l1, l2, l3 = m["loop1"], m["loop2"], m["loop3"]
    ch = m["changed_by_automated_loops"]
    if acc.get("status") == "computed":
        o = acc["overall"]
        ai = acc.get("judge") == "ai_auditor"
        who = "an independent AI auditor (Claude Opus, which produced none of the answers)" if ai else "Karan, by hand"
        head = (f'<div class="kpis"><div class="kpi"><span>{pct(o["pass1"])}</span>pass-1 accuracy</div>'
                f'<div class="kpi arrow">→</div><div class="kpi good"><span>{pct(o["final_automated"])}</span>after automated loops</div>'
                f'<div class="kpi"><span>{o["human_corrections"]}</span>sampled values still wrong</div></div>'
                + ('<div class="callout warn"><b>Not a human check.</b> The human review step (Loop 4) was skipped for lack of time before the '
                   'deadline, so these numbers come from an independent AI auditor instead. Treat them as a second opinion, not ground truth; '
                   'the blank human sheet and the review tool are in the repo (human_review/).</div>' if ai else '')
                + f'<p class="muted">Sample: {acc["rows"]} (app, field) pairs across {acc["apps"]} apps, stratified 3 apps per category '
                f'with a fixed seed (20261123), plus every app still flagged after Loop 3. Judged by {who}: each pass-1 and final value marked right/wrong.</p>')
        rows = "".join(f'<tr><td>{E(k)}</td><td>{v["n"]}</td><td>{pct(v["pass1"])}</td><td><b>{pct(v["final"])}</b></td></tr>'
                       for k, v in sorted(acc["per_field"].items()))
        table = f'<table class="small"><thead><tr><th>Field</th><th>n</th><th>Pass 1</th><th>Final</th></tr></thead><tbody>{rows}</tbody></table>'
        fixed = "".join(f'<tr><td>{E(x["app"])}</td><td>{E(x["field"])}</td><td>{E(x["pass1"])}</td><td>{E(x["final"])}</td><td>{E(x["caught_by"])}</td></tr>'
                        for x in acc["fixed_by_loops"]) or '<tr><td colspan="5">none</td></tr>'
        misses = "".join(f'<tr><td>{E(x["app"])}</td><td>{E(x["field"])}</td><td>{E(x["final"])}</td><td>{E(x["human"])}</td><td>{E(x["caught_by"])}</td></tr>'
                         for x in acc["misses"]) or '<tr><td colspan="5">none - every sampled final value was judged correct</td></tr>'
        detail = (f'<h3>Hits the loops produced (wrong in pass 1, right in final)</h3><div class="scroll"><table class="small"><thead><tr><th>App</th><th>Field</th><th>Pass 1</th><th>Final</th><th>Fixed by</th></tr></thead><tbody>{fixed}</tbody></table></div>'
                  f'<h3 id="misses">Misses (final value still wrong)</h3><div class="scroll"><table class="small"><thead><tr><th>App</th><th>Field</th><th>Our final value</th><th>Correct value (judge)</th><th>Status</th></tr></thead><tbody>{misses}</tbody></table></div>')
    else:
        n = acc.get("rows", "")
        head = (f'<div class="callout warn"><b>Human accuracy check pending.</b> The stratified sample sheet ({n} rows) is generated '
                f'but not yet filled, so no accuracy number is claimed here. The automated-loop numbers below are measured.</div>')
        table, detail = "", '<h3 id="misses">Misses</h3><p>Not yet measured - waiting for the human sheet.</p>'
    def kv(d):
        return E(", ".join(f"{k} x{v}" for k, v in d.items()) or "none")
    f1, h2, bf = kv(l1["flags"]), kv(l2["hard"]), kv(ch["by_field"])
    loops = f"""
<div class="loops">
 <div class="loop"><h4>Loop 1 · deterministic</h4><p>{l1['evidence_total']} evidence quotes checked against the cached pages:
 <b>{l1['evidence_verified_pct']}%</b> verified ({l1['evidence_exact']} exact, {l1['evidence_repaired']} re-anchored to the page's own wording),
 {l1['evidence_dropped']} dropped. {l1['fields_changed']} field values downgraded to <i>unknown</i> because no quote survived.
 Rule flags: {f1}.</p></div>
 <div class="loop"><h4>Loop 2 · independent second agent</h4><p>Different discovery, prompt and URL model, blind to pass 1.
 Hard disagreements: {h2}. {l2['apps_with_hard']} apps had at least one;
 {l2['fields_filled']} gaps filled with verified answers.</p></div>
 <div class="loop"><h4>Loop 3 · headless browser + adjudicator</h4><p>{l3['apps']} apps re-examined ({l3['fields_examined']} fields) with pages
 rendered in Chromium; a stronger model decided each field with a fresh quote that was re-verified in code.
 {l3['fields_changed']} values changed; {l3['unresolved']} left unresolved → sent to the human.</p></div>
</div>
<p><b>{ch['apps_changed']} of {m['n_apps']} apps ({ch['apps_changed_pct']}%)</b> had at least one key value changed by the automated loops
({bf}).</p>"""
    unresolved = "".join(f'<li><b>{E(x["app"])}</b>: {E(x["reason"])}</li>' for x in m["needs_human"]) or "<li>none</li>"
    return head + table + loops + detail + f'<h3 id="unresolved">Still unresolved after the automated loops ({len(m["needs_human"])})</h3><ul class="cols">{unresolved}</ul>'


def run() -> None:
    res = load_results()
    rows = [res[k] for k in sorted(res)]
    pat = read_json(DATA / "patterns.json")
    m = read_json(DATA / "metrics.json")
    for r in rows:
        r.pop("_meta", None)
    total = pat["n_apps"]
    acc = m.get("accuracy", {})
    judge = "AI-audited sample, not human" if acc.get("judge") == "ai_auditor" else "human-checked sample"
    acc_tile = (f'<div class="kpi good"><span>{pct(acc["overall"]["pass1"])} → {pct(acc["overall"]["final_automated"])}</span>accuracy, pass 1 → final ({judge})</div>'
                if acc.get("status") == "computed" else '<div class="kpi"><span>pending</span>human accuracy check</div>')
    heads = "".join(f'<li>{E(h["text"])}</li>' for h in pat["headlines"])
    wins_new = li(pat["easy_wins_without_composio_toolkit"], lambda i: ' <span class="tag new">no Composio toolkit yet</span>')
    wins_have = li([w for w in pat["easy_wins"] if w["composio_toolkit"] == "yes"], lambda i: "")
    outreach = li(pat["needs_outreach"], lambda i: f' <span class="tag">{E(L(i["access"]))}</span> <span class="muted small">{E(i["rationale"][:140])}</span>')
    review = li(pat["needs_app_review"], lambda i: "")
    paid = li(pat["needs_paid_plan"], lambda i: "")
    human = "".join(f"<tr>{''.join(f'<td>{E(c)}</td>' for c in r)}</tr>" for r in human_table())
    phases = "".join(f"<li><b>{E(r[0][-5:])}</b> · {E(r[1])} — {E(r[2])}</li>" for r in phase_rows())
    unknown_apps = [r for r in rows if r["access"]["status"] == "unknown" or r["auth"]["methods"] == ["unknown"]]
    failures = "".join(f'<li><b>{E(r["app"])}</b>: {E("; ".join(f"{k}: {v}" for k, v in (r.get("unknown_reasons") or {}).items() if v)[:220] or "unknown value")}</li>'
                       for r in unknown_apps) or "<li>none</li>"
    non_saas = ", ".join(f'{E(x["app"])} ({E(str(x.get("app_type")).replace("_", " "))})' for x in pat["non_saas"]) or "none"
    ct = m.get("cost_time", {})
    data_blob = json.dumps({"generated_at": ist_now().isoformat(timespec="minutes"), "patterns": pat, "metrics": m, "results": rows},
                           ensure_ascii=False).replace("</", "<\\/")

    page = TEMPLATE
    for k, v in {
        "__TOTAL__": str(total), "__READY__": str(pat["ready_n"]), "__CAVEATS__": str(pat["caveats_n"]), "__BLOCKED__": str(pat["blocked_n"]),
        "__SELF__": str(pat["self_serve_pct"]), "__OAUTH__": str(pat["auth_summary"]["oauth2_pct"]), "__ACC_TILE__": acc_tile,
        "__HEADLINES__": heads, "__WINS_NEW__": wins_new or "<li>none</li>", "__WINS_HAVE__": wins_have or "<li>none</li>",
        "__N_NEW__": str(pat["easy_new_n"]), "__N_WINS__": str(pat["easy_wins_n"]), "__OUTREACH__": outreach or "<li>none</li>",
        "__N_OUT__": str(pat["outreach_n"]), "__REVIEW__": review or "<li>none</li>", "__PAID__": paid or "<li>none</li>",
        "__N_REVIEW__": str(pat["review_n"]), "__N_PAID__": str(pat["paid_n"]),
        "__HUMAN__": human, "__VERIFICATION__": verification_html(m, pat), "__PHASES__": phases or "<li>see logs/phase_log.md</li>",
        "__FAILURES__": failures, "__NON_SAAS__": non_saas, "__REPO__": REPO, "__ACTIONS__": ACTIONS, "__LIVE__": LIVE,
        "__COST__": f'{ct.get("llm_cost_usd_reported", 0):.0f}', "__CALLS__": str(sum(ct.get("calls", {}).values())),
        "__GEN__": ist_now().strftime("%d %b %Y %H:%M IST"), "__DATA__": data_blob,
    }.items():
        page = page.replace(k, v)
    SITE.mkdir(exist_ok=True)
    (SITE / "index.html").write_text(page)
    (SITE / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    (SITE / "patterns.json").write_text(json.dumps(pat, ensure_ascii=False, indent=1))
    (SITE / "metrics.json").write_text(json.dumps(m, ensure_ascii=False, indent=1))
    (SITE / "llms.txt").write_text(llms_txt(pat, m))
    print(f"page: site/index.html {len(page)//1024} KB")


def llms_txt(pat, m) -> str:
    acc = m.get("accuracy", {})
    who = "an independent AI auditor (NOT a human)" if acc.get("judge") == "ai_auditor" else "a human"
    a = (f"Accuracy on a stratified sample, judged by {who}: pass 1 {pct(acc['overall']['pass1'])} -> final {pct(acc['overall']['final_automated'])}."
         if acc.get("status") == "computed" else "Human accuracy check: pending.")
    return f"""# Composio toolkit research: 100 apps

> An agent researched 100 apps for Composio toolkit feasibility (auth, self-serve vs gated access, API surface, MCP,
> buildability) with a verbatim evidence quote behind every answer, then verified itself in 3 automated loops + a human sample.

{a}

## Machine-readable files
- [results.json]({LIVE}results.json): one object per app (schema: auth, access, api_surface, mcp, buildability, evidence, pass1, verification)
- [patterns.json]({LIVE}patterns.json): every aggregate number and the headline sentences
- [metrics.json]({LIVE}metrics.json): coverage, per-loop verification stats, accuracy
- [Source repo]({REPO}): README explains how to run the agent

## Headlines
""" + "\n".join(f"- {h['text']}" for h in pat["headlines"]) + "\n"


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Toolkit Feasibility: 100 Apps</title>
<meta name="description" content="An agent researched 100 apps for Composio toolkit feasibility, with evidence and a verified accuracy check.">
<link rel="alternate" type="text/plain" href="llms.txt" title="llms.txt">
<style>
:root{--bg:#fbfbfa;--fg:#1d1f23;--muted:#5d636d;--card:#fff;--line:#e3e5e8;--accent:#3b4fd8;--good:#1a7f45;--warn:#9a6200;--bad:#b42318;
--good-bg:#e5f4ea;--warn-bg:#fff3d6;--bad-bg:#fde8e6;--neutral-bg:#eef0f3;--c1:#3b4fd8;--c2:#2f9e8f;--c3:#d08a1e;--c4:#c2415c;--c5:#8a8f98}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#131417;--fg:#e8e9ec;--muted:#a0a6b0;--card:#1c1e22;--line:#2d3036;--accent:#8b9bff;
--good:#5fd08f;--warn:#f0b84a;--bad:#ff8a7a;--good-bg:#163322;--warn-bg:#3a2d10;--bad-bg:#3d1c19;--neutral-bg:#26292e;--c1:#8b9bff;--c2:#4fc3b2;--c3:#f0b84a;--c4:#ef7b95;--c5:#8a8f98}}
:root[data-theme="dark"]{--bg:#131417;--fg:#e8e9ec;--muted:#a0a6b0;--card:#1c1e22;--line:#2d3036;--accent:#8b9bff;--good:#5fd08f;--warn:#f0b84a;--bad:#ff8a7a;
--good-bg:#163322;--warn-bg:#3a2d10;--bad-bg:#3d1c19;--neutral-bg:#26292e;--c1:#8b9bff;--c2:#4fc3b2;--c3:#f0b84a;--c4:#ef7b95;--c5:#8a8f98}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1120px;margin:0 auto;padding:0 16px 64px}a{color:var(--accent)}
nav{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);z-index:5;overflow-x:auto;white-space:nowrap}
nav a{display:inline-block;padding:9px 10px;font-size:13px;text-decoration:none;color:var(--muted)}nav a:hover{color:var(--fg)}
h1{font-size:clamp(24px,4vw,34px);line-height:1.2;margin:28px 0 6px}h2{font-size:21px;margin:44px 0 10px;padding-top:8px;border-top:1px solid var(--line)}
h3{font-size:16px;margin:22px 0 8px}h4{margin:0 0 4px;font-size:14px}.muted{color:var(--muted)}.small{font-size:13px}
.lede{font-size:17px;color:var(--muted);max-width:820px}
.kpis{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0}.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;min-width:130px;font-size:13px;color:var(--muted)}
.kpi span{display:block;font-size:24px;font-weight:650;color:var(--fg)}.kpi.good span{color:var(--good)}.kpi.arrow{border:0;background:none;font-size:26px;min-width:0;align-self:center}
.headlines{padding-left:20px;font-size:16px}.headlines li{margin:6px 0}
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px;margin-top:14px}
.chart{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}.chart h3{margin:0 0 8px;font-size:14px}
.bar{display:grid;grid-template-columns:120px 1fr 34px;gap:8px;align-items:center;font-size:12.5px;margin:4px 0}
.bar .t{height:14px;background:var(--neutral-bg);border-radius:3px;overflow:hidden;display:flex}.bar .t i{display:block;height:100%}
.legend{font-size:12px;color:var(--muted);margin-top:6px}.legend b{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 4px 0 10px;vertical-align:middle}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}
.panel{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px}.panel ul{padding-left:18px;margin:6px 0}.panel li{margin:3px 0}
.tag{display:inline-block;font-size:11.5px;padding:0 6px;border-radius:9px;background:var(--neutral-bg);color:var(--muted)}.tag.new{background:var(--good-bg);color:var(--good)}
.controls{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}.controls input,.controls select{font:inherit;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg)}
.controls input{flex:1;min-width:180px}.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{position:sticky;top:0;background:var(--card);cursor:pointer;white-space:nowrap;font-weight:600}table.small td,table.small th{font-size:12.5px}
td a{text-decoration:none}td a:hover{text-decoration:underline}tr.detail td{background:var(--bg);font-size:12.5px}
.chip{display:inline-block;padding:1px 7px;border-radius:9px;font-size:12px;font-weight:600;white-space:nowrap}
.v-ready{background:var(--good-bg);color:var(--good)}.v-ready_with_caveats{background:var(--warn-bg);color:var(--warn)}.v-blocked{background:var(--bad-bg);color:var(--bad)}
.pipeline{display:flex;flex-wrap:wrap;gap:6px;align-items:stretch;margin:12px 0}.step{flex:1 1 150px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px;font-size:13px}
.step b{display:block;font-size:13.5px;margin-bottom:2px}.step.h{border-color:var(--warn);background:var(--warn-bg)}.arrowr{align-self:center;color:var(--muted)}
.loops{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin:12px 0}.loop{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;font-size:13.5px}
.callout{border-radius:10px;padding:10px 14px;margin:10px 0}.callout.warn{background:var(--warn-bg)}ul.cols{columns:2 340px;font-size:13.5px}
code{background:var(--neutral-bg);padding:1px 5px;border-radius:4px;font-size:13px}pre{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px;overflow-x:auto}
@media (max-width:600px){.bar{grid-template-columns:90px 1fr 28px}.hide-sm{display:none}}
</style></head><body>
<nav aria-label="sections"><a href="#headline">Patterns</a><a href="#wins-outreach">Wins vs outreach</a><a href="#matrix">All 100 apps</a><a href="#agent">The agent</a><a href="#human-needed">Human needed</a><a href="#verification">Verification</a><a href="#proof">Proof</a><a href="#process">Process</a><a href="#limitations">Limitations</a></nav>
<main>
<header>
<h1>Can Composio build a toolkit for it? 100 apps, researched by an agent</h1>
<p class="lede">An agent read each app's own docs and decided how it authenticates, whether a developer can get credentials alone, how big the API is, whether an MCP server exists, and whether a toolkit could ship today. Every answer quotes the docs page behind it. The whole dataset went through 3 automated verification loops, and a stratified sample was then audited for accuracy.</p>
<div class="kpis"><div class="kpi good"><span>__READY__</span>ready today</div><div class="kpi"><span>__CAVEATS__</span>ready with caveats</div><div class="kpi"><span>__BLOCKED__</span>blocked</div>
<div class="kpi"><span>__SELF__%</span>self-serve credentials</div><div class="kpi"><span>__OAUTH__%</span>support OAuth2</div>__ACC_TILE__</div>
</header>

<section id="headline"><h2>The patterns</h2>
<ol class="headlines">__HEADLINES__</ol>
<div class="charts"><div class="chart" id="ch-auth"><h3>Auth methods (apps supporting each)</h3></div>
<div class="chart" id="ch-access"><h3>Self-serve vs gated, by category</h3></div>
<div class="chart" id="ch-block"><h3>Main blocker (apps not ready)</h3></div></div>
<noscript><p>Charts need JavaScript; all numbers are in <a href="patterns.json">patterns.json</a>.</p></noscript>
</section>

<section id="wins-outreach"><h2>Where to start, and who to call</h2>
<div class="grid2">
<div class="panel"><h3>Easy wins: __N_WINS__ self-serve, ready, broad-enough APIs</h3>
<p class="small muted">__N_NEW__ of them have no Composio toolkit yet, so they're the cheapest net-new coverage.</p><ul>__WINS_NEW__</ul>
<details><summary class="small">Already in Composio's catalog</summary><ul class="small">__WINS_HAVE__</ul></details></div>
<div class="panel"><h3>Needs outreach: __N_OUT__ apps behind a partner, sales gate or no public API</h3><ul>__OUTREACH__</ul>
<h3>App review / approval: __N_REVIEW__</h3><ul class="small">__REVIEW__</ul><h3>Paid plan required: __N_PAID__</h3><ul class="small">__PAID__</ul></div>
</div></section>

<section id="matrix"><h2>All 100 apps</h2>
<p class="small muted">Every cell links to the docs page its quote came from. Click a row for the one-liner, rationale and the exact quotes. Verdict colours also carry text labels.</p>
<div class="controls"><input id="q" type="search" placeholder="Search app, category, auth…" aria-label="search">
<select id="fcat" aria-label="category"><option value="">All categories</option></select>
<select id="fverd" aria-label="verdict"><option value="">All verdicts</option><option value="ready">Ready</option><option value="ready_with_caveats">Ready w/ caveats</option><option value="blocked">Blocked</option></select>
<select id="facc" aria-label="access"><option value="">All access</option></select><span id="count" class="small muted" style="align-self:center"></span></div>
<div class="scroll" style="max-height:640px"><table id="tbl"><thead><tr>
<th data-k="id">#</th><th data-k="app">App</th><th data-k="category" class="hide-sm">Category</th><th data-k="auth">Auth</th><th data-k="access">Access</th>
<th data-k="api" class="hide-sm">API</th><th data-k="mcp">MCP</th><th data-k="verdict">Verdict</th><th data-k="blocker" class="hide-sm">Blocker</th><th data-k="composio" class="hide-sm">Composio</th><th data-k="ver" class="hide-sm">Verified by</th></tr></thead><tbody></tbody></table></div>
<noscript><p>The table needs JavaScript. The full data is in <a href="results.json">results.json</a>.</p></noscript>
</section>

<section id="agent"><h2>The agent</h2>
<div class="pipeline">
<div class="step"><b>1 · Discover</b>Hint URLs + model-proposed official URLs (Claude WebSearch for the first 38 apps) + GitHub MCP search + Composio's public toolkit catalog, then a one-hop crawl for auth/pricing/MCP links.</div><span class="arrowr">→</span>
<div class="step"><b>2 · Fetch &amp; cache</b>Polite HTTP fetch (UA, 1 req/s per host); every page cached with a timestamp. That cache is the only allowed evidence source.</div><span class="arrowr">→</span>
<div class="step"><b>3 · Extract (pass 1)</b>A fast model (Claude Haiku) fills the schema from the cached pages and must quote the page for each answer. Snapshot kept as <code>pass1</code>.</div><span class="arrowr">→</span>
<div class="step"><b>4 · Loop 1</b>Code-only checks: quote exists in the page, URL returned 200, enum/schema valid, consistency rules, Composio catalog cross-check.</div><span class="arrowr">→</span>
<div class="step"><b>5 · Loop 2</b>An independent second agent re-researches each app blind to pass 1; field-level disagreements are flagged.</div><span class="arrowr">→</span>
<div class="step"><b>6 · Loop 3</b>Headless Chromium re-renders flagged and JS-built pages; Claude Sonnet adjudicates with fresh quotes, which are re-checked in code.</div><span class="arrowr">→</span>
<div class="step h"><b>7 · Accuracy audit</b>Stratified sample (fixed seed, 260 field checks). A human review tool was built, but the hand check was skipped for time, so an independent AI auditor (Claude Opus) judged it, and the page says so.</div>
</div>
<p class="small muted">Plain Python, about 1,500 lines. LLM calls go through one wrapper that can use the local <code>claude</code> CLI or the Anthropic API. This run: __CALLS__ logged LLM stage calls, about $__COST__ list-price equivalent. Composio is used through its public toolkit catalog (no key needed), with an optional SDK check (<code>Composio().toolkits.get</code>) when <code>COMPOSIO_API_KEY</code> is set.</p>
</section>

<section id="human-needed"><h2>Where a human was needed</h2>
<div class="scroll"><table class="small"><thead><tr><th>When (IST)</th><th>App</th><th>What the human did</th><th>Why the agent couldn't</th></tr></thead><tbody>__HUMAN__</tbody></table></div>
</section>

<section id="verification"><h2>Verification: how we know it's right</h2>
__VERIFICATION__
</section>

<section id="proof"><h2>Proof: run it yourself</h2>
<ul><li>Source + README: <a href="__REPO__">__REPO__</a></li>
<li>Runnable trigger: <a href="__ACTIONS__">GitHub Actions → “research” → Run workflow</a> (choose app ids; <code>verify-only</code> mode needs no API keys and re-checks every evidence quote live against the vendor pages).</li>
<li>Locally: <pre>python run.py --apps 1-5 --stage all</pre></li>
<li>For agents: <a href="llms.txt">llms.txt</a> · <a href="results.json">results.json</a> · <a href="patterns.json">patterns.json</a> · <a href="metrics.json">metrics.json</a>; the full dataset is also embedded in this page as <code>&lt;script id="data"&gt;</code>.</li></ul>
</section>

<section id="process"><h2>Process</h2><ol class="small">__PHASES__</ol></section>

<section id="limitations"><h2>Limitations and honest failures</h2>
<ul>
<li><b>Discovery depth varied by budget.</b> Apps 1–38 used Claude's web search for discovery. After the CLI hit its usage limit, apps 39–100 used model-proposed URLs plus crawling, which has lower recall for obscure apps.</li>
<li><b>MCP is the weakest field and the loops made it worse.</b> In the accuracy audit, MCP was the least accurate field, and it was the only one where accuracy dropped after the loops. The agent mostly misses <i>official</i> MCP servers (e.g. Google Ads, Supabase, Linear, Jira/Atlassian, Snowflake, Vercel). These are announced on pages the crawler never fetched, and Loop 3 dropped some correct ones because the URL wasn't quoted on a fetched page. Fix: add a dedicated MCP discovery step (vendor docs search plus the MCP registry) before extraction.</li>
<li><b>Docs say what's allowed, not what works.</b> Without paid or partner accounts, gated apps are judged from public docs only (as the brief asks). Nothing was tested with live credentials.</li>
<li><b>Breadth is a judgement</b> (narrow/moderate/broad), not an endpoint count. Composio-toolkit presence is an exact name match against Composio's public catalog, which can miss renamed toolkits.</li>
<li><b>Not SaaS:</b> __NON_SAAS__. These are classified as what they are, not forced into the SaaS mould.</li>
</ul>
<h3 id="failures">Apps the agent couldn't settle (a field is still unknown)</h3><ul class="cols">__FAILURES__</ul>
<p class="small muted">Next steps: authenticated API probes for the self-serve apps (to confirm the auth answers end to end), a larger human sample, and wiring discovery through Composio's search tools once an API key is available.</p>
</section>
<p class="small muted">Generated __GEN__ from data/*.json by src/build_page.py.</p>
</main>
<script type="application/json" id="data">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent),R=D.results,P=D.patterns;
const LBL={self_serve_free:'Self-serve (free)',self_serve_trial:'Self-serve (trial)',paid_plan_required:'Paid plan',admin_approval:'Admin approval',app_review:'App review',partner_gated:'Partner-gated',contact_sales:'Contact sales',unknown:'Unknown',ready:'Ready',ready_with_caveats:'Ready w/ caveats',blocked:'Blocked',none:'—',partner_gate:'Partner gate',paid_plan:'Paid plan',admin_scope:'Admin scope',no_public_api:'No public API',cli_only:'CLI only',other:'Other',oauth2:'OAuth2',api_key:'API key',basic:'Basic',bearer_token:'Bearer',jwt:'JWT',rest:'REST',graphql:'GraphQL',soap:'SOAP',websocket:'WebSocket',sdk_only:'SDK only',cli_or_library_only:'CLI/library',narrow:'narrow',moderate:'moderate',broad:'broad'};
const l=v=>LBL[v]||String(v).replace(/_/g,' ');const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function bars(id,items,max){const el=document.getElementById(id);el.insertAdjacentHTML('beforeend',items.map(([k,v,c])=>`<div class="bar"><span>${esc(k)}</span><span class="t"><i style="width:${100*v/max}%;background:${c||'var(--c1)'}"></i></span><span>${v}</span></div>`).join(''))}
const A=P.auth_distribution;bars('ch-auth',Object.entries(A).filter(([k])=>k!=='unknown').map(([k,v])=>[l(k),v]),P.n_apps);
(function(){const el=document.getElementById('ch-access');const C={'self-serve':'var(--c2)','paid plan':'var(--c3)','gated':'var(--c4)','unknown':'var(--c5)'};
el.insertAdjacentHTML('beforeend',Object.entries(P.access_by_category).map(([c,v])=>`<div class="bar"><span title="${esc(c)}">${esc(c.split(/[ ,]/)[0])}</span><span class="t">${['self-serve','paid plan','gated','unknown'].map(k=>`<i style="width:${100*v[k]/v.n}%;background:${C[k]}" title="${k}: ${v[k]}"></i>`).join('')}</span><span>${v.self_serve_pct}%</span></div>`).join('')+
`<div class="legend"><b style="background:var(--c2)"></b>self-serve<b style="background:var(--c3)"></b>paid plan<b style="background:var(--c4)"></b>gated<b style="background:var(--c5)"></b>unknown · % = self-serve</div>`)})();
const B=Object.entries(P.blocker_frequency);bars('ch-block',B.map(([k,v])=>[l(k),v,'var(--c4)']),Math.max(1,...B.map(x=>x[1])));
const first=(g,r)=>((r[g]||{}).evidence||[])[0];
const link=(txt,e)=>e?`<a href="${esc(e.url)}" target="_blank" rel="noopener" title="${esc(e.snippet)}">${txt}</a>`:txt;
const row=r=>({id:r.id,app:r.app,category:r.category,auth:r.auth.methods.map(l).join(', '),access:r.access.status,api:r.api_surface.styles.map(l).join('/')+' · '+r.api_surface.breadth,
 mcp:r.mcp.official?'official':(r.mcp.community.length?'community':'none'),verdict:r.buildability.verdict,blocker:r.buildability.main_blocker,composio:r.buildability.composio_existing_toolkit,ver:r.verification.resolved_by,r});
let rows=R.map(row),sortK='id',dir=1,open=new Set();
const cats=[...new Set(R.map(r=>r.category))];cats.forEach(c=>fcat.insertAdjacentHTML('beforeend',`<option>${esc(c)}</option>`));
[...new Set(R.map(r=>r.access.status))].sort().forEach(a=>facc.insertAdjacentHTML('beforeend',`<option value="${a}">${l(a)}</option>`));
function draw(){const q=document.getElementById('q').value.toLowerCase();let rs=rows.filter(x=>(!fcat.value||x.category===fcat.value)&&(!fverd.value||x.verdict===fverd.value)&&(!facc.value||x.access===facc.value)&&(!q||JSON.stringify([x.app,x.category,x.auth,x.access,x.api,x.mcp,x.blocker]).toLowerCase().includes(q)));
rs.sort((a,b)=>(a[sortK]>b[sortK]?1:a[sortK]<b[sortK]?-1:0)*dir);document.getElementById('count').textContent=rs.length+' apps';
document.querySelector('#tbl tbody').innerHTML=rs.map(x=>{const r=x.r;const mcpE=r.mcp.official?{url:r.mcp.official,snippet:'official MCP'}:(r.mcp.community[0]?{url:r.mcp.community[0],snippet:'community MCP'}:null);
return `<tr data-id="${x.id}" style="cursor:pointer"><td>${x.id}</td><td><b>${esc(x.app)}</b></td><td class="hide-sm">${esc(x.category)}</td><td>${link(esc(x.auth),first('auth',r))}</td><td>${link(l(x.access),first('access',r))}</td>
<td class="hide-sm">${link(esc(x.api),first('api_surface',r))}</td><td>${link(x.mcp,mcpE)}</td><td><span class="chip v-${x.verdict}">${l(x.verdict)}</span></td><td class="hide-sm">${l(x.blocker)}</td>
<td class="hide-sm">${link(x.composio,(r.buildability.composio_evidence||[])[0])}</td><td class="hide-sm">${esc(x.ver)}${r.needs_human?' ⚑':''}</td></tr>`+(open.has(x.id)?detail(r):'')}).join('')}
function detail(r){const ev=g=>((g==='overview'?r.overview_evidence:(r[g]||{}).evidence)||[]).map(e=>`<li><a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.url.replace(/^https?:\/\//,'').slice(0,70))}</a>: “${esc(e.snippet)}”</li>`).join('');
const p1=r.pass1||{};const ch=[['auth',(p1.auth||{}).methods,r.auth.methods],['access',(p1.access||{}).status,r.access.status],['verdict',(p1.buildability||{}).verdict,r.buildability.verdict]].filter(([,a,b])=>JSON.stringify(a)!==JSON.stringify(b));
return `<tr class="detail"><td></td><td colspan="10"><b>${esc(r.one_liner)}</b><br><i>${esc(r.buildability.rationale)}</i>
${ch.length?`<br><span class="tag">changed by verification: ${ch.map(([k,a,b])=>`${k} ${esc(JSON.stringify(a))} → ${esc(JSON.stringify(b))}`).join('; ')}</span>`:''}
${r.needs_human?`<br><span class="tag">needs human: ${esc(r.human_reason)}</span>`:''}
<ul>${ev('auth')}${ev('access')}${ev('api_surface')}${ev('mcp')}</ul>${r.api_surface.rate_limit_note?'Rate limits: '+esc(r.api_surface.rate_limit_note):''}</td></tr>`}
document.querySelector('#tbl tbody').addEventListener('click',e=>{if(e.target.closest('a'))return;const tr=e.target.closest('tr[data-id]');if(!tr)return;const id=+tr.dataset.id;open.has(id)?open.delete(id):open.add(id);draw()});
document.querySelectorAll('#tbl th').forEach(th=>th.onclick=()=>{const k=th.dataset.k;dir=sortK===k?-dir:1;sortK=k;draw()});
['q','fcat','fverd','facc'].forEach(id=>document.getElementById(id).addEventListener('input',draw));draw();
</script></body></html>"""
