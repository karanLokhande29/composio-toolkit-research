# Phase log

| when (IST) | phase | note |
|---|---|---|
| 2026-11-23 15:40 | P0 setup | Read brief + MASTER; verified Composio docs (package `composio`, keyless public catalog); scaffolded repo, apps.yaml (100), checker |
| 2026-11-23 15:45 | P1 pilot | Apps 1-5: discover (WebSearch agent) -> extract (haiku) -> loop 1; R1-R8 PASS for pilot |
| 2026-11-23 15:51 | P2 scale | Claude CLI hit plan usage limit mid-discovery (apps 39-50 lost search results; discarded) |
| 2026-11-23 16:20 | P2 scale | Limit reset; switched apps 39-100 to cheap discovery (model-proposed URLs + crawl); parallel extraction |
| 2026-11-23 16:35 | P2 scale | Pass 1 complete for all 100 apps (3 parallel extraction processes, merge-safe saves) |
| 2026-11-23 16:46 | P3 loops | Loop 1 on all 100; Loop 2 second agent on all 100; then Claude plan usage limit hit again (reset 21:20) |
| 2026-11-23 21:31 | P3 loops | Loop 1 re-run with corrected MCP rule; Loop 2 re-applied from cache; Loop 3 browser + adjudicator on 74 flagged apps |
| 2026-11-23 21:55 | P4/P5 accuracy | Human hand-check skipped by Karan (time); independent AI auditor (Claude Opus) judged the 260-row stratified sample; labelled as such on the page |
| 2026-11-23 22:02 | P6-P8 | Patterns, page, deploy to GitHub Pages; MCP weakness reported honestly |
