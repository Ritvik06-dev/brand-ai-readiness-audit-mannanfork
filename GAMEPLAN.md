# GAMEPLAN — Brand Retrieval Readiness Marketplace
### Adobe University Hackathon 2026 · Round 3 · single operative plan

**Precedence:** `hackathon.txt` outranks everything. This file outranks everything else.
`docs/` holds the superseded reviews and plans, kept for provenance and verbatim vendor quotes.

**Capacity:** 4 people, ~1.5 weeks. Agents write code and skills; humans verify claims, run
tests, and own gate verdicts. **The binding constraint is human verification bandwidth, not
code volume.** Seven skills with verified negative controls beat eleven without.

---

## 1. What we are building, and how it is positioned

A drop-in diagnostic. Someone points an agent at a URL, or just asks why their brand is not
showing up in AI answers, and gets one evidence-backed report telling them where they stand
and what to fix first. Zero setup, read-only, no instrumentation, no account.

Judges are from Adobe's brand visibility team. Their own product (LLM Optimizer, rebranded
Adobe Brand Visibility in Aug 2026, now folded together with Semrush market intelligence) is
instrumented enterprise monitoring: it needs CDN log forwarding and an analytics integration,
and it asks the brand to configure the topics and prompts to watch.

**Complement it, never clone it.** Our edges, and the README's opening pitch:

| They | Us |
|---|---|
| CDN logs + analytics integration | works on a cold URL with nothing installed |
| brand configures topics and prompts | we infer the prompt set from the site |
| dashboard that monitors a trend | diagnosis that names the mechanism and hands over an acceptance test |
| enterprise, AEM-integrated | portable, provider-neutral, read-only |

Cite Adobe Digital Insights traffic research as evidence. Never name their product.

### The model everything hangs off

```
reach → read → extract → identify → trust → cite → land
```

Seven stages, seven specialists, one entrypoint. Each finding names the stage that broke, on
which retrieval surfaces, with quoted evidence and a stated confidence.

### Where an LLM beats a crawler, and why that is the headline

A coded algorithm cannot deduce what a customer wanted, why they did not stay, or what an
assistant was trying to satisfy. Three judgments carry the submission:

1. **Intent** — what is a customer in this category actually trying to accomplish, and is this
   page the answer to the question that would surface it?
2. **Confirmation** — given the question that brought a visitor here, what on this page fails
   to confirm it?
3. **Selection** — given the competing sources, what makes this page the worse citation?

These are the method, not a report section (see §6). They stay capped at medium confidence
unless a deterministic observation corroborates them. That cap is the defence when a judge asks
why the interesting half is believable.

---

## 2. Frozen file tree

```
brand-retrieval-readiness/            ← zip root
├── marketplace.json                  ← 8 skills, exactly one entrypoint:true
├── README.md
├── skills/
│   ├── audit-orchestrator/           ← ENTRYPOINT
│   │   ├── SKILL.md                  ← composition, fallback chain, budgets, parallel dispatch
│   │   ├── scripts/collect_snapshot.py   ← ALL network I/O lives here (~40% of the code)
│   │   ├── scripts/build_report.py       ← merge, IDs, dedup, arithmetic guard, validation
│   │   └── references/
│   │       ├── output_schema.json
│   │       ├── finding_fragment.json
│   │       ├── snapshot_schema.json
│   │       ├── excerpts_schema.json      ← NEW (§4.3)
│   │       ├── check_catalog.json        ← NEW (§4.2) - the join key for everything
│   │       ├── severity_model.md
│   │       ├── provider_registry.json
│   │       ├── probe_protocol.md         ← NEW: how to phrase/record off-site probes
│   │       └── remediation_playbook.json ← prose; Phase 6
│   ├── access-discovery-audit/       ← reach   · SKILL.md + scripts/probe_access.py
│   ├── representation-parity-audit/  ← read    · SKILL.md + scripts/analyze_representation.py
│   ├── answer-coverage-audit/        ← extract · SKILL.md + references/question_archetypes.md
│   ├── entity-consistency-audit/     ← identify· SKILL.md + scripts/check_entities.py
│   ├── freshness-consistency-audit/  ← trust   · SKILL.md (judgment over claim index)
│   ├── offsite-visibility-audit/     ← cite    · SKILL.md (NEW - capability-gated)
│   └── referral-experience-audit/    ← land    · SKILL.md (judgment + snapshot probes)
├── tests/
│   ├── fixture_server.py             ← stdlib http.server, declared status/headers
│   ├── fixtures/                     ← 10 single-condition, expected findings AND non-findings
│   ├── sample_fragment.json          ← the G1 oracle
│   └── run_fixtures.py
└── evals/                            ← 6 prompt cases
```

Never zipped: `docs/`, `research/`, `PARKED.md`, `GAMEPLAN.md`.

**Changes from `docs/BUILD_PLAN.md`:** `answerability-audit` → `answer-coverage-audit`;
`offsite-visibility-audit` added; three new `references/`; **the vendored-`_fetch.py` scheme is
deleted** — all network I/O is in `collect_snapshot.py` and every specialist is a snapshot
reader. One SSRF guard, one deadline, one robots-aware probe path, nothing to keep in sync. A
specialist run standalone tells the user to build a snapshot first; that is one line of prose,
not a second fetch stack.

---

## 3. Settled decisions

| Decision | Value |
|---|---|
| **Skills** | 7 specialists + orchestrator. `offsite-visibility` earns its slot: its evidence is the wider web, its fix family is content strategy and corroboration. Neither overlaps another skill. |
| **Scripts / model split** | Scripts own status codes, parses, counts, timeouts, schema. The model owns intent, passage completeness, contradiction, entity ambiguity, source selection. |
| **JS rendering** | Surface-scoped. Hydration-only facts reach Google AI surfaces and Copilot (rendering crawlers), not ChatGPT / Claude / Perplexity retrieval. Per-surface `render_evidence` confidence. High, not critical: a partial outage. |
| **Inline state** | A fact only in `__NEXT_DATA__` / RSC / Redux is **partially readable**, not lost. Medium. |
| **Browser** | A representation tool, not an experience simulator. One post-load DOM capture per flagged page, cap ~3. No task loops, no click simulation. Never install by default (§5.3). |
| **Environment** | The harness already states it. Scripts take declared facts as flags and never probe for tools. Probing is reserved for the target site. |
| **Off-site probes** | Capability-gated, always attempted when search is available, hard sub-budget, first thing shed at the deadline. Absence → `not_evaluated`, never a finding. |
| **Evidence not assertion** | A check counts as run only when its observation is recorded (engine, query, timestamp, result). No record → `not_evaluated`, whatever was declared. |
| **No modes** | One path. No `--depth`. The default must fit the cap. |
| **Findings are patterns** | Title states the site-level pattern, evidence carries counts and quotes, `affected_urls` carries instances (§6). |
| **Engagement** | Two distinct check families: continuation failure (AI-specific) and generic friction (classic). |
| **Adobe traffic data** | Justifies severity asymmetry only. Never asserts anything about the audited site. |
| **Severity ⊥ confidence** | Separate dimensions, never multiplied. `critical` requires high confidence. Low confidence → `needs_verification`. A failed tool call is never a site defect. |
| **Context** | The snapshot never enters model context. Scripts `--out` to disk and print small JSON. Excerpts bounded. |
| **Scores** | Named, denominator-explicit ratios are allowed ("62% of visible content survives into the raw response"). A blended readiness number is not. |
| **Never recommend** | FAQPage/HowTo schema (retired), `llms.txt` as discoverability, mandatory `@graph`, required Wikidata, estimated Core Web Vitals, BLUF word-count laws, IndexNow guarantees. |
| **Generalization** | Zero host-specific logic under `skills/`. Fixtures synthetic. Tuning and validation domains split. |
| **Interpreter** | Python 3.9+, stdlib only. Node available but not required by anything. |

---

## 4. The contract — fix before any Phase 2 code

Phase 1 was committed but never exercised; the "G1 preliminary pass" commit was a one-line
schema tweak. Running G1 by hand shows a realistic fragment **fails** the fragment schema.

### 4.1 Blocking defects

1. **`finding_fragment.json` rejects `acceptance_test`.** `candidate_finding.suggested_action`
   is `additionalProperties: false` with only `summary` and `priority`. The specialist is the
   only component holding the page, so it cannot write the site-specific acceptance test the
   output schema expects. Add `effort`, `owner`, `acceptance_test` as optional.
2. **No check catalog** (§4.2).
3. **Judgment interfaces undefined** (§4.3).
4. **stdlib-only contradicts schema validation.** `jsonschema` is not stdlib. Vendor a ~150-line
   draft-07 subset validator into `build_report.py` covering only the keywords our schemas use
   (`type`, `enum`, `const`, `required`, `properties`, `additionalProperties`, `items`,
   `maxItems`, `pattern`, `minimum`, `minLength`, `maxLength`, in-file `$ref`). Keep the schema
   files as the contract and use real `jsonschema` in `tests/` as the dev-time oracle.

### 4.2 `check_catalog.json` — build this first, everything joins on it

`check_id` links fragments → dedup → `not_evaluated` → lint → playbook → category. The severity
model already forbids invented ids and nothing defines any. Three agents drafting skills in
parallel without it will produce three vocabularies.

```json
{
  "check_id": "REP-KEY-FACT-LOSS",
  "skill_id": "representation-parity-audit",
  "category": "representation-parity",
  "stage": "read",
  "pattern_template": "Key {fact_type} on {page_class} pages is absent from the raw server response",
  "mechanism": "one sentence, vendor-attributed where possible",
  "evidence_required": "direct-representation-comparison",
  "evidence_template": "Sampled {n} {page_class} pages; {k}/{n} omit {fact_type} from the raw response.",
  "severity_band": ["medium", "high"],
  "negative_control": "SSR page whose #__next contains the same fact in visible text",
  "affected_surfaces_default": ["chatgpt_search", "perplexity_retrieval", "claude_search"]
}
```

`pattern_template` and `evidence_template` are what stop agents writing incident-shaped titles.
`negative_control` is the "when NOT to flag" a judge looks for. Target ~30 entries. Playbook
prose can wait; ids, gates, templates and negative controls cannot.

### 4.3 `excerpts_schema.json`

Covers all three judgment interfaces, which currently have no shape at all:
`audit/excerpts/<skill>.json`, `audit/passages.json`, `audit/passages_checked.json`.

Excerpt file minimum: `skill_id`, `budget_chars`, `pages[]` with `url`, `page_class`, `title`,
`heading_tree` (level/text/id), `main_content_excerpt` (≤1,500 chars per candidate location,
with `char_offset`), a `claim_index` subset, plus per-skill extras (referral gets the probe
results; freshness gets sitemap dates; offsite gets the prompt set).

`passages.json`: `questions[]` with `question_id`, `question`, `source` (`site-derived` |
`market-derived`), `expected_page`, `candidate_passage` verbatim, `qualifier_present`.

### 4.4 Snapshot gaps

- **`site_type`** — absent entirely, and it is the Generalization rubric line. Classify
  conservatively (multiple allowed): saas, ecommerce, local-business, docs-developer,
  publisher, gov-edu, marketplace-platform, org-portfolio. Drive four things off it: which
  pages get sampled, which question archetypes apply, which claim types get extracted, and
  which checks are in scope at all.
- **`claim_index.type`** is `price|date|count|plan|version|hours` — SaaS-shaped. Add `address`,
  `phone`, `eligibility`, `deadline`, `stock`, `shipping`, `credential`. A clinic's decision
  facts are not pricing tiers.
- **`sitemap`** object — `url`, `http_status`, `parse_ok`, `entries_count`,
  `lastmod_present_count`, `lastmod_distinct_count`, `lastmod_sample[]`, plus per-page
  `sitemap_lastmod`. The freshness skill's headline check currently has no data.
- **Per-page `headers`** — allow-listed map. The WAF differential needs `server`/`cf-ray`;
  freshness can use `last-modified`; access wants `cache-control`, `content-language`, `link`.
- **`external_presence[]`** — `sameAs` and footer/social/registry links resolved by the
  collector: `url`, `declared_in`, `status`, `owned_vs_independent`, `brand_name_match`.
- **`capabilities`** — declared by the agent, not probed: `web_fetch`, `web_search`, `browser`,
  `subagents`, plus `notes`.
- `hreflang` becomes `{lang, href}[]`. `affected_surfaces` becomes an enum. Add
  `report_schema_version` to the report root.

### 4.5 Registry corrections

- Rename `claude_retrieval` → `claude_training`. ClaudeBot is the training bot per the
  registry's own `crawler_roles`. Keep `claude_search` at medium (undocumented).
- Add the Bing source URL to both `noarchive` and `nocache`:
  `https://blogs.bing.com/webmaster/september-2023/Announcing-new-options-for-webmasters-to-control-usage-of-their-content-in-Bing-Chat`.
  Verified wording: NOCACHE may appear in Copilot answers with only URL, title and snippet;
  NOARCHIVE is excluded from Copilot answers entirely; both still rank in ordinary Bing results.
- `severity_model.md` rule 6 names no severity. Two consecutive 5xx on `robots.txt` across the
  audit → high/high; a single one → `needs_verification`.
- Replace every `verified_in: "SECOND_REVIEW.md …"` with the source URL plus verification date.
  Shipped artifacts must not point at unshipped documents.

---

## 5. Runtime, capabilities, delegation

### 5.1 Budget

| Line | Value |
|---|---|
| Network deadline | 120 s |
| Per-request timeout | 8 s, one retry, safe GETs only |
| Concurrency | ≤ 3 |
| Total requests | 20-30 typical |
| Off-site probe sub-budget | ≤ 6 queries, shed first at the deadline |
| Model turns per specialist | ≤ 3; one input file, one output file |
| Whole audit | < 5 min, measured on ≥ 3 real sites, printed in the README |

A valid partial report always beats an overrun.

### 5.2 Capabilities come from the harness

No per-harness tool-name registry — it rots and it is wrong the moment someone runs it
somewhere we did not anticipate. The SKILL.md states capabilities abstractly and writes
instructions as tasks, not tool calls: *"search for how a customer in this category would ask
about X and record which domains are cited"*, never *"call WebSearch"*. The agent already knows
what it has and routes accordingly. Optional Exa/Brave keys are read from env, never bundled,
never required, never logged.

The agent declares what it used via `collect_snapshot.py --capabilities web_fetch,web_search,browser,subagents`
so scripts stay deterministic and `coverage` stays honest. `references/probe_protocol.md` covers
how to phrase and record a probe, which does not go stale, rather than which tool to call.

### 5.3 Browser ladder — never install by default

| Path | Download | Use |
|---|---|---|
| Browser the harness already exposes | 0 | first choice |
| System Chrome/Edge via Playwright `channel="chrome"` | 0 | second choice |
| `playwright install --only-shell` | ~100-115 MB | only on explicit user consent |
| `playwright install chromium` | ~280 MB on disk | never |

Bundling is impossible anyway; the zip cap is 50 MB. The static path (inline-state contrast +
metadata contrast) is the default and must be good enough to ship alone.

One post-load DOM capture buys exactly three things, and nothing else justifies the cost:
confirming the render gap at high confidence; separating collapsed-by-default content from
click-injected content; and catching overlays that render in after load. The accordion inversion
needs no interaction — content in the rendered DOM but hidden is present-but-collapsed, content
absent from the rendered DOM behind an accordion control is click-injected.

Ask to install only when all three hold: static evidence is genuinely ambiguous, no browser was
found, and the session is interactive. State the cost in the question. In a judged
non-interactive run nobody answers, so the default is skip and `not_evaluated`. **An audit that
hangs on a prompt is worse than one that admits a gap.**

### 5.4 Parallel dispatch — put this in the orchestrator SKILL.md

Judges will "probably" have subagents. Wall-clock is our top risk, and the design is already
parallel-ready because specialists share no state.

```
If your environment can run subagents concurrently, dispatch each specialist as its own task -
it is substantially faster and the audit is bounded at 5 minutes. Give each one: the marketplace
root, the snapshot path, its excerpt path, the path to its SKILL.md, and its output path.
Require it to return ONLY a one-line status. Never the fragment contents, never page text.

  Wave 1 (no dependencies)   access-discovery, representation-parity, entity-consistency,
                             freshness-consistency, answer-coverage
  Post-step                  collect_snapshot.py --passages audit/passages.json
  Wave 2 (needs wave 1)      referral-experience (needs passages_checked),
                             offsite-visibility (needs the prompt set from answer-coverage)

If subagents are unavailable, run the same waves in order in this session. A specialist that
fails or times out contributes not_evaluated entries. It never fails the audit.
```

`marketplace.json` array order encodes this dependency order.

### 5.5 Composition fallback chain

1. Walk up from the orchestrator's directory until `marketplace.json` is found.
2. Else look for sibling directories named as in the manifest.
3. Else, if the harness exposes the specialists as loaded skills, activate them by name.
4. Else **single-skill degraded mode**: the orchestrator's own scripts still emit a valid report
   with `coverage.specialists_resolved: 0` and judgment checks marked `not_evaluated`. The PS
   accepts a one-skill marketplace as a floor. A layout mismatch can never zero the submission.

---

## 6. Report design and authoring rules

### 6.1 Findings are patterns. This is the rule agents get wrong.

The problem statement's own example is the template:

> **title** — "No JSON-LD structured data on product pages"
> **evidence** — "Crawled 12 product pages; 0/12 contain schema.org markup."

Title states the site-level or template-level pattern. Evidence carries the count with its
denominator and the quotes. `affected_urls` carries the instances.

Wrong: *"A visitor asking about the blue scarf landed on the catalogue page."*
Right: *"Product references resolve to category listings rather than product detail pages"*,
with that landing as evidence.

The specific case is always the vivid thing, so agents drift toward incident-shaped titles.
`pattern_template` and `evidence_template` in the check catalog are the guardrail.

### 6.2 Intent is a method, not a section

Intent reasoning decides which findings exist and how they are prioritised. It does not become a
per-prompt table in the report — that would be a list of incidents. A compact coverage note is
fine; a row per question is not.

### 6.3 Report shape

PS floor fields (`site`, `audited_at`, counts-by-severity, findings with
`id/title/severity/evidence/suggested_action`) plus `audit_status`, `coverage`, `confidence`,
`affected_surfaces`, `check_id`, `category`, `why_it_matters`, `suggested_action.{priority,
effort, owner, acceptance_test}`, `opportunities[]`, `needs_verification[]`, `not_evaluated[]`,
`limitations[]`, `lint_warnings[]`, `human_summary`.

`opportunities[]` stays outside `findings` (they are not defects) but its count appears in
`summary`. `human_summary` is ~10 lines for a non-expert: what is broken, in what order, what it
costs. Arithmetic invariants are enforced in `build_report.py`, not the schema:
`total_findings == len(findings)`, one severity per finding, opportunities never counted,
sorted by severity then id so runs are stable.

---

## 7. Check inventory by skill

Seeds `check_catalog.json`. Every title below is pattern-shaped on purpose.

**access-discovery (reach)** — retrieval-crawler robots policy by role (training blocks are
policy, not outages); `noindex` on important pages; `nosnippet`/`max-snippet:0`/`data-nosnippet`
covering decision facts (Google AI features, documented); `noarchive`/`nocache` (Copilot,
documented); WAF differential (browser 200 / bot-UA 403, `cf-mitigated`, challenged responses
are always `text/html`); redirect and canonical conflicts; `robots.txt` 5xx; sitemap validity
where relevant; orphaned important URLs; `llms.txt` low and docs-scoped only. UA probes run on
robots-allowed paths only, homepage only, capped at medium confidence.

**representation-parity (read)** — key facts absent from the raw response; facts present only in
inline state payloads (medium, partially readable); text-bearing images with empty `alt`;
div-grids of ≥3 aligned columns with no `<table>`; canvas/SVG-only figures; video without
transcript; hidden text with an `sr-only`/skip-link allowlist. Appendix F (email summarisers) is
the same mechanism — name it in one sentence here rather than building an email skill.

**answer-coverage (extract)** — questions from two sources, site-derived and market-derived.
Unanswered category-standard questions; answers present but not self-contained (subject, claim,
units, timeframe, qualifier separated); qualifiers detached from claims; comparison data in
unlabelled grids; boilerplate swamping the answer. Unmet demand goes to `opportunities[]`, not
`findings[]` — a missing topic is not a defect. Writes `audit/passages.json`.

**entity-consistency (identify)** — invalid JSON-LD (a real high finding); brand-name
inconsistency across title / OG / canonical / H1 / schema / footer legal name; structured claims
contradicting visible ones; `sameAs` resolving to owned surfaces only, with zero independent
corroboration; entity-name ambiguity as an explicit model judgment with a required evidence
sentence. Never require Wikipedia, Wikidata, or `@graph`.

**freshness-consistency (trust)** — impossible or future dates; visible vs structured date
conflicts; sitemap `lastmod` vs `dateModified`; uniform build-stamp `lastmod`; superseded
products, versions and deprecated docs still linked; **the site contradicting itself across
pages** on price, plan, version or hours, adjudicated from the claim index with quotes on both
sides. Do not flag an evergreen page for lacking a date.

**offsite-visibility (cite)** — capability-gated. For the inferred prompt set: is the brand
mentioned, is the official page cited, is a third party cited instead, is the fact stated
correctly, is a competitor preferred. Record engine, query, timestamp, cited URLs on every
observation. Never call a sample of prompts a visibility score. Degrades to snapshot-only
reasoning over `external_presence[]` when search is unavailable.

**referral-experience (land)** — two families kept distinct. *Continuation failure*: the cited
claim is not confirmable above the fold with its qualifier; the answer passage is not one
contiguous visible run in raw HTML (text-fragment landings); the decision fact is collapsed by
default; no next action for the inferred intent. *Generic friction*: consent, paywall or login
overlay in the initial HTML; interstitials; autoplay; missing viewport; soft 404 (200 on a
missing path) or a dead-end 404 body; redirects that drop the path. Heading `id` coverage stays
low. `performance_risk` observations only, never a synthesised Core Web Vital.

---

## 8. Phase schedule and gates

Working days. Agents implement; the named human owns the gate verdict.

| Phase | Days | Content | Gate |
|---|---|---|---|
| **1 — Contract** | 1 | §4 in full: fragment fix, check catalog, excerpts schema, snapshot gaps, registry fixes, vendored validator | **G1** `tests/sample_fragment.json` validates; stub `build_report.py` converts it; output validates; arithmetic guard passes; all under Python 3.9. A gate that cannot fail is not a gate. |
| **2 — Collector + spine** | 2 | `collect_snapshot.py` (all network I/O, probes, claim index, excerpts, `--passages`, `--capabilities`), `build_report.py`, orchestrator SKILL.md with §5.4 and §5.5 | **G2** two timed runs on a real site: scripts-only wall-clock, plus one real judgment pass timed and multiplied. If it blows 5 min, cut judgment scope now. |
| **3 — Scripted specialists** | 1.5 | access-discovery, representation-parity, entity-consistency. Parallel agents against frozen schemas. | **G3** fragments from a real site feed a clean report |
| **4 — Judgment specialists** | 1.5 | answer-coverage, freshness-consistency, offsite-visibility, referral-experience. Parallel agents. | **G4** full 7-skill end-to-end, < 5 min measured, arithmetic clean |
| **5 — Fixtures + FP gate** | 1.5 (overlaps 3-4) | fixture server, 10 fixtures with expected non-findings, FP control corpus of 8-10 clean sites incl. the SSR Next.js negative control | **G5 (kill-risk)** clean sites yield zero critical and ≤ 1-2 high. Fix gates before adding any check. |
| **6 — Calibrate, freeze, ship** | 1.5 | ~12-site live corpus with human labels, freeze, sealed holdout run once, degradation drills, playbook prose, README, evals, zip | **G6** §11 checklist |

Degradation drills at Phase 6: no browser, robots-blocked, `robots.txt` 5xx, timeout mid-audit,
specialists unresolved. Each must produce a valid partial report.

---

## 9. Human workstream — field study

Failure-first, interleaved from Day 2. Ledgers already exist in `research/field-study/`.

Pick 10 sites where someone on the team knows a specific ground-truth fact (a price, an SSO
tier, a limit, opening hours, a return window). Run 8 question pairs × 2 engines (Perplexity plus
ChatGPT search or Google AI Mode) × 2 repeats, about 32 queries. Classify every outcome:
official cited / third-party cited / mentioned-not-cited / absent / wrong entity /
**fact stated wrongly** (the money case) / unhelpful landing.

Then diff cited against uncited on pipeline signals: is the fact in the raw HTML, robots policy
per role, JSON-LD types, first-80-words signal, empty `#root`, uniform `lastmod`, name in title
vs schema vs H1, overlay in raw HTML, image-only hero alt.

**Earn-a-check rule:** a signal becomes a check only if it repeatedly separates cited from
uncited, or repeatedly explains a misrepresentation. Everything else goes to `PARKED.md`.
A new check entering after Phase 5 needs a fixture and an FP re-run.

---

## 10. Team split (4 people)

| Owner | Scope |
|---|---|
| **A — contract & spine** | schemas, check catalog, `collect_snapshot.py`, `build_report.py`, orchestrator SKILL.md, all gate verdicts. Serial spine; the two shared APIs change only via a recorded version bump. |
| **B — scripted specialists** | access-discovery, representation-parity, entity-consistency + their scripts |
| **C — judgment specialists** | answer-coverage, freshness, offsite-visibility, referral-experience + question archetypes + probe protocol |
| **D — verification** | fixtures, FP corpus, live corpus labelling, field study, degradation drills, runtime measurement |

D is the bottleneck role and the one that protects the false-positive score. Do not let it
become part-time.

---

## 11. Submission checklist

- [ ] `marketplace.json` lists 8 skills, exactly one `entrypoint: true`, every path exists
- [ ] `uvx --from skills-ref agentskills validate skills/<name>` passes on all 8 (the package installs a binary called **`agentskills`**, not `skills-ref` — put the working command in the README)
- [ ] `agentskills to-prompt` inspected: entrypoint description triggers on implied audit intent; specialist descriptions defer to the orchestrator
- [ ] Every SKILL.md: name = directory, quoted string metadata, `compatibility` where network or Python is needed, `allowed-tools` declared, ≤ 500 lines
- [ ] Mechanism sentences with vendor quote + URL live in SKILL.md bodies, not only in `references/`
- [ ] Report arithmetic verified on 3 real runs; measured wall-clock < 5 min recorded in README
- [ ] Degraded mode demonstrated; fixtures pass under both 3.14 and 3.9 including expected non-findings
- [ ] FP corpus clean; holdout run once and reported honestly
- [ ] `grep -rn "GAMEPLAN\|Build status\|docs/" skills/ README.md` empty — no references to unshipped files
- [ ] `grep -rE` for studied domains under `skills/` empty
- [ ] Zip ≤ 50 MB, includes `tests/` and `evals/`, no model weights
- [ ] README: positioning, pipeline opener, skill table, composition + fallback, validator command, measured runtime, limitations, "what this will never claim"

---

## 12. Cut lines, in order

1. Field study 8 pairs → 6
2. Wayback CDX corroboration (optional and low-confidence by design)
3. `evals/` trace review → the 6 prompt cases only
4. Live corpus 12 → 6 sites, **before** the holdout is touched
5. Sealed holdout → FP-corpus-only validation
6. `offsite-visibility` degrades to snapshot-only reasoning and drops the live probe entirely
7. Merge freshness into orchestrator judgment steps

**`referral-experience` never drops below a SKILL.md. It is half the problem statement.**

---

## 13. Risk register

| # | Risk | Mitigation |
|---|---|---|
| 1 | Wall-clock on the judges' harness | G2 timing on Day 3, turn caps, parallel dispatch (§5.4), off-site shed first, degraded mode |
| 2 | Representation false positives with no browser | inline-state and metadata contrasts are high-specificity; the SSR Next.js negative control is the G5 gate |
| 3 | Context blowup | snapshot never read into context, `--out` discipline, bounded excerpts, subagents return one-line status |
| 4 | Agents write incident-shaped findings | `pattern_template` + `evidence_template` in the catalog; spot-check every skill's first three findings |
| 5 | Model overstates its own capabilities | evidence-not-assertion: no recorded observation means `not_evaluated` |
| 6 | Judgment non-determinism | scripts own all counts; quoted evidence required; medium-confidence cap; stable sort; disclosed in README |
| 7 | Scope creep | `PARKED.md` + vendor-documented-or-measured rule; G5 blocks new checks |
| 8 | Reads as an Adobe product clone | positioning table in §1; cite their traffic research, never their product |

---

## 14. Immediate next action

Phase 1, in this order, then commit as "Phase 1: G1 passed":

1. `finding_fragment.json` — allow `effort`, `owner`, `acceptance_test`
2. `check_catalog.json` — ~30 entries with pattern and evidence templates and negative controls
3. `excerpts_schema.json` — excerpts, passages, passages_checked
4. `snapshot_schema.json` — `site_type`, widened `claim_index`, `sitemap`, headers, `external_presence[]`, `capabilities`, hreflang pairs
5. `output_schema.json` — `affected_surfaces` enum, `report_schema_version`
6. `provider_registry.json` — rename `claude_training`, add the Bing URL, replace `verified_in` with source URLs
7. `severity_model.md` — rule 6 severity; add the pattern-level authoring rule
8. `tests/sample_fragment.json` + stub `build_report.py` with the vendored validator; run G1 for real
