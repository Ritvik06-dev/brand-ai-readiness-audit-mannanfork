---
name: freshness-consistency-audit
description: Judge freshness and version integrity from the snapshot's claim index - cross-page contradictions on prices, plans, versions and hours; date conflicts between visible text, structured dateModified and sitemap lastmod; impossible dates; uniform build-stamp lastmod; and superseded products, versions or deprecated docs that stay linked and indexable without supersession signals. Normally invoked by audit-orchestrator; use alone only when asked specifically about staleness, dates, or versioning concerns.
license: MIT
allowed-tools: Bash Read Write
metadata:
  version: "1.0.0"
---

# Freshness & Consistency Audit (trust)

This skill guards the **trust** stage: can a retrieval system tell which version of a fact is
current? The mechanism is cross-web agreement turned inward — a claim that the site states two
different ways is a claim an assistant must adjudicate, and it will pick one; when the loser
is what the customer acts on, that is misrepresentation the brand never wrote. Google's
structured-data guidelines require sites to "provide up-to-date information" and warn they
"won't show a rich result for time-sensitive content that is no longer relevant"
(developers.google.com/search/docs/appearance/structured-data/sd-policies) — freshness
conflicts are the measurable, on-site form of that failure.

## When to use

- Someone asks why assistants quote an old price, plan, or version of their product.
- A site owner wants to know whether its pages contradict each other or its own dates lie.
- Out of scope: whether a claim is complete as a standalone answer (answer-coverage-audit);
  whether structured data matches the visible page it sits on — same-page conflicts are
  entity-consistency-audit's ENT-STRUCTURED-VISIBLE-CONFLICT; this skill adjudicates
  **cross-page** contradictions (pair them; do not double-report one root cause).

## Inputs

- Prepared excerpt file `audit/excerpts/freshness-consistency-audit.json` (one read): per page
  `url`, `page_class`, `title`, `heading_tree` (context for adjudication), excerpts, and
  `claim_index_subset` (repeated identical claims arrive capped with `count`); extras carry
  `sitemap` (lastmod present/distinct counts + sample) and `page_dates` (structured dates
  per page + visible date claims). `extras.checks` carries the check templates;
  `extras.fragment_shape` the fragment keys.
- Snapshot context relayed by the orchestrator when needed: `sitemap.lastmod_distinct_count`.
- Runtime contract: judge from the excerpt only, in a single pass, and write the fragment
  once; emit partial findings with `not_evaluated` rather than overrun.
  `extras.fragment_shape` is the complete fragment contract — never open `finding_fragment.json`.

## Procedure

1. **Build the claim matrix** from the excerpt's `claim_index_subset`: group by claim type and
   semantic identity (the "Pro plan price", "SSO availability", "v3 support window") across
   pages. Start from `extras.claim_matrix` (type-grouped quotes with page URLs and scoping
   context — grouping only, never verdicts); verify each pair against the subsets before ruling.
2. **Adjudicate groups** — the judgment the script cannot make:
   - **FRS-CLAIM-CONFLICT**: two pages state materially different values for the same fact
     with no on-page scoping (tier, region, date-of-publication). Quote both sides with their
     URLs and any visible dates. Escalate to high when the conflicting value is the one a
     transaction or procedure depends on.
   - **FRS-DATE-CONFLICT**: visible dates vs structured `dateModified` vs sitemap `lastmod`
     disagree on the same page beyond plausible publishing lag. Quote the values and their
     sources.
   - **FRS-IMPOSSIBLE-DATE**: dates in the future relative to audit time, or structurally
     impossible (Feb 30). Verify the extractor did not misparse a version or price first —
     the negative control.
   - **FRS-LASTMOD-UNIFORM**: `lastmod_distinct_count` ≈ 1 across a meaningful sample. This is
     a LOW finding alone — it escalates only when a page's visible content is clearly older
     than the uniform stamp (corroborating staleness).
   - **FRS-STALE-VERSION**: current pages link into deprecated versions, docs, or product
     pages that carry no supersession signal ("deprecated", "superseded by", redirect). The
     heading_tree gives the section context; quote the linking page and the stale target.
3. **Gate and write** the fragment to the orchestrator's `audit/findings/` path.

## Findings (authoring rules)

- Titles follow each check's `pattern_template`; evidence follows `evidence_template` — counts
  with denominators, both sides of any conflict quoted with their page URLs. Titles state
  site-level patterns ("The site states different prices for the same plan across pages"),
  never one page's slip.
- When NOT to flag (negative controls), in plain words, per check:
  - FRS-CLAIM-CONFLICT: differences that are intentional tier/regional variants clearly scoped
    on-page; a "from $X" homepage vs an exact plan page is scoping, not conflict — unless the
    qualifier is missing (that is answer-coverage's ANS-QUALIFIER-DETACHED; pair, don't
    double-report).
  - FRS-DATE-CONFLICT: publishing lag within days; dates the extractor misread.
  - FRS-IMPOSSIBLE-DATE: extractor misparses (a version string or price read as a date) —
    verify semantic context before flagging.
  - FRS-LASTMOD-UNIFORM: varied lastmod that tracks content; a small sitemap; uniformity
    without any corroborating staleness — never above low.
  - FRS-STALE-VERSION: clearly labeled historical or archive content; a versioned docs set
    where old versions are intentionally published and marked as non-current.
- Severity and confidence are separate; follow
  `../audit-orchestrator/references/severity_model.md`. Contradiction adjudication is a
  semantic judgment (`evidence_quality: "semantic-judgment"`, capped at medium) unless both
  sides carry deterministic quotes from the claim index (then `indirect-corroborated`).
  Date arithmetic is deterministic: `direct-measurement`. A failed or missing observation is
  `not_evaluated` with a reason, never a finding.

## Output

- The finding fragment to the orchestrator's `audit/findings/` path, shaped by
  `../audit-orchestrator/references/finding_fragment.json`. Never assign `F-` ids; the
  orchestrator does. Done means valid: the fragment parses as JSON and matches
  `finding_fragment.json` before handoff (`python3 <orchestrator>/scripts/validate_fragment.py <fragment>` (checks the schema, not just syntax)) — an
  unvalidated fragment is not a handoff. Building it programmatically (e.g. `json.dump`). If writing JSON through a shell heredoc instead, quote the delimiter (`<<'EOF'`). Report which pages supplied each side of every conflict so the
  remediation can name the source of truth.
