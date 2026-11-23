# Human review guide (Loop 4) - for Karan only

Seed: 20261123. Sample: 3 apps per category = 30 apps x 8 fields, plus 12 apps still flagged after Loop 3
(only their flagged fields). Total rows: 260. Apps: 93, 98, 100, 2, 3, 9, 27, 29, 30, 51, 52, 53, 62, 65, 67, 41, 42, 45, 86, 88, 90, 31, 35, 40, 71, 74, 78, 12, 14, 18, 6, 34, 47, 49, 50, 55, 58, 73, 83, 84, 91, 97.

Run `python scripts/review_server.py` and open http://localhost:8765 . For every row, open the evidence link
(and the vendor's docs if needed) and mark **pass1_correct** and **final_correct** (y/n). If a value is wrong,
type the correct value in human_value. The agent never fills these columns.

What counts as correct (judge the value, not the wording):
- one_liner: describes what the product does; minor wording issues are fine.
- auth.methods: every scheme the public API accepts for third-party access is listed and nothing extra.
  A static personal token sent as `Authorization: Bearer` = bearer_token; a key in a header/query = api_key.
  Accept api_key vs bearer_token interchangeably if the doc itself blurs them; mark n if OAuth2 is missing/extra.
- access.status: how a random developer gets working credentials TODAY. free plan / free dev account / OSS = self_serve_free;
  only a time-limited trial = self_serve_trial; must buy a plan = paid_plan_required; workspace admin must enable = admin_approval;
  build/test free but vendor approval for production = app_review; partner programme = partner_gated; talk to sales = contact_sales.
- api_surface.styles: REST/GraphQL/SOAP etc. as documented. breadth: narrow (a few endpoints), moderate, broad (many resources).
- mcp: official = MCP server published by the vendor itself; community = third-party repos. Mark n if a vendor MCP exists but is missing,
  or if a listed URL is not an MCP server for this app.
- buildability.verdict / main_blocker: could Composio build a toolkit today, and what is the single biggest obstacle.
  Judge against the definitions above, not against your preference.
Fastest path: the evidence link first; if it doesn't settle it, the vendor's auth/getting-started page and pricing page.
