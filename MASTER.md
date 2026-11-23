# MASTER — Composio AI Product Ops Intern take-home

**This file is the single source of truth.** Save it as `MASTER.md` in the repo root. Every prompt in `PROMPTS.md` tells Claude Code to re-read it. If anything in a prompt conflicts with this file, this file wins. Do not edit the requirements (§2) — only the status tracker changes.

---

## 1. The assignment (from Composio's brief)

Composio turns apps into tools that AI agents can call. Before building a toolkit for an app, they research it: what auth it uses, whether there is a self-serve path or it is partner-gated, what the API surface looks like, and whether it can be an MCP server or agent-callable skills. They do this across hundreds of apps; by hand it doesn't scale. This is a small, real version of that problem.

- **Budget:** 6–8 hours. They care about the result and how clearly it's presented, not the hours. Submit as early as possible — **within 8 hours of receiving it**. Email received **Mon 23 Nov 2026, 15:01 IST → hard deadline ≈ 23:00 IST**.
- **Research 100 apps** (§9). For each: category + one line; auth method(s); self-serve vs gated; API surface (REST/GraphQL, breadth, existing MCP); buildability verdict + main blocker; evidence URL behind each answer; "and more".
- **The actual point — patterns.** Don't just produce 100 rows. Cluster results: which auth dominates, which categories are self-serve vs gated, the most common blocker, easy wins vs what needs outreach. **Insight over raw table.**
- **Do it with an agent, not by hand.** Build an agent/script/pipeline. Using Composio's own SDK and MCP is in the spirit of the role. Say what it does and **where it needed a human**.
- **Verify accuracy — what matters most.** Sample the 100, cross-check against real docs by hand, report right vs wrong. Build real verification loops (agent, browser-use, other means) plus human checks; show how it was verified, including **how accuracy moved from a lower first pass to a higher one because of those loops**.
- **Deliverable:** a single self-explanatory HTML page / slideshow / case study a reviewer understands in ~2 minutes with no narration, showing: findings (clean skimmable table/matrix), patterns (up top, plainly stated, the headline), the agent (what was built, where a human was needed), the proof (live link or runnable trigger), and the verification (sample accuracy, hits and misses shown honestly). Show both the final output and the process/workflow. Easy for **both an agent and a human** to consume.
- **Constraints & honesty:** AI tooling is fine, but I must understand and explain everything (the interview will probe it). If the agent got things wrong or an app defeated us, say so on the page. No paid accounts needed; a payment/partner gate stated with evidence is a correct finding, not a failure.
- **Submit:** (1) live link to the deployed page; (2) source repo link with a short README on how to run the research agent. Submission is via the Google Form linked in the email.

---

## 2. Requirements register (IDs are used everywhere for traceability)

| ID | Requirement | How it is checked |
|---|---|---|
| R1 | All 100 apps from §9 present, ids 1–100, none duplicated | AUTO |
| R2 | Each app has category + one-line description | AUTO |
| R3 | Each app has auth method(s) (or `unknown` + reason) | AUTO |
| R4 | Each app has access status: self-serve vs gated (or `unknown` + reason) | AUTO |
| R5 | Each app has API surface: style(s), breadth, existing MCP (official/community/none) | AUTO |
| R6 | Each app has buildability verdict + main blocker + one-sentence rationale | AUTO |
| R7 | Every non-`unknown` answer has ≥1 evidence URL that was actually fetched (in cache) and a snippet that literally appears in that cached page | AUTO |
| R8 | "And more" fields captured (sandbox, webhooks, OpenAPI spec, rate-limit note, Composio toolkit exists) | AUTO (presence) |
| R9 | Patterns computed in code: auth distribution, self-serve vs gated by category, top blockers, MCP coverage, easy wins vs needs-outreach; every headline has a number from `data/patterns.json` | AUTO + MANUAL |
| R10 | Research is done by an agent/pipeline, not by hand; Composio SDK/MCP used where possible (fallbacks documented) | MANUAL |
| R11 | Every point a human was needed is logged in `logs/human_interventions.md` and shown on the page | AUTO (file non-empty) + MANUAL |
| R12 | Verification loops implemented: deterministic checks, independent second agent, browser loop | AUTO (logs exist) + MANUAL |
| R13 | Human cross-check on a stratified sample; per-field right/wrong recorded by Karan (never by the agent) | AUTO (sheet filled) |
| R14 | Accuracy shown for pass 1 vs final, computed only from logged data, with hits AND misses | AUTO |
| R15 | One self-contained HTML page (`site/index.html`), readable in ~2 minutes, works on mobile | AUTO + MANUAL |
| R16 | Page sections present in order: headline patterns → easy wins/outreach → findings matrix → agent + human-needed → verification → proof → process/workflow → limitations | AUTO (section ids) |
| R17 | Machine-readable: embedded JSON on the page + `results.json`, `patterns.json`, `llms.txt` published | AUTO |
| R18 | Honesty: wrong answers, unresolved apps and failures stated on the page | AUTO (list non-empty or explicit "none") + MANUAL |
| R19 | No paid accounts used; gated apps reported with evidence | MANUAL |
| R20 | Karan can explain everything: `docs/INTERVIEW_NOTES.md` explains each component in plain words | AUTO (file) + MANUAL |
| R21 | Page is deployed and the live URL returns 200 | AUTO (once deployed) |
| R22 | Repo has README: setup, `.env.example`, how to run the agent, architecture, verification method | AUTO |
| R23 | Submitted before ≈23:00 IST, 23 Nov 2026 | MANUAL |
| R24 | No secrets committed (`.env` ignored, secret scan clean) | AUTO |

Status values: `PASS`, `FAIL`, `PARTIAL`, `NOT_YET` (phase not reached), `MANUAL_PENDING`.

---

## 3. Continuous requirements check (applies to EVERY prompt)

1. **Start of every prompt:** re-read `MASTER.md` and `REQUIREMENTS_STATUS.md`; run `python scripts/check_requirements.py`; print the summary table.
2. **During work:** before marking any step done, ask "which R-IDs does this touch, and does it still satisfy them?" If a change would break an R-ID, stop and tell Karan.
3. **End of every prompt (the gate):** run the checker again; update `REQUIREMENTS_STATUS.md` (status, evidence/file path, last-checked time per R-ID); append a line to `logs/phase_log.md`.
4. **Gate rule:** if any R-ID that belongs to the current or an earlier phase is `FAIL`, fix it before declaring the phase done. If it can't be fixed in budget, say so plainly and propose an option — never hide it, never mark it PASS without evidence.
5. **Never self-certify MANUAL items.** Mark them `MANUAL_PENDING` and list what Karan must check.
6. **Clock check:** print current IST time vs the phase budget and the 23:00 deadline at the start and end of every prompt.

`scripts/check_requirements.py` must: read the data/site/repo files, evaluate every AUTO check above, print a table (ID, status, detail), write `reports/requirements_check.json`, and exit non-zero if a FAIL exists for a reached phase. Checks for phases not reached yet return `NOT_YET`, not FAIL.

---

## 4. Hard rules

1. **No fabrication.** A value is either backed by a fetched URL + verbatim snippet, or it is `unknown` with a reason.
2. **Verify before asserting — including Composio itself.** Read current official docs (docs.composio.dev, the SDK README/GitHub) for the exact package name, install command, env vars and method names before writing Composio code. Same for every library.
3. **Human verdicts are only Karan's.** Never fill `human_value` / `correct` columns.
4. **Secrets in `.env` only** (git-ignored); ship `.env.example`; never print keys.
5. **Terminal-first.** When Karan must act, give exact copy-paste commands in one code block.
6. **Small first, then scale:** 5 apps → 100 apps.
7. **Reproducible & polite:** cache every fetched page (`cache/`, keyed by URL hash, with timestamp); rate-limit; set a user agent.
8. **Keep it explainable:** plain Python, short modules, comments where non-obvious, no heavy framework Karan can't explain.
9. **Don't force non-SaaS entries** (Sherlock, Mermaid CLI are CLI/OSS tools; YouTube Transcript points at a third-party API) into the SaaS mould — classify honestly.

---

## 5. Data schema (`data/results.json`, one object per app)

```json
{
  "id": 1, "app": "Salesforce", "category": "CRM and Sales", "hint": "salesforce.com",
  "one_liner": "",
  "auth": {"methods": ["oauth2|api_key|basic|bearer_token|jwt|other|unknown"], "oauth_grant_types": [], "notes": "", "evidence": [{"url": "", "snippet": ""}]},
  "access": {"status": "self_serve_free|self_serve_trial|paid_plan_required|admin_approval|app_review|partner_gated|contact_sales|unknown",
             "dev_sandbox": null, "notes": "", "evidence": []},
  "api_surface": {"styles": ["rest|graphql|soap|websocket|sdk_only|cli_or_library_only|none"], "breadth": "narrow|moderate|broad|unknown",
                  "openapi_spec_url": null, "webhooks": null, "rate_limit_note": "", "evidence": []},
  "mcp": {"official": null, "community": [], "evidence": []},
  "buildability": {"verdict": "ready|ready_with_caveats|blocked", "main_blocker": "none|partner_gate|paid_plan|app_review|admin_scope|no_public_api|cli_only|other",
                   "rationale": "", "composio_existing_toolkit": "yes|no|unknown"},
  "confidence": 0.0,
  "pass1": {},
  "verification": {"checks": [], "disagreements": [], "resolved_by": "agent|browser|human|unresolved", "human_checked": false},
  "needs_human": false, "human_reason": ""
}
```

---

## 6. Repo layout

```
MASTER.md  REQUIREMENTS_STATUS.md  README.md  .env.example  .gitignore
apps.yaml                     # §9
run.py                        # CLI: python run.py --apps 1-100 --stage discover|fetch|extract|verify|analyze|page|all
src/discover.py fetch.py extract.py verify.py second_agent.py browser_check.py metrics.py analyze.py build_page.py
scripts/check_requirements.py
data/results.json  data/patterns.json  data/metrics.json
cache/                        # fetched pages
human_review/sample.csv  human_review/sample.md
logs/phase_log.md  logs/human_interventions.md  logs/verification_log.jsonl
docs/INTERVIEW_NOTES.md
site/index.html  site/results.json  site/patterns.json  site/llms.txt
.github/workflows/research.yml   # workflow_dispatch: run agent on chosen app ids, upload JSON artifact
```

---

## 7. Verification design

- **Pass 1:** single agent extraction → snapshot into `pass1`.
- **Loop 1 — deterministic:** URL returns 200; snippet present in cached text (normalised whitespace); schema valid; consistency rules (e.g. `partner_gated` + `ready` → flag; `oauth2` with no OAuth evidence → flag; MCP URL not a repo/docs page → flag).
- **Loop 2 — independent second agent:** re-research blind to pass 1 (different prompt; different model or temperature if available); flag field-level disagreements.
- **Loop 3 — browser:** headless browser (Playwright or browser-use) on flagged items and JS-rendered docs; re-extract and resolve.
- **Loop 4 — human (Karan):** stratified sample, fixed printed seed: 3 apps per category = 30, plus anything still flagged after Loop 3. Karan fills `human_review/sample.csv`.
- **Metrics:** field-level accuracy on the human sample for pass 1 vs final (per field, per category); every miss listed with which loop caught it (or none); % of the 100 changed by automated loops. Only from logged data.

---

## 8. Page spec (`site/index.html`, single self-contained file, vanilla JS, no build step)

Section ids (checked automatically): `#headline`, `#wins-outreach`, `#matrix`, `#agent`, `#human-needed`, `#verification`, `#proof`, `#process`, `#limitations`.

1. **#headline** — 4–6 plain-sentence patterns, each with its number, + 2–3 small charts (auth mix; self-serve vs gated by category; top blockers).
2. **#wins-outreach** — easy wins vs needs-outreach lists (frame as useful to Composio).
3. **#matrix** — all 100 apps; search, filter, sort; colour-coded verdicts; each cell links to its evidence.
4. **#agent** — one pipeline diagram + what each stage does. **#human-needed** — from `logs/human_interventions.md`.
5. **#verification** — pass-1 → final accuracy per field, sample size/method, honest hits & misses table.
6. **#proof** — repo link, one-line run command, GitHub Actions trigger link.
7. **#process** — timeline of what was done, phase by phase.
8. **#limitations** — what the agent couldn't do, apps that defeated it, next steps.

Also: `<script type="application/json" id="data">` with the full results; publish `results.json`, `patterns.json`, `llms.txt` alongside. Semantic HTML, accessible colours, mobile-friendly. Deploy to GitHub Pages (or Vercel).

---

## 9. The 100 apps (source for `apps.yaml`)

```csv
id,app,category,hint
1,Salesforce,CRM and Sales,salesforce.com
2,HubSpot,CRM and Sales,hubspot.com
3,Pipedrive,CRM and Sales,pipedrive.com
4,Attio,CRM and Sales,attio.com
5,Twenty,CRM and Sales,twenty.com (open-source CRM)
6,Podio,CRM and Sales,podio.com
7,Zoho CRM,CRM and Sales,zoho.com/crm
8,Close,CRM and Sales,close.com
9,Copper,CRM and Sales,copper.com
10,DealCloud,CRM and Sales,api.docs.dealcloud.com
11,Zendesk,Support and Helpdesk,zendesk.com
12,Intercom,Support and Helpdesk,intercom.com
13,Freshdesk,Support and Helpdesk,freshdesk.com
14,Front,Support and Helpdesk,front.com
15,Pylon,Support and Helpdesk,usepylon.com
16,LiveAgent,Support and Helpdesk,liveagent.com
17,Plain,Support and Helpdesk,plain.com
18,Help Scout,Support and Helpdesk,helpscout.com
19,Gorgias,Support and Helpdesk,gorgias.com
20,Gladly,Support and Helpdesk,gladly.com
21,Slack,Communications and Messaging,slack.com
22,Twilio,Communications and Messaging,twilio.com
23,Zoho Cliq,Communications and Messaging,zoho.com/cliq
24,Lark (Larksuite),Communications and Messaging,open.larksuite.com
25,Pumble,Communications and Messaging,pumble.com
26,Discord,Communications and Messaging,discord.com
27,Telegram,Communications and Messaging,core.telegram.org
28,WhatsApp Business,Communications and Messaging,developers.facebook.com/docs/whatsapp
29,Aircall,Communications and Messaging,aircall.io
30,Vonage,Communications and Messaging,developer.vonage.com
31,Google Ads,"Marketing, Ads, Email and Social",developers.google.com/google-ads
32,Meta Ads,"Marketing, Ads, Email and Social",developers.facebook.com/docs/marketing-apis
33,LinkedIn Ads,"Marketing, Ads, Email and Social",learn.microsoft.com/linkedin/marketing
34,GoHighLevel,"Marketing, Ads, Email and Social",highlevel.stoplight.io
35,Mailchimp,"Marketing, Ads, Email and Social",mailchimp.com/developer
36,Klaviyo,"Marketing, Ads, Email and Social",developers.klaviyo.com
37,systeme.io,"Marketing, Ads, Email and Social",systeme.io (funnel builder)
38,Pinterest,"Marketing, Ads, Email and Social",developers.pinterest.com
39,Threads (Meta),"Marketing, Ads, Email and Social",developers.facebook.com/docs/threads
40,SendGrid,"Marketing, Ads, Email and Social",sendgrid.com
41,Shopify,Ecommerce,shopify.dev
42,WooCommerce,Ecommerce,woocommerce.com/document/woocommerce-rest-api
43,BigCommerce,Ecommerce,developer.bigcommerce.com
44,Salesforce Commerce Cloud,Ecommerce,developer.salesforce.com/docs/commerce
45,Magento (Adobe Commerce),Ecommerce,developer.adobe.com/commerce
46,Squarespace,Ecommerce,developers.squarespace.com
47,Ecwid,Ecommerce,api-docs.ecwid.com
48,Gumroad,Ecommerce,gumroad.com/api
49,Amazon Selling Partner,Ecommerce,developer-docs.amazon.com/sp-api
50,fanbasis,Ecommerce,fanbasis.com
51,DataForSEO,"Data, SEO and Scraping",docs.dataforseo.com
52,SE Ranking,"Data, SEO and Scraping",seranking.com/api
53,Ahrefs,"Data, SEO and Scraping",ahrefs.com/api
54,MrScraper,"Data, SEO and Scraping",docs.mrscraper.com
55,Apify,"Data, SEO and Scraping",docs.apify.com
56,Firecrawl,"Data, SEO and Scraping",firecrawl.dev
57,Bright Data,"Data, SEO and Scraping",brightdata.com
58,Sherlock,"Data, SEO and Scraping",github.com/sherlock-project/sherlock
59,Waterfall.io,"Data, SEO and Scraping",waterfall.io (contact/company intel)
60,Clay,"Data, SEO and Scraping",clay.com
61,GitHub,"Developer, Infra and Data platforms",docs.github.com/rest
62,Vercel,"Developer, Infra and Data platforms",vercel.com/docs/rest-api
63,Netlify,"Developer, Infra and Data platforms",docs.netlify.com/api
64,Cloudflare,"Developer, Infra and Data platforms",developers.cloudflare.com/api
65,Supabase,"Developer, Infra and Data platforms",supabase.com/docs
66,Neo4j,"Developer, Infra and Data platforms",neo4j.com/docs/api
67,Snowflake,"Developer, Infra and Data platforms",docs.snowflake.com
68,MongoDB Atlas,"Developer, Infra and Data platforms",mongodb.com/docs/atlas/api
69,Datadog,"Developer, Infra and Data platforms",docs.datadoghq.com/api
70,Sentry,"Developer, Infra and Data platforms",docs.sentry.io/api
71,Notion,Productivity and Project Management,developers.notion.com
72,Airtable,Productivity and Project Management,airtable.com/developers
73,Linear,Productivity and Project Management,developers.linear.app
74,Jira,Productivity and Project Management,developer.atlassian.com
75,Asana,Productivity and Project Management,developers.asana.com
76,Monday.com,Productivity and Project Management,developer.monday.com
77,ClickUp,Productivity and Project Management,clickup.com/api
78,Coda,Productivity and Project Management,coda.io/developers
79,Smartsheet,Productivity and Project Management,smartsheet.com/developers
80,Harvest,Productivity and Project Management,harvestapp.com (help.getharvest.com/api-v2)
81,Stripe,Finance and Fintech,stripe.com/docs/api
82,Plaid,Finance and Fintech,plaid.com/docs
83,Binance,Finance and Fintech,binance-docs.github.io
84,Paygent Connect,Finance and Fintech,paygent (NMI-powered)
85,iPayX,Finance and Fintech,ipayx.ai/docs
86,QuickBooks,Finance and Fintech,developer.intuit.com
87,Xero,Finance and Fintech,developer.xero.com
88,Brex,Finance and Fintech,developer.brex.com
89,Ramp,Finance and Fintech,docs.ramp.com
90,PitchBook,Finance and Fintech,pitchbook.com (research API)
91,NotebookLM,"AI, Research and Media-native",cloud.google.com/gemini (Enterprise API)
92,Otter AI,"AI, Research and Media-native",help.otter.ai (MCP server)
93,Fathom,"AI, Research and Media-native",fathom.video
94,Consensus,"AI, Research and Media-native",consensus.app (OAuth requested)
95,Reducto,"AI, Research and Media-native",reducto.ai (document parsing)
96,Devin,"AI, Research and Media-native",docs.devin.ai (MCP)
97,higgsfield,"AI, Research and Media-native",higgsfield.ai/cli (content suite)
98,Mermaid CLI,"AI, Research and Media-native",github.com/mermaid-js/mermaid-cli
99,YouTube Transcript,"AI, Research and Media-native",transcriptapi.com
100,Grain,"AI, Research and Media-native",grain.com (meeting notes)
```
