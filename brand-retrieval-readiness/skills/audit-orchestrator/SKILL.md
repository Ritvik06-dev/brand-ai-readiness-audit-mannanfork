---
name: audit-orchestrator
description: Audit a website for AI-discoverability and on-site-engagement problems and emit a single evidence-backed audit report. Use when asked to audit a site or domain, or to diagnose why a brand is hard to find or misrepresented in AI assistants, or why visitors who arrive do not engage. The sole entrypoint of this marketplace; composes the six specialist skills in manifest order.
license: MIT
compatibility: Requires Python 3.9+ (standard library only) and outbound HTTPS. A headless browser is optional and only raises confidence on render checks.
metadata:
  version: "1.0.0"
---

# Audit Orchestrator (marketplace entrypoint)

> **Build status (Phase 0):** stub. Full composition procedure, `scripts/collect_snapshot.py`,
> `scripts/build_report.py`, and all `references/` land in Phases 1-2 per `BUILD_PLAN.md`.

## When to use

Stub - see description.

## Inputs

Stub: a public http(s) URL.

## Procedure

Stub: safety preflight -> bounded discovery -> shared snapshot -> specialists in manifest order
-> correlation -> report build + validation -> human summary.

## Output

Stub: one audit report JSON against `references/output_schema.json` (frozen in Phase 1).
