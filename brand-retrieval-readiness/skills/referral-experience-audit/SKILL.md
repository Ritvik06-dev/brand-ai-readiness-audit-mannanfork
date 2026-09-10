---
name: referral-experience-audit
description: Judge whether a visitor arriving from an AI citation can confirm the cited fact and continue their task - answer confirmable above the fold with its qualifier, text-fragment landing survivability, answers collapsed by default, overlays and consent walls, soft 404s, dead-end 404 bodies, path-dropping redirects, and static performance risk. Normally invoked by audit-orchestrator; use alone only when asked specifically about landing-page or engagement concerns.
license: MIT
compatibility: Requires Python 3.9+ (standard library only). A headless browser is optional and only raises confidence.
allowed-tools: Bash Read Write
metadata:
  version: "1.0.0"
---

# Referral Experience Audit (land)

This skill guards the **land** stage, and it carries the engagement half of the problem
statement. The governing reframe: a visitor arriving from an assistant is not a search
visitor — they arrive **with a pre-formed question and an expected fact already in hand**. The
referral fails when the page cannot confirm that fact fast. Every check below is that failure,
measured: two check families, kept distinct — **continuation failure** (AI-specific: the page
cannot confirm the cited claim) and **generic friction** (classic landing defects that bite any
visitor, judged here because they land on the citation).

## When to use

- Someone asks why visitors referred from AI answers bounce, or whether their pages confirm
  what assistants claim about them.
- A site owner wants to know what a citation landing actually looks like: the answer above the
  fold, the quote that highlights, the path that survives.
- Out of scope: which questions the site should answer (answer-coverage-audit); whether facts
  survive the raw fetch (representation-parity-audit — the click-injected sibling of the
  accordion case lives there).

## Inputs

- Prepared excerpt file `audit/excerpts/referral-experience-audit.json` (one read): pages with
  `heading_tree` (ids matter), first excerpts, `extras.pages_signals` (per page: overlays,
  accordions, dialogs, `details_elements` with `details_open` and `details_collapsed`,
  `images_without_dimensions` of `images_total`, `render_blocking_head_scripts`),
  `extras.soft_404` (probe result + body quality), and
  `extras.redirect_path_preservation`. Every count a check's `evidence_template` asks for is
  measured there: quote it, never recount it, never open the snapshot to derive it. `extras.checks` carries the check templates;
  `extras.fragment_shape` the fragment keys; `extras.phase1_findings` lists the phase-1
  findings (pairing with REP-* without re-reading fragments).
- `audit/passages_checked.json` — written by the `--passages` post-step. **Its array key is
  `results`, not `questions`** (that is the key in `passages.json`, its input). Each row: the
  `question_id`, whether the passage exists as one contiguous visible text run (`contiguous`),
  `first_window`, and why not (`note`). A `note` saying the anchor was never pinned is a
  quoting/fragmentation signal, never evidence the question is unanswered.
- Runtime contract: judge from the excerpt and `passages_checked` only, in a single pass, and
  write the fragment once; emit partial findings with `not_evaluated` rather than overrun. If
  a read truncates, continue from the truncation offset — do not restart or re-open.
  **Timebox:** the fragment must be authored by 300 s elapsed (printed by the scripts); past
  that, record the deterministic relays and judge continuation failures for at most the first
  3 questions — the rest `not_evaluated` (`timebox: ...`). A partial fragment beats an overrun.
  `extras.fragment_shape` is the complete fragment contract — never open `finding_fragment.json`.

## Procedure

1. **Deterministic relays** — `extras.relays` carries each as a finding-candidate plus an
   evidence line, precomputed by the collector; gate them (the pass/finding decision stays
   with you — e.g. a 404 body with navigation but no search is your call):
   - **REF-SOFT-404** — a nonexistent path returned 200. A Google-recognized defect that
     admits junk URLs to indexes and turns mangled citations into silent dead ends.
   - **REF-404-DEAD-END** — the 404 body's recovery path: no search, no navigation, no
     suggestions.
   - **REF-PATH-DROP-REDIRECT** — a variant redirect that dropped the path to `/`, losing
     the answer for every citation of that variant.
2. **Text-fragment survivability** — **REF-FRAGMENT-UNSURVIVABLE** from `passages_checked.json`:
   `contiguous: false` rows, with their notes. Judge passages **as answer-coverage wrote them**
   under its quote-granularity rule (≤ ~600 characters, the specific answer sentence(s)); a
   passage that fails only because it was an oversized dump is `not_evaluated` with that
   reason — the check measures the site, not quoting style. Google AI Overviews and AI Mode
   land visitors with `#:~:text=` scroll-to-text fragments (roughly half of AI Mode
   click-throughs by third-party analysis), so a passage split across spans or assembled by
   script fails the highlight silently. Heading-`id` coverage stays **low** severity: Google
   surfaces land with text fragments, not heading anchors — stable anchors help other surfaces
   and the human's table of contents, and nothing more.
3. **Continuation judgments** — semantic, medium cap, quoted from the excerpts:
   - **REF-ANSWER-NOT-CONFIRMED** — for each answer-coverage question with an expected page:
     is the answer confirmable in the first screenful with its qualifier attached?
     `passages_checked.json` carries `first_window` per question (offset vs the ~600-char
     proxy) — the offset question is answered; the confirmation question is still yours:
     on news/publisher pages a confirming headline overrides `in_window: false` (name the
     confirming surface in the evidence); `in_window: true` never clears a collapsed answer
     (consult `pages_signals`); qualifier attachment is never precomputed. A declared
     browser capability upgrades to direct observation.
   - **REF-COLLAPSED-ANSWER** — the accordion inversion: content in the DOM but collapsed by
     default is fine for the machine and hostile to the human who arrived for exactly that
     fact. The number is `pages_signals.details_collapsed` (elements minus `details_open`) —
     `details_elements` alone says nothing, since an open `<details>` hides nothing. Read it,
     never count by hand. Your judgment is only whether a *decision* fact is inside one; the
     accordions and dialogs counts scope it. The click-injected counterpart is
     representation's case — name the pairing, do not double-report.
4. **Generic friction** — **REF-OVERLAY-BLOCK** (overlay present in the initial HTML —
   observed, never guessed) and **REF-PERF-RISK**, whose two numbers are measured for you in
   `pages_signals`: `images_without_dimensions` (of `images_total`) and
   `render_blocking_head_scripts` (`<script src>` in `<head>` with no async/defer). Quote
   those; never open the snapshot and never write a script to recount them. A risk
   observation or `needs_verification` hypothesis only; NEVER a measured Core Web Vital —
   say that real measurement requires CrUX field data or a lab run, which this audit does
   not perform.
5. **Write** the fragment to the orchestrator's `audit/findings/` path.

## Findings (authoring rules)

- Titles follow each check's `pattern_template`; evidence follows `evidence_template` — counts
  with denominators and quotes ≤ 200 chars. Titles state site- or template-level patterns; the
  specific landing is evidence, not the title. State probe observations in words (path and
  status), never as field paths (`snapshot.*`, `*.is_soft_404`). When a finding shares its
  root cause with another stage's check (fragment survival with REP-*, confirmation with
  ANS-*), name the paired check_id in the evidence — one effect per stage, cited pairs.
- When NOT to flag (negative controls), in plain words, per check:
  - REF-SOFT-404: nonexistent paths return 404/410 (then REF-404-DEAD-END judges the body).
  - REF-404-DEAD-END: the 404 page offers search, navigation, or suggestions.
  - REF-PATH-DROP-REDIRECT: variant redirects preserve the full path.
  - REF-FRAGMENT-UNSURVIVABLE: the passage exists as one contiguous run; expand-on-demand is
    fine for supplementary content (the flag case is the *landing answer* itself).
  - REF-ANSWER-NOT-CONFIRMED: the answer appears above the fold with its qualifier.
  - REF-COLLAPSED-ANSWER: the answer content is visible on arrival.
  - REF-OVERLAY-BLOCK: a dismissible banner that does not obstruct main content; legally
    required overlays on their specific content class.
  - REF-PERF-RISK: no fabricated CLS/LCP/INP numbers, ever.
- Severity and confidence are separate; follow
  `../audit-orchestrator/references/severity_model.md`. Deterministic relays carry
  `direct-measurement`; the continuation judgments carry `semantic-judgment`, capped at medium
  unless a deterministic observation corroborates them. A failed or missing observation is
  `not_evaluated` with a reason, never a finding.

## Output

- The finding fragment to the orchestrator's `audit/findings/` path, shaped by
  `../audit-orchestrator/references/finding_fragment.json`. Never assign `F-` ids; the
  orchestrator does. One write path, no alternatives, and you never hand-write
  nested fragment JSON. Write a **verdicts file** in exactly this shape — the top-level key
  is `verdicts`, and `skill_id` is required:

  ```json
  {"skill_id": "<this skill's id>",
   "verdicts": [
     {"check": "XXX-PASSING-CHECK", "gate": "pass"},
     {"check": "XXX-SKIPPED-CHECK", "gate": "not_evaluated", "reason": "why not judged"},
     {"check": "XXX-FAILING-CHECK", "gate": "finding",
      "severity": "medium", "confidence": "medium",
      "title": "<pattern-shaped title>", "evidence": "<counts with denominators + quote>",
      "why": "<why it matters>", "fix": "<what to change>", "verify": "<acceptance test>",
      "owner": "<who>", "effort": "small",
      "urls": ["https://example.com/page"],
      "observations": {"any_extra_measured_field": 1}}]}
  ```

  Every field except `check` and `gate` is optional. `reason` is for `not_evaluated`;
  `observations` merges on top of the collector's measured values and is where recorded
  probe rows go. Then run

  `python3 <orchestrator>/scripts/write_fragment.py --verdicts --in <verdicts> --excerpt <this skill's excerpt> --out <final path>`

  It assembles the nested result objects, merges in the observations the collector already
  measured (`extras.measured`), fills `evidence_quality` and `affected_surfaces` from the
  check catalog, validates, and prints one line. Never retype a measured number or a
  relay's evidence sentence: cite it by gating the check and let the script carry it.
  Any catalog check you submit no verdict for is recorded `not_evaluated` — silence is
  never a pass, so submit a verdict for every check you actually judged. Do not run
  `validate_fragment.py` yourself and do not write a per-run builder script; the merge
  salvages anything still invalid. In your summary, name which family each finding belongs to so the report
  can order continuation failures before generic friction.
