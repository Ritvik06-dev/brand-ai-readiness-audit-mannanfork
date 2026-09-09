---
name: answer-coverage-audit
description: Judge whether the questions a category's customers actually ask are answered by complete, extractable passages on the site — using a two-source prompt set (site-derived and market-derived questions), checking for unanswered category-standard questions, answers missing subject/units/timeframe, qualifiers detached from their claims, comparison data trapped in unlabelled grids, and boilerplate swamping the answer. Normally invoked by audit-orchestrator; use alone only when asked specifically about answer-coverage or content-extractability concerns.
license: MIT
compatibility: Requires Python 3.9+ (standard library only).
allowed-tools: Bash Read Write
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
  location with `char_offset`), and `claim_index_subset`. `extras.checks` carries the check
  templates; `extras.fragment_shape` the fragment keys. `extras.boilerplate` carries the
  measured preamble/offset stats from the phase-1 script; `extras.phase1_findings` lists
  the phase-1 findings (pairing without re-reading fragments); `extras.suggested_slots`
  suggests archetype/page pairs (you still phrase and judge every question);
  `extras.authoring_rules` and `extras.severity_facts` are the composed-run contract.
- The snapshot's `site_type` (recorded in the snapshot; the orchestrator relays it).
- Archetype applicability: `references/question_archetypes.md`.
- Runtime contract: judge from the excerpt only, in a single pass, and write the fragment
  once; emit partial findings with `not_evaluated` rather than overrun. If a read
  truncates, continue from the truncation offset — do not restart or re-open.
  **Set-freeze:** once `audit/passages.json` is written, the question set is frozen — the
  gates read it and never rebuild or re-enumerate it.
  **Timebox:** check the script-printed elapsed before authoring; past 150 s, map and judge
  the core-archetype questions only and emit the rest `not_evaluated` (`timebox: ...`) —
  a partial fragment beats an overrun.
  `extras.fragment_shape` is the complete fragment contract — never open `finding_fragment.json`.

## Procedure

1. **Generate the question set** per `references/question_archetypes.md`: 4–6 questions
   weighted toward the site type's core archetypes, at least two market-derived. Record each
   question's `source` and `intent`. `extras.coverage_appendix` (heading inventory, nav labels,
   claim-topic counts) aids coverage — apply the archetypes without restating the table; model
   still authors every question; never emit appendix rows
   as questions. Defaults: identity always; transaction and trust on unless the appendix shows
   neither fees nor credentials anywhere; local only when the site type calls for it;
   comparison only when the excerpt shows a competing-option surface (tier grids, a
   vs-page, a plan grid) — never invent a competitor.
   Prefer questions whose expected page is in the sample: an unmapped question can only end
   in `not_evaluated` or an opportunity, never a finding. If the excerpt carries no sampled
   pages (no capture), emit every ANS check as `not_evaluated` ("no capture") — generate no
   questions from site-type imagination. Curation budget: one sentence per question
   decision; a deliberation longer than the question set itself is the failure mode.
2. **Map and judge.** For each question find the expected page and its best candidate passage
   (verbatim, ≤2,000 chars). Judge completeness: subject explicit, claim with units/timeframe,
   qualifier attached (the `qualifier_present` field). Judge extractability: heading path gives
   the passage context; comparison data survives the grid.
   **Quote granularity rule:** `candidate_passage` is the specific answer sentence(s) — one
   paragraph, at most ~600 characters, never a multi-section dump; if the answer genuinely
   needs more than ~600 characters, redraw tighter or leave the question to `opportunities`.
   You do NOT copy passages by hand: quote a short verbatim **anchor** (≤~20 words, exactly
   as the excerpt renders it, dashes and punctuation included) into the draft, and let
   `build_passages.py` expand it to the sentence-bounded passage (see step 3).
   **Draw every anchor from inside one entry of that page's `anchorable_runs`.** Those are
   the page's contiguous extraction blocks — the only text a passage can be cut from — so an
   anchor taken from inside one resolves on the first build. An anchor assembled across two
   runs cannot resolve, by construction. Two further uses of the same field: it carries
   content the capped `main_content_excerpts` may not reach, so check it before calling a
   question unanswered; and `repeats_on_pages` > 1 marks templated boilerplate, which anchors
   fine but is never a per-page fact. If the builder still reports a failure, re-anchor that
   question only — a quoting-fidelity signal, not a site defect.
   A page whose only long runs are brand-story prose, with every commercial fact under the
   40-character floor, is itself the ANS-PASSAGE-INCOMPLETE / REP-TABLE-SEMANTICS evidence.
3. **Build `audit/passages.json`** via `build_passages.py` (see Output). The draft is the
   whole contract, one object per question:

   ```json
   {"questions": [
     {"question_id": "Q-001", "question": "How much does the Pro plan cost?",
      "source": "market-derived", "intent": "transaction",
      "expected_page": "https://example.com/pricing",
      "anchor": "Pro is $29 per user per month", "qualifier_present": false}
   ]}
   ```

   Omit `anchor` entirely for a question the site does not answer; keep the entry. The
   script cuts the ≤600-char passage from the anchor's own block, so contiguity holds by
   construction, and writes `kind`/`skill_id`/`questions`.
   **It always writes.** Resolved questions are kept even when others fail, so a repair pass
   re-anchors only the FAIL lines and never redrafts the set. Each question comes back with
   an `anchor_status`: `resolved`, `unanswered` (no anchor drafted — a site gap), or
   `unresolved` (an anchor was drafted but would not pin). **`unresolved` is never evidence
   that a question is unanswered** — it means the fact is stated in fragments, which pairs
   with REP-*. Leave it unresolved and say so rather than forcing an anchor.
4. **Gate the checks** and write the fragment to the orchestrator's `audit/findings/` path:
   - **ANS-QUESTION-UNANSWERED** — a *core* archetype question with no official answering
     passage. Site-derived gap: finding (the site claims the territory and does not cover it).
     Market-derived gap: `opportunities[]` entry (unmet demand — the site never claimed it),
     never a finding.
   - **Sampling gap** — `not_evaluated` with the reason (`sampling limitation: ...`), never
     a finding and never an opportunity, in exactly two cases: (1) the expected page was
     never sampled; (2) a market-derived question no sampled page answers while the
     excerpt's `coverage_appendix` (headings, nav labels) still shows a page that would
     carry the answer. Decide between the two cases in one sentence; do not re-litigate.
   - **Sampled-page silence is evidence, not a sampling gap.** The question's source does
     not decide this — the page's claim does. If a sampled page's section-level headings in
     main content (h2/h3 naming the question's subject — a `PROGRAM FEES` heading counts;
     nav, carousel, or announcement headings do not) claim the territory and carry no
     answering passage → finding (ANS-QUESTION-UNANSWERED). A market-derived question no
     sampled page claims anywhere → `opportunities[]`. If the missing section is plausibly
     collapsed-by-default DOM content, that is REF-COLLAPSED-ANSWER / representation's case
     — name the paired check, do not double-report. If the answer plausibly lives on an
     unsampled page, say so in the evidence sentence — it scopes the finding, it does not
     erase it. Corroboration damping may lower the finding one step when external
     corroboration is strong — state the cited-despite sentence in `why_it_matters`.
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
     offset **above 1,500 characters** — gate from `extras.boilerplate`'s measured numbers,
     never re-measure offsets by hand. Below that (e.g. a 130–300 character docs-index nav
     with content starting at ~300) it is orientation — pass, with the measured numbers
     recorded as the non-evidence. A broken sentence inside the preamble is a separate
     ANS-PASSAGE-INCOMPLETE fact, not this check.

## Findings (authoring rules)

- Titles follow each check's `pattern_template`; evidence follows `evidence_template` — counts
  with denominators and quotes ≤ 200 chars with page URL and `char_offset`. Titles state
  site-level patterns, never one question's story. When a finding shares its root cause with
  another stage's check (comparison grids with REP-TABLE-SEMANTICS, qualifier scope with
  FRS-*-CONFLICT), name the paired check_id in the evidence — one effect per stage, cited
  pairs, never silent overlap.
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
  JSON and matches `finding_fragment.json`. Two scripts, one call each, no alternatives:
  `python3 <orchestrator>/scripts/build_passages.py --draft <draft> --excerpt audit/excerpts/answer-coverage-audit.json --snapshot audit/snapshot.json --out audit/passages.json`
  for the question set (fix only its FAIL lines, then re-run that one command), and
  `python3 <orchestrator>/scripts/write_fragment.py --in <fragment draft> --out audit/findings/answer-coverage-audit.json`
  for the fragment. `write_fragment.py` validates and applies safe fixes; do not run
  `validate_fragment.py` yourself, do not write a builder script, and do not hand-copy
  passages. The fragment you author carries only the judgment fields.
  State in your summary which questions were
  market-derived so the offsite probe set inherits the right phrasing.
