---
name: referral-experience-audit
description: Judge whether a visitor arriving from an AI citation can confirm the cited fact and continue their task - answer confirmable above the fold with its qualifier, text-fragment landing survivability, answers collapsed by default, overlays and consent walls, soft 404s, dead-end 404 bodies, path-dropping redirects, and static performance risk. Normally invoked by audit-orchestrator; use alone only when asked specifically about landing-page or engagement concerns.
license: MIT
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
  `heading_tree` (ids matter), first excerpts, `extras.pages_signals` (overlays, accordions,
  details, dialogs per page), `extras.soft_404` (probe result + body quality), and
  `extras.redirect_path_preservation`. `extras.checks` carries the check templates;
  `extras.fragment_shape` the fragment keys.
- `audit/passages_checked.json` — written by the `--passages` post-step: per candidate answer
  passage, whether it exists as one contiguous visible text run (`contiguous`) and why not
  (`note`: "price split across spans", "inside collapsed details").
- Snapshot context relayed when needed: image dimensions and inline render-blocking hints.
- Runtime contract: judge from the excerpt and `passages_checked` only, in a single pass, and
  write the fragment once; emit partial findings with `not_evaluated` rather than overrun.
  `extras.fragment_shape` is the complete fragment contract — never open `finding_fragment.json`.

## Procedure

1. **Deterministic relays** — the probes already ran in the snapshot; quote the recorded
   observation, never re-derive it:
   - **REF-SOFT-404** — `extras.soft_404`: a nonexistent path returned 200. A Google-recognized
     defect that admits junk URLs to indexes and turns mangled citations into silent dead ends.
   - **REF-404-DEAD-END** — the 404 body's `body_quality`: no search, no navigation, no
     suggestions.
   - **REF-PATH-DROP-REDIRECT** — `extras.redirect_path_preservation`: a variant redirect that
     dropped the path to `/`, losing the answer for every citation of that variant.
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
     is the answer confirmable in the first screenful with its qualifier attached? **Explicit
     proxy (adopted; no improvising per run):** the first screenful is approximated by the
     first ~600 characters of the page's main-content extraction — an answer appearing within
     that window confirms; an answer beyond it, or present only after interaction, is the
     flag case. State the proxy in the evidence and keep confidence at medium; a declared
     browser capability upgrades to direct observation. The slogan H1 with the fact 900 words
     down is the flag case, not the pass case. On news- and publisher-style pages a headline
     (h1/h2) stating the answer with its qualifier counts as confirmation — headlines are
     the confirmable surface there; name the confirming surface in the evidence.
   - **REF-COLLAPSED-ANSWER** — the accordion inversion: content in the DOM but collapsed by
     default is fine for the machine and hostile to the human who arrived for exactly that
     fact (use `pages_signals` accordions/details/dialogs plus the excerpts). The
     click-injected counterpart is representation's case — name the pairing, do not
     double-report.
4. **Generic friction** — **REF-OVERLAY-BLOCK** (overlay present in the initial HTML —
   observed, never guessed) and **REF-PERF-RISK** (static indicators: images without dimension
   attributes, render-blocking hints — a risk observation or `needs_verification` hypothesis
   only; NEVER a measured Core Web Vital; say that real measurement requires CrUX field data
   or a lab run, which this audit does not perform).
5. **Write** the fragment to the orchestrator's `audit/findings/` path.

## Findings (authoring rules)

- Titles follow each check's `pattern_template`; evidence follows `evidence_template` — counts
  with denominators and quotes ≤ 200 chars. Titles state site- or template-level patterns; the
  specific landing is evidence, not the title.
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
  orchestrator does. Done means valid: the fragment parses as JSON and matches
  `finding_fragment.json` before handoff (`python3 <orchestrator>/scripts/validate_fragment.py <fragment>` (checks the schema, not just syntax)) — an
  unvalidated fragment is not a handoff. Building it programmatically (e.g. `json.dump`). If writing JSON through a shell heredoc instead, quote the delimiter (`<<'EOF'`). In your summary, name which family each finding belongs to so the report
  can order continuation failures before generic friction.
