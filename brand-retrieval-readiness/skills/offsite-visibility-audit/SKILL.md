---
name: offsite-visibility-audit
description: Probe how retrieval surfaces answer the site's inferred prompt set - is the brand mentioned, is the official page cited, is a third party cited instead, is the fact stated correctly, is a different entity resolved. Capability-gated and evidence-not-assertion every observation records engine, query, timestamp, and result; without a search capability it degrades to snapshot-only reasoning over the site's external presence and never invents probe results. Normally invoked by audit-orchestrator; use alone only when asked specifically about off-site visibility concerns.
license: MIT
metadata:
  version: "1.0.0"
---

# Off-site Visibility Audit (cite)

> **Status:** stub — the full procedure and `references/probe_protocol.md` (phrasing and
> recording of probes) land with the Phase 4 build. This file fixes the capability gate, the
> prompt-set input contract, and the check set (OFF-* in `check_catalog.json`).

## When to use

Stub - see description.

## Inputs

- The inferred prompt set: `audit/passages.json` (questions with `source`: site-derived |
  market-derived) written by answer-coverage-audit.
- The snapshot's `external_presence[]` for the degraded (no-search) path.
- Declared capabilities: this skill runs live probes ONLY when the orchestrator declared
  `web_search`; absence of capability means `not_evaluated`, never a finding.

## Procedure (contract - full procedure lands in Phase 4)

1. Take the prompt set (cap: <= 6 queries; shed first at the deadline).
2. For each prompt, run the probe per `probe_protocol.md` and record engine, query, timestamp,
   cited URLs, and outcome class (official cited / third-party cited / mentioned-not-cited /
   absent / wrong entity / fact stated wrongly).
3. Never call a sample of prompts a visibility score. One run is an observation, not a rank.
4. Write the finding fragment to the orchestrator's `audit/findings/` path.

## Output

Finding fragment per the orchestrator's `finding_fragment.json` (checks: OFF-* per
`check_catalog.json`).
