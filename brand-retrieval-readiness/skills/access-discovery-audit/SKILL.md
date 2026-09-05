---
name: access-discovery-audit
description: Analyze whether AI crawlers and fetchers can discover, reach, and index a site's important pages - crawler-role robots policy, noindex/nosnippet/noarchive index controls, canonicals, redirects, bot challenges, sitemaps. Normally invoked by audit-orchestrator; use alone only when asked specifically about crawl-access, index-control, or discovery concerns.
license: MIT
compatibility: Requires Python 3.9+ (standard library only) and outbound HTTPS.
metadata:
  version: "1.0.0"
---

# Access & Discovery Audit

> **Status:** stub. The Phase 3 SKILL.md and `scripts/probe_access.py` (a snapshot-only reader —
> ALL network I/O lives in `collect_snapshot.py`; this skill never fetches) land with the
> Phase 3 build.

## When to use

Stub - see description.

## Inputs

Stub: a snapshot path (or a URL for standalone mode).

## Procedure

Stub.

## Output

Stub: finding fragments per the orchestrator's `finding_fragment.json`.
