# Independent Review & Recommended Approach
### Adobe University Hackathon 2026 — Round 3

Reviewed: `hackathon.txt` (source of truth), `FINAL_APPROACH.md`, `grok.txt`, `chatgpt.txt`,
`gemini.txt`, `gemini_researchreport.txt`, `glm.txt`, `glm_flash.txt`.
Primary sources re-verified: agentskills.io spec / best-practices / using-scripts,
OpenAI bots doc, Anthropic crawler doc, Perplexity crawler docs, Google AI-features doc,
2026 llms.txt evidence, 2026 AI-crawler JS-rendering evidence.

---

## 0. Verdict in one paragraph

`FINAL_APPROACH.md` is directionally correct and is the right base. Its six-specialist
pipeline decomposition, its crawler-role separation, its severity/confidence split, and its
false-positive discipline all survive verification. But it has one structural problem
(**it is too large to actually build in a take-home**), one place where it over-corrected
into being wrong (**the JS-rendering claim**), three unspecified mechanics that the rubric
grades directly (**how the entrypoint actually composes sub-skills; the context budget;
LLM latency inside the 5-minute cap**), and one half of the problem statement that is still
thin (**on-site engagement**). Sections 2–7 below fix each of those. Section 8 is the
site-finding protocol.

---

## 1. Re-verification against `hackathon.txt`

Everything below was checked line-by-line against the PS text.

| PS requirement | Status in `FINAL_APPROACH.md` |
|---|---|
| Single marketplace, `marketplace.json` at root, exactly one `entrypoint: true` | ✅ correct |
| Every skill folder independently valid per agentskills.io | ✅ stated — but see §3, this constrains the composition design |
| Report floor: `site`, `audited_at`, counts-by-severity, findings with `id/title/severity/evidence/suggested_action` | ✅ correct; extra fields explicitly allowed ("a floor, not a ceiling") |
| Cover **both** halves: off-site discoverability **and** on-site engagement | ⚠️ discoverability is strong; engagement is thin (§6); off-site is quietly pulled on-site (§7) |
| Named failure modes (crawlability, JS-render gaps, missing/invalid structured data, facts locked in non-text, stale/uncorroborated facts, entity ambiguity, weak orientation / no context retention) | ✅ all mapped |
| Proactive suggestions beyond detected defects | ✅ present, but hidden in a non-`findings` array — see §5 |
| Recommend-only, read-only, no auth, respect robots.txt, no rate abuse | ✅ correct |
| Self-contained manifest, no external service to resolve | ✅ correct — this is why live engine probes stay out of the runtime |
| ≤ 50 MB zip, no model weights | ✅ trivial |
| **< 5 minutes for a typical site** | ❌ **budget is wrong — see §4.** All drafts budget *network* time only. |
| Judged on unseen sites; graded on the marketplace itself, not one report | ✅ correctly internalised |

**Two things in the PS that every draft under-reads:**

1. *"Suggested actions ... prioritized by impact"* and *"a non-expert could act on"* (rubric,
   Output design). Nobody designed the report for a **non-expert reader**. A JSON blob with
   `check_id: REP-KEY-FACT-LOSS` is not that. Emit the JSON as required **and** have the
   entrypoint print a short human-readable summary alongside it. Cheap, directly graded.
2. *"Decomposing your reasoning into multiple focused skills (one per concern) is the point
   of the marketplace format."* The word is **reasoning**, not checks. The thing being
   decomposed is the diagnostic argument, not the HTTP calls. This is the strongest argument
   for the pipeline-stage decomposition and it should be the first sentence of the README.

---

## 2. Where `FINAL_APPROACH.md` is wrong

### 2.1 It over-corrected on JavaScript rendering — this is a real, costly error

`FINAL_APPROACH.md §2 "Do not adopt"` rejects *"claims that most AI crawlers never execute
JavaScript. Measure representation loss instead."* Half right, half wrong.

**Verified position (2026):** GPTBot, ClaudeBot and PerplexityBot fetch raw HTML and do not
execute JavaScript — GPTBot requests JS assets in ~11.5% of hits and ClaudeBot in ~23.8%,
and neither executes them (Vercel's crawler analysis and its 2026 follow-ups). Googlebot
and Bingbot **do** render, so Google AI Overviews / AI Mode and Microsoft Copilot inherit
rendering while the rest do not.

So the correct encoding is neither "React is invisible" nor silence. It is a
**surface-scoped mechanism**:

> A key fact that exists only after hydration is retrievable by Google AI surfaces and
> Copilot (which inherit rendering crawlers) and is *not* retrievable by ChatGPT, Claude
> or Perplexity retrieval, which read the raw response. Severity: **high**, not critical —
> it is a partial outage, and the report should name which surfaces are affected.

That single sentence is the most valuable output the whole marketplace can produce. Refusing
to state the mechanism throws away the differentiator. State it, attribute it, and still
measure the loss rather than inferring it from the framework name. (Do **not** cite the SEO
blogs that repeat this — cite Vercel's own crawler study. Search results on this topic are
dominated by GEO-vendor content farms and that is exactly where `gemini.txt`'s fake-precise
numbers came from.)

### 2.2 It is too large to build

Count what §5–§14 actually asks for: 7 skills × (SKILL.md + scripts + references), a
20-fixture unit suite, 36 live domains, 12 matched cited/uncited pairs run across 2–3
engines with ≥3 repeats each (≈108 manual assistant queries), an 8-domain sealed holdout,
an `evals/` directory with execution-trace review, and a 6-phase build. That is two to three
person-weeks. This is a take-home.

**The risk nobody flagged is the real one: a half-built seven-skill marketplace scores worse
than a complete four-script one.** The rubric rewards completeness and composition; it does
not reward ambition. Take the cut line in §4.3.

### 2.3 It leaves the composition mechanic unspecified — and that is a graded line

Rubric: *"does the entrypoint compose them cleanly, or is it padding?"* Every draft says the
orchestrator "invokes" or "dispatches to" sub-skills. **No runtime resolves
`marketplace.json`.** agentskills.io defines a single-skill format; the marketplace manifest
is, in the PS's own words, *"this contest's own lightweight convention."* And the spec's file
convention is *relative paths from the skill root* — it says nothing about crossing skill
boundaries. So "invoke crawl-access-audit" is a hand-wave that a judge reading the SKILL.md
will notice. Fix in §3.

### 2.4 Smaller corrections

- **`allowed-tools` syntax.** `glm_flash.txt` claims `allowed-tools: Bash(python3:*) Bash(curl:*) Read`
  is malformed and needs list syntax. It is **wrong** — the spec defines the field as
  *"a space-separated string."* That form is correct. (It is also flagged Experimental, so
  don't rely on it for behaviour; declare it for hygiene points.)
- **`compatibility:` is unused by every draft.** The spec has a frontmatter field expressly
  for *"required system packages, network access needs."* The PS says each skill should
  *"declare its tool needs."* This is free rubric credit:
  `compatibility: Requires Python 3.9+ (standard library only) and outbound HTTPS. A headless browser is optional and only raises confidence on render checks.`
- **`metadata` values must be strings.** `version: "1.0.0"` must be quoted — the spec defines
  metadata as a map of string keys to *string* values. Unquoted `1.0` is a YAML float and may
  fail `skills-ref validate`.
- **`name` must match the parent directory**, no consecutive hyphens, ≤64 chars. Trivial but
  it is the first thing a validator catches.
- **Validator is real and installable:** `pip install skills-ref`, then
  `skills-ref validate ./skills/<name>`. Also `skills-ref to-prompt` — useful for seeing
  exactly what a harness loads from your descriptions.
- **`ChatGPT-User` vs `Claude-User` differ and the drafts flatten them.** OpenAI: user-initiated
  fetches mean *"robots.txt rules may not apply"*, and ChatGPT-User is *"not used to determine
  whether content may appear in Search."* Anthropic: **all three** bots including `Claude-User`
  honour robots.txt. Encode the difference; it is exactly the kind of precision the "few false
  positives" line rewards. Also note `OAI-AdsBot` now exists, and OpenAI's own wording for the
  one severity-critical case: sites disallowing `OAI-SearchBot` *"will not be shown in ChatGPT
  search answers, though can still appear as navigational links."* Quote that verbatim in the
  remediation playbook — it is a documented mechanism, not an inference.
- **llms.txt: even weaker than the drafts say.** Two 2026 studies (a ~300k-domain citation
  correlation and a ~900-domain server-log study) both land on null; one found model accuracy
  *improved* when llms.txt was dropped as a predictor; Google has publicly stated it does not
  use llms.txt and has no plans to. Keep it as a **low, site-type-scoped** proactive suggestion
  framed as agent/MCP-harness navigation DX for docs sites — never as discoverability.
- **Google's own AI-features doc undercuts most GEO advice**: *"There are no additional
  requirements to appear in AI Overviews or AI Mode, nor other special optimizations
  necessary"* and *"there's also no special schema.org structured data that you need to add."*
  Cite this in the README. It is the cleanest possible defence of an evidence-first audit
  against a checklist audit, from the horse's mouth.

---

## 3. The composition mechanic (fix for §2.3)

Design it so that **all three** of these are true, and say so in the README:

1. **Each specialist is independently valid and independently useful.** Its SKILL.md takes a
   URL *or* a path to an existing snapshot. This satisfies the PS's hard rule ("every skill
   folder must independently satisfy the spec") and makes the decomposition genuine rather
   than decorative — each skill is a thing you'd actually install alone.

2. **The entrypoint composes by explicit, resolvable file paths — not by magic.** The
   orchestrator's procedure should read, literally:

   ```
   1. Resolve MARKETPLACE_ROOT = the directory containing marketplace.json
      (the parent of this skill's own directory's parent).
   2. Read MARKETPLACE_ROOT/marketplace.json to enumerate specialist skills.
   3. Run scripts/collect_snapshot.py --url <URL> --out ./audit/snapshot.json
   4. For each specialist S in manifest order:
        read MARKETPLACE_ROOT/skills/S/SKILL.md
        follow its "Snapshot mode" procedure against ./audit/snapshot.json
        it writes ./audit/findings/S.json
   5. Run scripts/build_report.py --in ./audit/findings --out ./audit/report.json
   ```

   That is deterministic, inspectable, and works in any harness that can read files and run
   Python. It is also honest about the fact that the marketplace layer is a convention.

3. **The orchestrator owns everything shared:** the one snapshot, the finding-ID assignment,
   dedup/root-cause correlation, severity normalisation, schema validation, the deadline, and
   the final emission. Specialists never fetch the site twice and never assign IDs. That is
   the sentence that proves it isn't padding.

**Sub-skill `description` fields are load-bearing.** In a real harness the description is all
the agent sees at selection time. Write them as *"Use when …"* trigger conditions, not as
summaries. Optimise them like you'd optimise a function signature.

---

## 4. Runtime, context, and the cut line

### 4.1 The 5-minute budget is not a network budget

Every draft sets a ~240 s network deadline inside a 300 s cap. But the cap covers the
**whole audit**, and this design spends real wall-clock on model turns: reading six
SKILL.mds, making semantic judgments, correlating, writing the report. That is plausibly
60–150 s of LLM latency on its own.

**Corrected budget:** network deadline **120 s**, per-request timeout 8 s, concurrency ≤3,
one retry on safe GETs only. ~20–30 total requests (robots + sitemap + 6–8 pages + 3 UA
probes + 1 not-found probe + a handful of `sameAs` HEADs) finishes in well under 60 s. That
leaves ≥150 s of headroom for the model. Then state the measured runtime in the README.

### 4.2 The context budget is the failure mode nobody named

A snapshot containing the raw HTML of eight pages is 300k+ tokens. **If it ever enters the
model's context the audit dies.** Non-negotiable rules, stated in the orchestrator SKILL.md:

- Scripts read the snapshot **from disk** and print **small JSON** to stdout. The snapshot
  file itself is never `Read` into context.
- Any script that could emit a lot takes `--out <file>` and prints only a summary
  (this is literally what the agentskills "Using scripts" guidance recommends: predictable
  output size, structured data to stdout, diagnostics to stderr, meaningful exit codes,
  `--help`, no interactive prompts).
- The one place the model needs prose — answerability — gets **bounded excerpts**: the
  snapshot pre-extracts, per page, the heading tree plus ≤1,500 characters of main content
  per candidate answer location. Never the page.

### 4.3 The cut line: build this, in this order, and stop when time runs out

Keep the six-specialist shape (it is right), but **do not write six scripts.** Write five,
and let three skills be judgment-over-snapshot.

| # | Component | Script? | Priority |
|---|---|---|---|
| 0 | `marketplace.json`, report JSON Schema, severity/confidence policy, finding fragment schema | — | **P0 — do first, it's the contract** |
| 1 | `audit-orchestrator` + `collect_snapshot.py` + `build_report.py` | ✅ 2 scripts | **P0** |
| 2 | `access-discovery-audit` + `probe_access.py` | ✅ | **P0** |
| 3 | `representation-parity-audit` + `render_diff.py` | ✅ | **P0** |
| 4 | `entity-consistency-audit` + `check_entities.py` | ✅ | **P0** |
| 5 | `answerability-audit` | ❌ SKILL.md + `references/question_archetypes.md`, reads snapshot | **P1** |
| 6 | `freshness-consistency-audit` | ❌ SKILL.md, reads snapshot dates + claim index | **P1** |
| 7 | `referral-experience-audit` | ❌ SKILL.md, reads snapshot + the not-found/redirect probes already in #2 | **P1 — but mandatory, it is half the PS** |
| 8 | `references/remediation_playbook.json`, `references/provider_registry.json` | — | **P1** |
| 9 | Fixture suite (10, not 20), FP control corpus | — | **P1** |
| 10 | Sealed holdout, evals/, matched-pair field study at full scale | — | **P2 / cut freely** |

Five scripts, stdlib-only. This is defensible on its own terms, and say so in the README:
*scripts own what must be exact (bytes, status codes, parses, counts); the model owns what
regex cannot judge (is this passage self-contained? is this the same entity? do these two
claims actually contradict?).* Skills 5–7 are precisely the checks where judgment beats
regex — that is a design decision, not a shortfall.

---

## 5. Report design — three small fixes

1. **Keep proactive suggestions out of `findings` (correct — they aren't defects) but make
   them impossible to miss.** Put them in a top-level `opportunities` array *and* reference
   the count in `summary` (e.g. `"opportunities": 3`). A judge scanning for the
   "beyond-defect" rubric line should not have to scroll.
2. **Emit a human-readable summary next to the JSON.** The rubric says *"a non-expert could
   act on."* Ten lines: what's broken, in what order to fix it, what it costs.
3. **Every finding carries an `acceptance_test`.** `FINAL_APPROACH.md` has this and it is the
   single best idea in the document — it forces every recommendation to be falsifiable and
   it is what "mechanism-sound" looks like in practice. Keep it. Add `confidence` and
   `affected_surfaces` (which retrieval surfaces this actually breaks) alongside.

Also add a `not_evaluated` list. Saying "browser unavailable, render gap unconfirmed" is
worth more than a guess, and it directly serves the FP line.

---

## 6. The engagement half — where you can actually win

Every draft converges on the same thin set: viewport meta, cookie overlay, breadcrumbs,
"click here" link text, and an apology for not measuring Core Web Vitals. Assume every
competent team ships exactly that. Here are mechanisms that are static, deterministic, safe,
and (as far as I can tell) absent from all six drafts.

**The framing that unlocks them:** a visitor arriving from an assistant is not a search
visitor. They arrive **with a pre-formed question and an expected fact already in hand**.
The referral fails when the page cannot confirm that fact fast. Every check below follows
from that.

### 6.1 Not-found handling for AI-referred traffic — dual-purpose, novel, one request

Assistants routinely cite URLs that have moved, or that they have subtly mangled. Probe one
random path (`/<uuid>`) and check two things:

- **Status.** A `200` on a nonexistent path is a **soft 404** — a genuine crawl/index-quality
  defect on the discoverability side too, because it lets junk URLs into indexes.
- **Body.** Does the 404 page offer search, navigation, or suggestions — or is it a dead end?
  A bare 404 makes an AI referral a guaranteed bounce.

One safe request, no ambiguity, covers both halves of the PS, and it will not be in anyone
else's submission.

### 6.2 Path-preserving redirects

Fetch a known deep page over `http://` and over the apex/`www` variant the site doesn't
canonicalise to. If either redirect drops the path and dumps the visitor on `/`, then every
citation of the non-canonical variant loses the answer entirely. Two requests, deterministic,
and it is a real and common misconfiguration.

### 6.3 Fragment and anchor survivability

Does the cited page's content carry stable heading `id`s / anchor links? If an assistant
cites a 4,000-word page and the visitor lands at the top with no way to reach the sentence,
the referral is technically successful and practically a bounce. Statically checkable:
count content headings with `id` attributes; note client-side routers that strip fragments.
Frame as medium/low with a concrete fix (stable slugged heading IDs, a table of contents).

### 6.4 The accordion inversion — this is the "encoded reasoning" the rubric wants

The same element gets **opposite verdicts depending on audience**:

- Content that is in the DOM but **collapsed by default** → fine for the machine, hostile to
  the human who arrived for exactly that fact.
- Content that is **injected only on click** → invisible to the machine, fine for the human.

Writing that distinction explicitly into a SKILL.md is worth more to a judge than ten more
checks, because it demonstrates that the skill reasons about a mechanism instead of matching
a pattern. Same trick applies to tabs and "read more" toggles.

### 6.5 Does the landing page restate the cited claim above the fold?

Model judgment over the snapshot: for each generated question, is the answer present in the
first screenful of main content, with its qualifier attached — or is the H1 a slogan and the
fact 900 words down? This is the engagement mirror of the answerability check and reuses the
same question set for free.

### 6.6 What to keep from the drafts

Viewport meta (real, high on mobile), consent/paywall/login overlay present in the **initial
HTML** (not guessed), interstitials, autoplay media, inconsistent product naming across pages
(breaks conversational context — appendix E without cosplay), no in-content next action on
decision pages.

### 6.7 What to keep refusing

Do not synthesise CLS/LCP/INP from static HTML. `gemini.txt` and `glm.txt` both do
("estimated CLS > 0.1"), and it is a fabricated measurement — the fastest way to lose the
false-positive line. Emit a **`performance_risk` observation** with the indicators (undimensioned
media, render-blocking scripts) and say plainly that it is a hypothesis requiring a real
Lighthouse/CrUX run. `FINAL_APPROACH.md` is right on this.

---

## 7. The off-site half — build the portable 60%

The PS names *"Off-site discoverability — why the brand isn't found or cited"* as one of the
two halves, and appendix D is entirely about cross-web agreement. Every draft quietly pulls
this on-site because of the self-contained constraint. That is the right constraint but the
wrong conclusion. Three things are portable, deterministic, and genuinely off-site:

1. **Verify the site's own declared external presence.** Take `sameAs`, footer social links,
   GitHub/npm/PyPI/docs links, press pages. `HEAD`/`GET` each. Does it resolve? Does the
   destination carry a matching brand name? Distinguish **owned** surfaces (the brand's own
   LinkedIn/X) from **independent** ones (Wikipedia, Wikidata, a package registry, a
   standards body) — owned social is not corroboration, and `FINAL_APPROACH.md` is right to
   say so. Findings: "the brand declares zero independent corroboration surfaces." Timeouts
   never become findings.

2. **Use the model's world knowledge as the entity-ambiguity oracle.** This is the correct
   division of labour and nobody framed it this way. Python cannot know that "Mercury"
   collides with a planet, an element and a bank, or that a two-word Indian SaaS brand name
   collides with a film. The model can — that is exactly the judgment a script can't make.
   Encode it as an explicit judgment step with a required evidence sentence:
   *"The name X also denotes {…}; the site's homepage, `<title>` and Organization schema
   contain no category, location or legal-name qualifier that distinguishes it."*
   That is appendix D's "mistaken identity" problem, solved portably.

3. **On-page contradiction as the portable form of "uncorroborated."** True multi-source
   contradiction needs third-party APIs. But **the site contradicting itself** is fully
   observable and is the highest-yield misrepresentation source: pricing page says $99,
   homepage says "from $79", a 2023 blog post says $49 — and the assistant will pick one.
   Method: the snapshot builds a **claim index** (prices, dates, counts, plan names, version
   strings, hours) per page; the model adjudicates disagreements across pages. Deterministic
   extraction, model judgment, quoted evidence on both sides. This is a first-class check and
   no draft makes it one.

Optional, free, no API key, worth a look if time allows: the **Wayback CDX endpoint**
(`http://web.archive.org/cdx/search/cdx?url=<page>&output=json`) gives timestamped snapshots,
which is real external corroboration for a `dateModified` that claims a recent update. Treat
as optional and low-confidence; never let a timeout become a finding.

---

## 8. How to find sites — a protocol you can actually finish

`grok.txt` and `FINAL_APPROACH.md §10` are both good here. The problem is scale: 12 matched
pairs × 3 engines × 3 repeats is ≈108 manual assistant queries, which is a full day of human
time you do not have. Cut it.

### 8.1 Do the false-positive corpus first, not the discovery corpus

**If you only have time for one corpus, build this one.** The rubric punishes false positives,
and clean-site behaviour needs **no ground truth to validate** — you already know the answer
should be "almost nothing." It is the cheapest possible signal that your gates are right.

Pick 8–10 sites you are confident are well-built, spanning architectures:

- large reference docs (MDN-class), commercial developer docs (Stripe-class)
- a government/public-service site with strong IA (gov.uk-class)
- an encyclopedic/editorial control (Wikipedia)
- **an SSR framework marketing site** (Next.js/Nuxt with `#__next` full of server-rendered
  text) — the critical negative control for your render gap
- a schema-rich commerce storefront (any competent Shopify store)
- a docs site that already ships `llms.txt` (should yield at most low recommendations)
- a site with legitimate `sr-only` / skip-link content (must not trip hidden-text checks)

**Gate:** if any of these produces a `critical`, or more than one or two `high`, your
thresholds are wrong. Fix the gates before adding a single new check. This is the highest-ROI
hour in the whole build.

### 8.2 Then the discovery corpus — inverted, because it's faster

Instead of building a 40-query bank and running it blind, run **failure-first from sites you
already know**. Pick 10 sites whose content you personally know contains a specific fact
(a price, a limit, an SSO tier, a return window, opening hours). Ask two citation-showing
surfaces the question that fact answers. You have ground truth for free, so you can classify
outcomes immediately:

- official site cited → **positive control**
- third-party cited instead → **the interesting case**
- brand mentioned, no citation
- brand absent
- wrong entity → entity ambiguity
- **fact stated wrongly** → misrepresentation; the most valuable case in the whole study,
  and the one the PS explicitly names

Then diff the pipeline for cited vs. not-cited: raw-HTML word count and whether the fact
appears in it, robots policy per crawler role, JSON-LD types, whether the first 80 words of
main content contain a number/date/named entity, empty `#root`/`#app`, `lastmod` uniformity,
brand name in `<title>` vs schema vs H1, overlay in raw HTML, image-only hero with empty alt.

**Budget: 8 pairs, 2 engines (Perplexity — always shows sources, fastest; plus ChatGPT with
search or Google AI Mode for a different crawler stack), 2 repeats.** ≈32 queries. Stop when
new pairs stop teaching new mechanisms — usually around six.

A signal earns a check only if it repeatedly separates cited from uncited, or repeatedly
explains a misrepresentation. If `llms.txt` doesn't separate them (it won't), it stays a
proactive suggestion. If raw-vs-shell does, it is P0.

### 8.3 Free ways to find each archetype (no paid APIs, no vendor lists)

| Archetype you need | How to find it, free |
|---|---|
| **True CSR SPA** (must flag) | Search the exact string `"You need to enable JavaScript to run this app"` — the create-react-app default noscript text. Also `"Loading..."` in a `<title>`. Verify by view-source, never by framework name. |
| **SSR that looks like a SPA** (must NOT flag) | Any Next.js/Nuxt marketing site; confirm `#__next` / `#__nuxt` contains real text in view-source. This is your most important negative control. |
| **WAF / bot challenge** | Fetch once with a browser UA and once with a retrieval-bot UA; keep the sites where they differ. Look for `cf-mitigated`, `server: cloudflare` + 403. |
| **Schema-poor SMB** | Google Maps / OpenStreetMap for one city + one category (clinics, contractors, restaurants). Endless supply. |
| **Ambiguous entity name** | Brand names colliding with common words, elements, planets, cities; 3-letter acronyms; Indian brand names that collide with film or place names. |
| **Stale / date-liar** | Corporate blogs with a "2024" in body copy on a page whose sitemap `lastmod` is last week; unmaintained product pages. |
| **Image-heavy / non-text lock-in** | Agency portfolios, fashion lookbooks, conference sites, newsletter landing pages. |
| **Paywall / consent wall** | EU news publishers. |
| **Popularity-stratified random sample** | Tranco (`tranco-list.eu`) — reproducible and free, good for an unbiased holdout. |
| **Subdomain discovery** (docs.*, help.*) | `crt.sh` certificate transparency search. Free, instant. |
| **Historical ground truth for freshness** | Wayback CDX API. Free, no key. |

Deprioritise: HTTP Archive (needs BigQuery/GCP), CrUX API (needs a key), Common Crawl index
(slow). They are all real, none is on the critical path.

### 8.4 Offline fixtures — 10, not 20

Live sites change under you; fixtures are your regression suite and they belong in the zip
as tests (not as skills). Ten single-condition HTML/HTTP fixtures buy most of the value:

1. `robots.txt` disallowing `OAI-SearchBot` **vs.** disallowing `GPTBot` only *(must produce
   very different severities — this is the single most important fixture)*
2. `robots.txt` 404 **vs.** 503 *(no restrictions vs. a real crawl problem)*
3. SSR React with `#root` full of text *(must NOT flag)*
4. True CSR shell with an empty `#root` and a `noscript` notice *(must flag)*
5. Legitimate `sr-only` skip link *(must NOT flag as hidden text)*
6. Invalid JSON-LD **vs.** valid JSON-LD without `@graph` *(only the first is a finding)*
7. Truthful varied `lastmod` **vs.** uniform build-stamp `lastmod`
8. Image-only price with a real `alt` **vs.** with an empty `alt`
9. Semantic `<table>` **vs.** a visually identical unlabelled `div` grid
10. Soft 404 (200 on a missing path) **vs.** a helpful 404

Every fixture declares both its expected findings **and its expected non-findings**. The
non-findings are the point.

### 8.5 Two rules from the PS itself

- **Never put a studied domain in the skill.** No `if domain == …`. They said they won't ask
  which sites you studied and none are graded; a hard-coded host is pure anti-generalisation
  risk with zero upside.
- **Split tuning from validation.** Hold out whole domains (and where you can, whole template
  families), and freeze the checks, gates, playbook and schema before you run them once.

---

## 9. What every draft got right (don't relitigate these)

Convergent across independent models and verified — treat as settled:

- Hub-and-spoke: one entrypoint + a small number of specialists split by **pipeline stage**
  (reach → read → extract → identify → trust → land), because that stage is also the mechanism
  the finding names. `chatgpt.txt` had the best model; `FINAL_APPROACH.md` operationalised it.
- One shared snapshot, built once by the orchestrator; specialists never recrawl.
- Severity and confidence are **separate dimensions**, not multiplied. (`grok.txt` says
  multiply; `FINAL_APPROACH.md` correctly overrules it.)
- Training-bot blocks (`GPTBot`, `ClaudeBot`, `Google-Extended`) are a **policy choice**, not a
  visibility outage. Retrieval-bot blocks (`OAI-SearchBot`, `Claude-SearchBot`, `PerplexityBot`,
  `Googlebot`) are the critical case, and only on a **differential** (browser 200 / bot 403).
- A spoofed UA proves a UA-dependent response from *your* IP, not that the verified crawler is
  blocked. Say it in the skill, cap confidence at medium. (Provider IP lists exist —
  `claude.com/crawling/bots.json`, `perplexity.com/perplexitybot.json` — mention them as the
  owner's verification path in the remediation, don't fetch them at runtime.)
- No live multi-engine probe in the graded runtime — not self-contained, not deterministic,
  not required. Use it in field research and mention the result in the README.
- No dedicated prompt-injection/security skill. Fold hidden-text into machine readability as
  a signal-vs-junk question. "Hidden instructions cause de-indexing" is not in the PS and is
  weakly evidenced.
- No dedicated email skill. Appendix F is the same mechanism as non-text lock-in — name it in
  one sentence inside the representation skill so the judge sees you read the appendix.
- Don't ship as laws: 30–60 word BLUF, 256–512 token chunks, `@graph` mandatory, Wikidata
  required, "ChatGPT always uses Bing", raw/rendered ratio < 0.40, estimated CLS.
- `gemini.txt` and `gemini_researchreport.txt` are the weakest inputs: the harness/backend
  taxonomy table is largely unsourced (several of those product→search-backend mappings are
  undocumented or user-configurable), and the precise-looking thresholds are GEO-vendor
  marketing. Mine them for vocabulary, not for facts.

---

## 10. The three sentences the README should open with

> This marketplace audits the assistant pipeline — **reach → read → extract → identify →
> trust → land** — and reports, for each break, which stage failed, on which retrieval
> surfaces, with quoted evidence and a stated confidence.
>
> Scripts own what must be exact: status codes, parses, counts, timeouts, schema validation.
> The model owns what regex cannot judge: whether a passage stands alone as an answer,
> whether two claims contradict, whether a name is ambiguous.
>
> It refuses to treat training-crawler policy, a missing `llms.txt`, or a guessed Core Web
> Vital as an outage — Google's own documentation states there are no special requirements or
> schema needed to appear in AI features, and the checks here are built accordingly.

That is the opposite of an AI-SEO scanner, and it is the position the rubric was written for.

---

## 11. Suggested next action

Build in this order and do not start a new check until the previous artefact exists:

1. `marketplace.json` + report JSON Schema + the finding-fragment schema + the
   severity/confidence policy. **The contract first — everything else is downstream of it.**
2. `collect_snapshot.py` (this is 40% of the total code; get the claim index, the bounded
   excerpts and the `--out` discipline right the first time).
3. `audit-orchestrator/SKILL.md` with the explicit path-resolution composition from §3.
4. `access-discovery-audit` — it carries the most severity weight and the most FP risk.
5. The 10 fixtures, then the FP control corpus. **Do not add checks until clean sites are clean.**
6. Everything else, in the §4.3 priority order.
