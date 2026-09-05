---
name: representation-parity-audit
description: Analyze whether a page's important facts survive into the raw server response's visible text — detecting content that exists only after hydration, only inside inline state payloads, only in metadata, or only inside media, which non-rendering AI crawlers cannot retrieve. Normally invoked by audit-orchestrator; use alone only when asked specifically about rendering, hydration, or representation-loss concerns.
license: MIT
compatibility: Requires Python 3.9+ (standard library only).
allowed-tools: Bash Read
metadata:
  version: "1.0.0"
---

# Representation Parity Audit (read)

A fact plainly visible in a browser is not always retrievable by a machine. Googlebot renders
JavaScript with the Web Rendering Service, so Google AI surfaces and Microsoft Copilot inherit
rendering; the retrieval crawlers behind ChatGPT, Claude, and Perplexity fetch the raw response
and do not execute it — Vercel's crawler study measured GPTBot fetching JS assets in ~11.5% of
hits and ClaudeBot in ~23.8%, and executing none
(https://vercel.com/blog/the-rise-of-the-ai-crawler). Content that exists only after hydration
is therefore retrievable by some retrieval surfaces and not others: a partial outage, not total
invisibility. Content present only inside inline state payloads (`__NEXT_DATA__`, RSC flights,
Redux/Apollo caches) is partially readable, because crawlers may index JSON included in the
initial HTML response. This skill measures where facts survive across representations: raw
visible text, inline payloads, metadata, and media alternatives.

## When to use

- Diagnosing why content that renders fine in a browser is missing or truncated in AI answers.
- Checking whether a client-rendered site hides its substance from non-rendering fetchers.
- Out of scope: deciding *which* questions customers ask (answer-coverage), judging dates
  (freshness), or identity conflicts (entity-consistency) — this skill reports representation
  loss only.

## Inputs

- Primary: `--snapshot <path>` — the shared snapshot from `collect_snapshot.py`. Consume only:
  `pages[]` fields `raw_html`, `visible_text`, `inline_state`, `images`, `tables`,
  `non_text`, `links`, `interactive`, `headings`, `open_graph`, `meta_description`, `title`,
  `page_class`, `claim_index`.
- Standalone: if no snapshot exists, run
  `../audit-orchestrator/scripts/collect_snapshot.py --url <URL>` first (or ask the user to).
  This skill performs no network I/O of its own.

## Procedure

Run `scripts/analyze_representation.py --snapshot <path> --out <fragment path>`. The script
implements all eight checks deterministically:

1. **Shell detection (REP-KEY-FACT-LOSS).** Count independent shell indicators per page:
   "enable JavaScript" noscript text; tiny visible text against a large raw response; loading
   or empty title; near-empty root container. Emit a finding only when at least two indicators
   coexist AND the inline payload holds no content-like strings (if it does, the page is
   REP-STATE-ONLY-FACT's case — partially readable, not lost). Otherwise the check is
   `not_evaluated`: "no browser: render gap unconfirmed". With a declared browser capability,
   one post-load DOM capture per flagged page upgrades this check to
   `direct-representation-comparison`/high confidence, separates collapsed-by-default content
   from click-injected content, and catches post-load overlays — capability-gated, never
   installing anything.
2. **Inline-state contrast (REP-STATE-ONLY-FACT).** For each page, count payload-only strings
   that read like content (not props, ids, routes). A finding requires content-like payload
   strings on a page whose visible text is under 250 words. An SSR page whose payload strings
   also appear in visible text passes — machinery strings on a full-content page are not facts.
3. **Metadata contrast (REP-METADATA-CONTRAST).** Extract fact tokens (prices, percentages,
   versions, plan names) from `og:description`/meta description; a page counts only when a
   token never appears in its visible text. A finding requires at least two such pages.
4. **Extraction displacement (REP-EXTRACTION-LOSS).** Detect an identical preamble (≥80 chars)
   shared by half the sampled pages AND a median page-unique-content offset above 1,500
   characters. Preamble presence alone is not displacement.
5. **Non-text lock-in (REP-NON-TEXT-LOCKIN).** Flag pages that are media-dominant: ≥5
   empty-alt images against <300 visible words, or ≥3 text-free canvas/SVG/video elements.
6. **Grid semantics (REP-TABLE-SEMANTICS).** Flag decision/product pages (or pages with ≥2
   price claims) carrying ≥2 aligned div-grids and zero semantic `<table>`.
7. **Script-only navigation (REP-LINKS-SCRIPT-ONLY).** Extract internal paths referenced by
   script handlers; a page counts when ≥5 such paths have no crawlable `<a href>` equivalent;
   a finding requires two such pages.
8. **Hidden text (REP-HIDDEN-TEXT-SUSPECT).** Count inline `display:none`,
   `visibility:hidden`, `font-size:0`, and off-screen positioning, after allowlisting
   `sr-only`/`visually-hidden`/skip-link classes, `aria-hidden="true"` decorative elements,
   and `type="hidden"` inputs. A finding requires ≥2 instances on ≥2 pages.

## Findings (authoring rules)

- Titles follow the check's `pattern_template`; evidence follows `evidence_template` — counts
  with denominators and short quotes (≤200 chars); `affected_urls` carries the instances.
  Titles state site- or template-level patterns, never one visitor's incident.
- When NOT to flag (negative controls), in plain words:
  — REP-KEY-FACT-LOSS: an SSR page whose root container holds the same facts as visible text
    passes; a framework marker alone is a clue, never a finding.
  — REP-STATE-ONLY-FACT: payload strings that also appear in visible text pass; machinery
    strings (props, routes, ids) on a full-content page are not facts.
  — REP-METADATA-CONTRAST: a description that summarizes or mirrors visible text is normal.
  — REP-EXTRACTION-LOSS: boilerplate that precedes content within a few hundred characters is
    orientation, not displacement.
  — REP-NON-TEXT-LOCKIN: a text alternative carrying the same fact is a pass; decorative
    media is not lock-in.
  — REP-TABLE-SEMANTICS: grids without comparison content, or any semantic `<table>`, pass.
  — REP-LINKS-SCRIPT-ONLY: destinations that also exist as crawlable links pass.
  — REP-HIDDEN-TEXT-SUSPECT: accessibility patterns are allowlisted and never flagged.
- Severity and confidence are separate; follow
  `../audit-orchestrator/references/severity_model.md`. Hydration-only facts are high (a
  partial outage — `affected_surfaces` names the non-rendering surfaces); payload-only facts
  are medium ("partially readable"; acceptance test: the fact appears in visible raw text, not
  only in an inline script). Every semantic judgment stays at medium unless a deterministic
  observation corroborates it. A failed tool call is never a site defect — `not_evaluated`
  with a reason.

## Output

`--out <path>` writes the finding fragment shaped by
`../audit-orchestrator/references/finding_fragment.json`; the script self-validates it against
that schema when the marketplace root is resolvable. Stdout is a small summary. Exit 0 =
fragment written and valid; 1 = validation failure; 2 = could not analyze (a fragment with
`not_evaluated` entries is still written). Never assign `F-` ids; the orchestrator does.
