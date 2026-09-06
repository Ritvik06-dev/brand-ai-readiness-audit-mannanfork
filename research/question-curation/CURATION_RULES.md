# Question curation rules — v1 from the 20-site muse corpus

Derived from `corpus.jsonl` (20 independent muse-spark runs, one per unseen site, constant
model: opencode-go/muse-spark-1.3-contributor and opencode/muse-spark-1.3-contributor-free).
This is the empirical answer to "how should the question set be curated, and how do we stop
the model overthinking it."

## The data

- Questions per run: min 5, max 8, **avg 6.3**; market-derived min 2 max 4, **avg 3.0**.
- Intent frequency across runs (of 20): identity 17, transaction 15,
  trust 15, capability 13, comparison 13, procedure 12, temporal 12, local 8.
- Finding yield by check across the corpus: REF-ANSWER-NOT-CONFIRMED 15/20,
  ANS-PASSAGE-INCOMPLETE 9, ACC-SITEMAP-ORPHAN 8, ANS-QUALIFIER-DETACHED 7,
  REP-TABLE-SEMANTICS 7, REF-FRAGMENT-UNSURVIVABLE 6, ANS-QUESTION-UNANSWERED 5,
  ACC-HREFLANG-INCONSISTENT 5, REF-404-DEAD-END 4, ACC-BOT-CHALLENGE 4,
  ANS-COMPARISON-UNREADABLE 4.

## Rules (data-grounded)

1. **Identity is never optional** (17/20 runs; the misses
   were no-capture runs).
   It is also the question the fold check most often fails on homepages — keep it first.
2. **transaction + trust are the near-universal core** (15/20 each, across site types —
   including gov-edu and docs sites, whose tables mark them "often"). Treat the archetype
   table's "often" row as *default-on* for these two when the site sells, charges, or
   certifies anything; skip only when the coverage appendix shows neither fees nor
   credentials anywhere.
3. **local is site-type-gated, not optional-ish** (8/20 = exactly the local-relevant types).
   The table's gating works; do not add local questions to sites without a physical or
   scheduling dimension.
4. **comparison is high-cost, medium-yield** — 13/20 runs asked one, and
   ANS-COMPARISON-UNREADABLE fired 4 times (its TP rate is fine, but the mapping work is
   the most expensive per question: grid-pairing analysis). Rule: ask a comparison question
   only when the excerpt shows a competing-option surface (pricing tiers, vs-page, plan grid);
   never invent a competitor.
5. **4–6 questions is the right cap.** The 8-question runs (razer, weavehand, wtflex) showed
   no finding-yield advantage over 5-question runs (docs-python, python.org, swayam: 2
   findings each on 5 questions) — yield comes from question→page fit, not count. The
   Tier-2 sizing change (4–6, prefer sampled pages) is confirmed by the data.
6. **Prefer sampled pages.** Every question whose expected page was not sampled ended in
   `not_evaluated` or an opportunity — zero findings. The appendix check ("is there a page
   that would carry this?") is the highest-leverage single decision in curation.
7. **Two market-derived is the floor, three is the sweet spot** (avg 2.9). Market-derived
   questions feed opportunities (which fired in 18/20 runs) and the probe set; they are also
   the phrasing that found the money case in the jaipur study. Never drop below two.

## Overthinking counter-rules (from the same corpus + the trace studies)

8. **One sentence per curation decision, then move.** The question set is 4–6 rows; any
   deliberation longer than the set itself is the failure mode. The 37K-char question-set
   design block (glm/jaipur) produced the same list as the 3K-char one (muse runs).
9. **Never re-enumerate a settled set.** Once written into `passages.json`, the set is
   frozen; gates read it, they do not rebuild it.
10. **Gates inherit the mapping; they do not re-map.** If ANS-QUESTION-UNANSWERED needed a
    fresh excerpt search to decide, the mapping step was wrong.
11. **Zero-capture sites get zero questions** — sony.co.in produced 0 findings on 0 fetched
    pages and that is the *correct* report (honest emptiness). Do not generate questions
    from site_type imagination when pages_without_content says there is nothing; emit
    not_evaluated with the capture reason.

## What this says about the check set

- The fold/confirmation family (REF-ANSWER-NOT-CONFIRMED + REF-FRAGMENT-UNSURVIVABLE,
  15/20 and 6/20) is the highest-yield judgment in the marketplace — it justifies its
  deliberation cost and must never be shed before probes.
- Deterministic checks carry real breadth (SITEMAP-ORPHAN 8, HREFLANG 5, BOT-CHALLENGE 4,
  TABLE-SEMANTICS 7) — the phase-1 scripts earn their 12 seconds many times over.
- FRS-* fired only 4 times across 20 sites (DATE-CONFLICT 3, LASTMOD 1) — freshness is a
  low-frequency, high-severity layer; its judgment stays cheap (claim matrix is pre-built)
  and should never be expanded.
