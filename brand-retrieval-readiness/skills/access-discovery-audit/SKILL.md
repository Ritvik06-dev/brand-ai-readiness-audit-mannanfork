---
name: access-discovery-audit
description: Analyze whether AI crawlers and fetchers can discover, reach, and index a site's important pages — crawler-role robots policy, noindex/nosnippet/noarchive index controls, canonicals, redirects, bot challenges, sitemaps. Normally invoked by audit-orchestrator; use alone only when asked specifically about crawl-access, index-control, or discovery concerns.
license: MIT
compatibility: Requires Python 3.9+ (standard library only).
allowed-tools: Bash Read
metadata:
  version: "1.0.0"
---

# Access & Discovery Audit (reach)

This skill guards the **reach** stage of the assistant pipeline: can the right public URL be
found, fetched, and indexed by each retrieval role. Blocking is per crawler role — OpenAI
documents that sites disallowing OAI-SearchBot "will not be shown in ChatGPT search answers,
though can still appear as navigational links" (developers.openai.com/api/docs/bots), while
blocking a training crawler (GPTBot, ClaudeBot) is a policy choice, not a visibility outage.
On the snippet side, Google's AI-features documentation names `nosnippet`, `data-nosnippet`,
`max-snippet`, and `noindex` as "the" controls that limit what AI Overviews and AI Mode can
show (developers.google.com/search/docs/appearance/ai-features), and Bing documents that
`noarchive` excludes a page from Bing Chat answers while it still ranks in ordinary results
(blogs.bing.com/webmaster/september-2023).

## When to use

- Someone asks why their pages are not being picked up, indexed, or cited by AI assistants,
  and the cause could be access: robots rules, index directives, WAF challenges, canonical
  or redirect conflicts.
- A site owner wants to know whether their crawler policy matches their visibility intent.
- Out of scope: whether page content is readable once fetched (representation-parity-audit),
  whether the brand is cited off-site (offsite-visibility-audit), landing-page behavior
  (referral-experience-audit).

## Inputs

- Primary: `--snapshot <path>` — the shared snapshot from `collect_snapshot.py`. Consume only:
  `robots` (status, groups with per-token roles), `probes.ua_probes`, `probes.llms_txt`,
  `probes.redirect_path_preservation`, `pages[]` (robots_meta, x_robots_tag, canonical,
  final_url, redirect_chain, hreflang, lang, links, page_class, status), `sitemap`,
  `discovery`, `site_type`.
- Standalone: if no snapshot exists, run
  `../audit-orchestrator/scripts/collect_snapshot.py --url <URL>` first (or ask the user to).
  This skill performs no network I/O of its own; every fetch, probe, and robots parse already
  happened in the snapshot.

## Procedure

Run `scripts/probe_access.py --snapshot <path> --out <fragment path>`. The script implements
all eleven checks deterministically:

1. **ACC-ROBOTS-ROLE** — for each `search-index` role token in `robots.groups`, match
   `disallowed_paths` against sampled important page paths (longest-match wins; allow rules
   override). Finding when an important path is blocked while the direct fetch returned 200.
   Whole-site block (homepage `/`) is critical. A `Disallow` against training-role tokens is
   recorded as a policy observation, never a citation-loss finding.
2. **ACC-ROBOTS-UNAVAILABLE** — `robots.txt` 404 is "no crawl restrictions" and never a
   defect. A 5xx is a real crawl-delay condition: two or more consecutive 5xx across the audit
   escalate to high/high; the snapshot currently records one attempt, so a single 5xx emits a
   low-confidence candidate that the orchestrator routes to `needs_verification`.
3. **ACC-INDEX-CONTROL** — parse `robots_meta` and `x_robots_tag` per important page
   (homepage/decision/product/docs/about/trust). `noindex` is high (critical if site-wide);
   `nosnippet` / `max-snippet:0` on decision pages is high and scoped to Google AI surfaces.
   `data-nosnippet` coverage is recorded as an observation only — whether it covers a decision
   fact is a judgment for the reader of the report, not a script gate.
4. **ACC-NOARCHIVE-COPILOT** — `noarchive`/`nocache` on important pages, surface-scoped to
   Copilot (noarchive high, nocache medium).
5. **ACC-CANONICAL-CONFLICT** — declared canonical vs final fetch URL, compared after
   scheme/host/trailing-slash normalization.
6. **ACC-REDIRECT-LOOP** — repeated URLs inside a sampled page's `redirect_chain` (loop, high)
   or chains of 4+ hops (medium).
7. **ACC-BOT-CHALLENGE** — `probes.ua_probes` differentials (bot-UA 401/403/429/503 while a
   direct fetch returned 200), strengthened by `cf_mitigated` headers and a forced
   `text/html` content type. Same-IP spoofed-UA evidence: confidence capped at medium;
   owner-side verification runs through provider IP lists
   (claude.com/crawling/bots.json, perplexity.com/perplexitybot.json) — never fetched here.
8. **ACC-SITEMAP-ORPHAN** — sampled sitemap URLs not reachable from any sampled page's links,
   flagged only on large/poorly-linked sites (candidates >= 50). Sample-limited evidence is
   stated in the finding.
9. **ACC-SITEMAP-INVALID** — a declared sitemap that 5xx's or fails to parse. Sitemap absence
   alone is never a defect.
10. **ACC-HREFLANG-INCONSISTENT** — only when sampled pages declare hreflang: invalid lang
    codes and missing reciprocal declarations between sampled pages. Single-locale sites are
    `not_evaluated`.
11. **ACC-LLMS-TXT-ABSENT** — only when `site_type` includes `docs-developer`: `/llms.txt`
    probe from the snapshot; low severity, framed as agent-navigation opportunity, never
    discoverability.

## Findings (authoring rules)

- Titles follow each check's `pattern_template`; evidence follows `evidence_template` — counts
  with denominators, the matching rule or directive, and the comparison status. Titles state
  site- or template-level patterns; `affected_urls` carries the instances.
- When NOT to flag (negative controls), in plain words, per check:
  — ACC-ROBOTS-UNAVAILABLE: a 404 robots.txt means "no crawl restrictions" — never a defect.
  — ACC-ROBOTS-ROLE: blocking a training crawler (GPTBot, ClaudeBot) is policy, not an outage.
  — ACC-INDEX-CONTROL: `noindex` on staging, duplicate, or internal URLs the site intends to
    hide.
  — ACC-NOARCHIVE-COPILOT: `noarchive` on legal or archive pages carrying no decision facts —
    low or an opportunity, not a defect.
  — ACC-CANONICAL-CONFLICT: a canonical that merely normalizes scheme/host, or a deliberate
    single hop to the preferred host.
  — ACC-REDIRECT-LOOP: a single 301/308 hop to the canonical URL.
  — ACC-BOT-CHALLENGE: challenges issued only to abusive paths, or absent for robots-allowed
    tokens.
  — ACC-SITEMAP-ORPHAN / ACC-SITEMAP-INVALID: a small, comprehensively linked site without a
    sitemap — absence alone is never a defect.
  — ACC-HREFLANG-INCONSISTENT: single-locale sites — not applicable, lands in
    `not_evaluated`.
  — ACC-LLMS-TXT-ABSENT: any non-docs site — and on no site is `llms.txt` a discoverability
    factor.
- Severity and confidence are separate; follow
  `../audit-orchestrator/references/severity_model.md`. Spoofed-UA differentials cap at medium
  confidence. Semantic judgments are capped at medium confidence unless a deterministic
  observation corroborates them — every ACC gate is deterministic, so candidates here carry
  direct-measurement evidence or nothing. A failed or missing observation is `not_evaluated`
  with a reason, never a finding.

## Output

- `--out <path>` writes the finding fragment shaped by
  `../audit-orchestrator/references/finding_fragment.json`; the script self-validates it when
  the orchestrator's schema is resolvable from the marketplace root.
- Stdout: a small summary (finding/pass/not_evaluated counts plus one line per finding).
- Exit 0 = fragment written and valid; 1 = fragment validation failed; 2 = could not analyze
  (a fragment whose `not_evaluated` array carries the reason is still written).
