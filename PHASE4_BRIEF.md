# PHASE 4 BRIEF — judgment specialists (answer-coverage, freshness, offsite, referral)

Read `GAMEPLAN.md` §7 first. This brief is the execution contract for the four parallel
drafters. Gate verdicts belong to owner A. These four skills are the submission's headline:
where an LLM beats a crawler — intent, confirmation, selection (GAMEPLAN §1). Write them like
it.

## What is different from Phase 3

**No scripts.** All four are judgment skills: the deliverable is the SKILL.md (plus
`references/question_archetypes.md` for answer-coverage). The model executes the procedure at
audit time. The runtime budget is real and documented in each SKILL.md: **one read** (the
prepared excerpt file, or the named prepared file below), **one judgment**, **one write** (the
fragment), at most 3 tool calls; emit partial findings with `not_evaluated` rather than exceed.

**The model writes the fragment.** Same shape as always
(`references/finding_fragment.json`), with two Phase 4 facts:
- `candidate_finding.evidence` quotes the excerpt (≤ 200 chars) with page URL + method.
- `opportunities[]` (fragment schema v1.1) is carried by answer-coverage only: market-derived
  questions with no answering page become opportunities, never findings — a missing topic is
  not a defect. `build_report.py` merges, dedupes by title, sorts by priority, and sets
  `summary.opportunities`; they are never counted in `total_findings`.

**No script to name** — but the SKILL.md must name its prepared input file exactly and state
the one-read/one-judgment/one-write contract (the template's judgment-skills Inputs bullet).

## Prepared inputs (what each skill reads at audit time)

| Skill | Prepared input | Extras |
|---|---|---|
| answer-coverage | `audit/excerpts/answer-coverage-audit.json` | pages with page_class, heading_tree, excerpts, claims |
| freshness | `audit/excerpts/freshness-consistency-audit.json` | claim subsets + heading_tree + sitemap lastmod summary + page_dates |
| offsite | `audit/excerpts/offsite-visibility-audit.json` | prompt set + external_presence + search_declared (written by the `--passages` post-step) |
| referral | `audit/excerpts/referral-experience-audit.json` | pages_signals (overlays/accordions) + soft_404 + redirect probes; plus `audit/passages_checked.json` (post-step) |

Every excerpt file validates against `references/excerpts_schema.json` (kind: excerpt). The
referral skill reads TWO prepared files (its excerpt + passages_checked) — that is its one
read round, still ≤ 3 tool calls total.

## KILL-LIST (unchanged, plus)

1–7 as in `PHASE3_BRIEF.md` (no vendored fetch, no `answerability`, no unshipped-doc refs, no
host-specific logic, no `F-` ids, no synthesized measurements, no incident-shaped titles) —
plus: **no fabricated probes** (probe_protocol rule 1/9), **no visibility scores**, and no
Core Web Vital numbers anywhere in referral (REF-PERF-RISK stays a static risk observation).

## Per-skill contracts

### answer-coverage-audit (extract) — the headline skill

- Generates 5–8 questions from TWO sources, recorded per question: **site-derived** (what the
  sampled pages claim to answer) and **market-derived** (what a category customer asks
  regardless of what the site chose to publish — driven by `site_type`).
- Writes `audit/passages.json` (excerpts_schema `passages_file`; `question_id` Q-###, `source`,
  `intent`, `expected_page`, verbatim `candidate_passage` ≤ 2000 chars, `qualifier_present`).
- Checks: ANS-QUESTION-UNANSWERED (site-derived gaps → findings; market-derived gaps →
  `opportunities[]`), ANS-PASSAGE-INCOMPLETE, ANS-QUALIFIER-DETACHED, ANS-COMPARISON-UNREADABLE,
  ANS-BOILERPLATE-DROWNING.
- Owns `references/question_archetypes.md`: the eight archetypes (identity, capability,
  transaction, procedure, temporal, comparison, trust, local) × a site-type applicability
  matrix (saas, ecommerce, local-business, docs-developer, publisher, gov-edu,
  marketplace-platform, org-portfolio) — which archetypes apply, and what "answered" means for
  each. Do not force every archetype on every site (the check's negative control).
- Known-good bar: on agentskills.io a REAL finding already exists (the docs-index preamble →
  ANS-BOILERPLATE-DROWNING, observed in G2b) — finding it again is correct, not a false
  positive. The bar is: no critical, quoted evidence on every finding, and market-derived
  demand routed to opportunities.

### freshness-consistency-audit (trust)

- Adjudicates the claim index across pages: FRS-CLAIM-CONFLICT (prices/plans/versions/hours —
  quote both sides with page URLs), FRS-DATE-CONFLICT (visible vs structured vs sitemap
  lastmod), FRS-IMPOSSIBLE-DATE, FRS-LASTMOD-UNIFORM (low; escalates only with corroborating
  staleness evidence), FRS-STALE-VERSION.
- Do not flag: evergreen pages without dates; uniform lastmod alone; clearly labeled
  historical content; date-like tokens inside code (the collector already suppresses code
  spans — trust it, and verify on the corpus).

### offsite-visibility-audit (cite) — capability-gated

- Two modes, one SKILL.md: with `web_search` declared → live probes per
  `references/probe_protocol.md` (record engine/query/timestamp/result; ≤ 6; shed first);
  without → every OFF-\* check lands in `not_evaluated` with the protocol's reason, plus
  snapshot-only observations from `external_presence[]` (never invented results).
- OFF-\* findings carry the probe rows as evidence (the templates already demand engine,
  query, timestamp). `OFF-FACT-STATED-WRONG` additionally quotes the official page's
  contradicting statement with its URL.
- The G4 harness run has NO `web_search` — the degraded path is what runs; exercise both modes
  in your own validation if you have a search-capable session, otherwise validate the degraded
  path and say so in your return.

### referral-experience-audit (land) — half the problem statement

- Two families, kept distinct in the SKILL.md: **continuation failure** (AI-specific:
  REF-ANSWER-NOT-CONFIRMED, REF-FRAGMENT-UNSURVIVABLE, REF-COLLAPSED-ANSWER) and **generic
  friction** (REF-SOFT-404, REF-404-DEAD-END, REF-PATH-DROP-REDIRECT, REF-OVERLAY-BLOCK,
  REF-PERF-RISK).
- REF-SOFT-404 / REF-404-DEAD-END / REF-PATH-DROP-REDIRECT are deterministic relays from the
  excerpt's probe extras (no re-derivation; quote the recorded observation). REF-FRAGMENT-
  UNSURVIVABLE reads `passages_checked.json` (contiguous=false rows, with the note).
  REF-ANSWER-NOT-CONFIRMED / REF-COLLAPSED-ANSWER are semantic judgments over the excerpts and
  signals — medium cap, quoted evidence, `affected_urls` = instances.
- REF-PERF-RISK: static indicators only (image dims now in the snapshot; render-blocking
  hints); NEVER a measured Core Web Vital; typically `needs_verification` or low.
- Heading-`id` coverage stays LOW (Google AI surfaces land with text fragments, not heading
  anchors — SECOND_REVIEW §2.8 reasoning, restated in one line in the SKILL.md).

## Validation before finishing (each drafter)

1. `uvx --from skills-ref agentskills validate brand-retrieval-readiness/skills/<id>`.
2. Kill-list grep on your own files (the Phase 3 list + `web_fetch`-safe `_fetch\.py` term).
3. Dry-run your judgment against BOTH smoke artifact sets (agentskills.io + docs.python.org:
   `uv run --python 3.9 --with jsonschema tests/run_smoke.py --url <site>` → use the printed
   tempdir's `audit/excerpts/<yours>.json`): write your passages/fragment into `/tmp/`,
   validate the fragment with the real oracle:
   `uv run --with jsonschema python -c "..."` against `references/finding_fragment.json`.
4. Known-good bar: no critical; every finding quoted and mechanism-sound; market-derived gaps
   → opportunities; degraded offsite emits not_evaluated, not silence.
5. `--help` N/A (no scripts) — but the SKILL.md's Inputs section must name the prepared files
   exactly as the table above.

Return (max 12 lines): files written; checks covered; dry-run results (findings you produced
on the two known-good sites, with severities — these are real judgments, report them
honestly); proposed collector/reference changes (never improvised); anything parked.
