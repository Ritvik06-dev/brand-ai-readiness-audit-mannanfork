---
name: answer-coverage-audit
description: Judge whether the questions a category's customers actually ask are answered by complete, extractable passages on the site — using a two-source prompt set (site-derived and market-derived questions), checking for unanswered category-standard questions, answers missing subject/units/timeframe, qualifiers detached from their claims, comparison data trapped in unlabelled grids, and boilerplate swamping the answer. Normally invoked by audit-orchestrator; use alone only when asked specifically about answer-coverage or content-extractability concerns.
license: MIT
metadata:
  version: "1.0.0"
---

# Answer Coverage Audit (extract)

This skill guards the **extract** stage, and it carries the submission's central bet: an
algorithm can check whether a page contains a keyword, but only a judgment can say what a
customer in this category was actually trying to accomplish, and whether this page is the
answer to the question that would surface it. Google's own AI-features guidance says there are
"no additional requirements to appear in AI Overviews or AI Mode" — meaning retrieval systems
answer from whatever extractable passages exist. A page whose answer cannot be extracted is an
answer that loses to a competitor's extractable one, regardless of quality.

The two-source contract: **site-derived** questions ask what these pages claim to answer;
**market-derived** questions ask what a customer in this category would ask regardless. The
gap between them is where the findings and the opportunities live.

## When to use

- Someone asks why assistants answer questions about their category without citing them.
- A site owner wants to know which category-standard questions their site cannot answer.
- Out of scope: whether facts are retrievable by non-rendering crawlers
  (representation-parity-audit), whether answers are current (freshness-consistency-audit),
  whether the site is cited off-site (offsite-visibility-audit).

## Inputs

- Prepared excerpt file `audit/excerpts/answer-coverage-audit.json` (one read): pages with
  `url`, `page_class`, `title`, `heading_tree`, `main_content_excerpts` (≤1,500 chars per
  location with `char_offset`), and `claim_index_subset`.
- The snapshot's `site_type` (recorded in the snapshot; the orchestrator relays it).
- Archetype applicability: `references/question_archetypes.md`.
- Runtime contract: one read, one judgment, one write — at most 3 tool calls. Emit partial
  findings with `not_evaluated` rather than exceed it. Judge from the excerpt — it carries
  everything rated to this skill's checks; re-reading the full snapshot duplicates work the
  scripts already did.

## Procedure

1. **Generate the question set** per `references/question_archetypes.md`: 5–8 questions
   weighted toward the site type's core archetypes, at least two market-derived. Record each
   question's `source` and `intent`.
2. **Map and judge.** For each question find the expected page and its best candidate passage
   (verbatim, ≤2,000 chars). Judge completeness: subject explicit, claim with units/timeframe,
   qualifier attached (the `qualifier_present` field). Judge extractability: heading path gives
   the passage context; comparison data survives the grid.
   **Quote granularity rule:** `candidate_passage` is the specific answer sentence(s) — one
   paragraph, at most ~600 characters, never a multi-section dump. Oversized passages make
   the referral skill's fragment-survivability check measure your quoting style instead of
   the site; if the answer genuinely needs more than ~600 characters, redraw tighter or leave
   the question to `opportunities`.
3. **Write `audit/passages.json`** (excerpts_schema `passages_file`): shape literal
   `{"kind": "passages", "skill_id": "answer-coverage-audit", "questions": [...]}` — the
   array key is `questions`, never `passages`. Every question with its
   `expected_page`, verbatim `candidate_passage`, `qualifier_present`, `source_location`. For
   unanswered questions write the best near-miss passage you can find or omit the entry — the
   orchestrator's `--passages` post-step tolerates missing pages.
4. **Gate the checks** and write the fragment to the orchestrator's `audit/findings/` path:
   - **ANS-QUESTION-UNANSWERED** — a *core* archetype question with no official answering
     passage. Site-derived gap: finding (the site claims the territory and does not cover it).
     Market-derived gap: `opportunities[]` entry (unmet demand — the site never claimed it),
     never a finding.
   - **ANS-PASSAGE-INCOMPLETE** — the passage exists but omits subject, units, or timeframe;
     extracted alone it under-informs.
   - **ANS-QUALIFIER-DETACHED** — the claim is stated without the qualifier that scopes it
     (plan tier, region, exception), and the qualifier lives on another page or behind
     interaction.
   - **ANS-COMPARISON-UNREADABLE** — a comparison question's data sits in a grid whose
     plan-value pairing does not survive extraction (pair with REP-TABLE-SEMANTICS; do not
     double-report the same defect).
   - **ANS-BOILERPLATE-DROWNING** — repeated boilerplate precedes or swamps main content in
     extraction. The gate is quantified and aligned with REP-EXTRACTION-LOSS's displacement
     bar: a shared preamble on at least half the sampled pages **AND** median unique-content
     offset **above 1,500 characters**. Below that (e.g. a 130–300 character docs-index nav
     with content starting at ~300) it is orientation — pass, with the measured numbers
     recorded as the non-evidence. A broken sentence inside the preamble is a separate
     ANS-PASSAGE-INCOMPLETE fact, not this check.

## Findings (authoring rules)

- Titles follow each check's `pattern_template`; evidence follows `evidence_template` — counts
  with denominators and quotes ≤ 200 chars with page URL and `char_offset`. Titles state
  site-level patterns, never one question's story.
- When NOT to flag (negative controls), in plain words, per check:
  - ANS-QUESTION-UNANSWERED: the archetype does not apply to this site type — skip it; a
    market-derived question the site never claimed goes to `opportunities[]`, not findings;
    "answered by a third party" is this finding's *mechanism*, not a pass.
  - ANS-PASSAGE-INCOMPLETE: a complete, self-contained passage for the same question exists
    elsewhere on the page.
  - ANS-QUALIFIER-DETACHED: the qualifier is attached in the same passage.
  - ANS-COMPARISON-UNREADABLE: the grid is semantic, or the same comparison exists as
    extractable labeled text.
  - ANS-BOILERPLATE-DROWNING: the preamble is a few hundred characters of orientation and
    unique content starts early.
- Severity and confidence are separate; follow
  `../audit-orchestrator/references/severity_model.md`. Every ANS gate is a semantic judgment:
  `evidence_quality: "semantic-judgment"`, capped at medium confidence unless a deterministic
  observation (a claim-index conflict, a measured preamble length) corroborates it.
- opportunities[] entries carry `title`, `rationale` (the demand and the gap), `priority`
  (weighted by archetype centrality), and are carried ONLY here — never as findings.

## Output

- `audit/passages.json` (for the `--passages` post-step) and the finding fragment
  (excerpts_schema `passages_file` shape; fragment per
  `../audit-orchestrator/references/finding_fragment.json`, including its `opportunities[]`).
- Never assign `F-` ids; the orchestrator does. Done means valid: the fragment parses as
  JSON and matches `finding_fragment.json` before handoff (`python3 <orchestrator>/scripts/validate_fragment.py <fragment>` (checks the schema, not just syntax)) — an unvalidated fragment is not a handoff. Building it programmatically (e.g.
  `json.dump`) avoids the most common failure here. State in your summary which questions were
  market-derived so the offsite probe set inherits the right phrasing.
