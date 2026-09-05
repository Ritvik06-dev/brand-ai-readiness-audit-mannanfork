---
name: entity-consistency-audit
description: Analyze entity identity and structured-data consistency — JSON-LD validity, brand-name consistency across title/OG/canonical/H1/schema/footer, structured claims contradicting visible ones, sameAs corroboration resolved owned-vs-independent, and entity-name ambiguity observations for a model judgment. Normally invoked by audit-orchestrator; use alone only when asked specifically about entity, identity, or structured-data concerns.
license: MIT
compatibility: Requires Python 3.9+ (standard library only).
allowed-tools: Bash Read
metadata:
  version: "1.0.0"
---

# Entity Consistency Audit (identify)

This skill guards the **identify** stage: can a retrieval system tell *which* entity this site
is, and does every machine-readable statement about it agree with what a visitor can see?
Google's structured-data guidelines state not to "mark up content that is not visible to
readers of the page" — "if the JSON-LD markup describes a performer, the HTML body must
describe that same performer" — and that structured data "must be a true representation of the
page content" (developers.google.com/search/docs/appearance/structured-data/sd-policies).
That is why this skill flags structured data that **contradicts** visible content or **fails
to parse**, and never flags merely missing or optional markup. The mistaken-identity risk it
also measures is the on-site half of cross-web agreement: when a brand name also denotes other
prominent things and the site carries no distinguishing qualifier, assistants resolve the name
to the wrong entity. Never require Wikipedia, Wikidata, or `@graph` — absence of optional
markup is not a defect.

## When to use

- Someone asks why assistants describe their company wrong, merge it with another brand, or
  cannot attribute its claims.
- A site owner wants to know whether its structured data, identity surfaces, and declared
  external presence agree with each other.
- Out of scope: whether content survives extraction (representation-parity-audit), whether
  dates are trustworthy (freshness-consistency-audit), whether the brand is cited off-site
  (offsite-visibility-audit) — the observed *effect* of ambiguity off-site belongs there.

## Inputs

- Primary: `--snapshot <path>` — the shared snapshot from `collect_snapshot.py`. Consume only:
  `pages[]` (jsonld blocks with parse outcomes, title, open_graph, meta_description, headings,
  canonical, links, claim_index, page_class, visible_text, raw_html for footer legal-name
  lines), and `external_presence[]` (http_status, owned_vs_independent, brand_name_match).
- Standalone: if no snapshot exists, run
  `../audit-orchestrator/scripts/collect_snapshot.py --url <URL>` first (or ask the user to).
  This skill performs no network I/O of its own.

## Procedure

Run `scripts/check_entities.py --snapshot <path> --out <fragment path>`. The script implements
five checks and degrades per check: a missing input yields that check's `not_evaluated`
entry with a reason, and an unreadable snapshot or analysis failure still writes a valid
`not_evaluated` fragment (exit 2) — the other checks' verdicts are never lost to one gap.

1. **ENT-JSONLD-INVALID** — per JSON-LD block: parse failures and missing type-required
   properties (`name`, `@type`). Severity medium; escalates to high only when the failed block
   is the site's main Organization/Product identity. Valid markup without `@graph`, and absent
   optional types, are never findings.
2. **ENT-STRUCTURED-VISIBLE-CONFLICT** — JSON-LD `offers.price`/availability/`name` compared
   against the same page's visible `claim_index` values, title, and Open Graph. Quote both
   sides. Severity high: a wrong quotable fact is worse than missing markup.
3. **ENT-NAME-INCONSISTENT** — the organization name as stated across title, `og:site_name`,
   H1, JSON-LD `name`, and footer legal-name lines; report distinct variants with counts.
   Intentional brand/product hierarchies with a consistent legal entity name are the negative
   control.
4. **ENT-AMBIGUOUS-NAME** — *model judgment*. The script emits `gate: "pass"` with prepared
   observations: candidate name and its source, name variants, and qualifier presence in
   title/H1/schema/about. The fragment is the prepared input — the orchestrator reopens it
   once (it is small) to complete the gate per the authoring rules below; a shared name alone
   is never a finding.
5. **ENT-CORROBORATION-ABSENT** — from `external_presence`: resolved links, independent vs
   owned classification, brand-name matches. Owned social profiles (LinkedIn/X/Facebook)
   never count as corroboration; surfaces with `http_status: null` (unresolved/timeout) are
   counted separately as unresolved and never become findings.

## Findings (authoring rules)

- Titles follow each check's `pattern_template`; evidence follows `evidence_template` — counts
  with denominators and both sides of any conflict, quoted. Titles state site-level patterns;
  `affected_urls` carries the instances.
- When NOT to flag (negative controls), in plain words, per check:
  — ENT-JSONLD-INVALID: valid JSON-LD without `@graph`; missing optional types; a block that
    parses and carries its required identity properties.
  — ENT-STRUCTURED-VISIBLE-CONFLICT: markup scoped to a different offer or page region — only
    same-page contradictions about the same fact count.
  — ENT-NAME-INCONSISTENT: intentional brand/product hierarchies with a consistent legal
    entity name.
  — ENT-AMBIGUOUS-NAME: distinguishing qualifiers present in title, H1, schema, or about — a
    shared name alone is never a finding.
  — ENT-CORROBORATION-ABSENT: independent surfaces that resolve with a matching brand name;
    owned social profiles never count as corroboration; unresolved fetches
    (`http_status: null`) never become findings.
- Severity and confidence are separate; follow
  `../audit-orchestrator/references/severity_model.md`. Semantic judgments are capped at
  medium confidence unless a deterministic observation corroborates them.

**Completing ENT-AMBIGUOUS-NAME (the model's step).** Promote the prepared result to a
finding only when the name collides with other prominent entities (person, place, category
term, another brand) AND the prepared `qualifier_presence` shows no distinguishing context.
The evidence must be the required sentence shape: *"The name X also denotes {…}; the site's
homepage, `<title>`, and Organization schema carry no category, location, or legal-name
qualifier that distinguishes it."* With qualifiers present, or when the observed off-site
behavior (offsite-visibility-audit) already attributes the collision, leave it as a pass and
say so — double-reporting one root cause is the failure mode this rule exists to prevent.

## Output

- `--out <path>` writes the finding fragment shaped by
  `../audit-orchestrator/references/finding_fragment.json`; the script self-validates it when
  the orchestrator's schema is resolvable from the marketplace root.
- Stdout: a small summary (finding/pass/not_evaluated counts plus one line per finding).
- Exit 0 = fragment written and valid; 1 = fragment validation failed; 2 = could not analyze
  (a `not_evaluated` fragment is still written).
- Never assign `F-` ids; the orchestrator does.
