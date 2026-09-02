# Second Review — of `INDEPENDENT_REVIEW.md`, `FINAL_APPROACH.md`, and the six drafts
### Against `hackathon.txt`, with independent re-verification (2026-09-03)

Everything marked **verified** below was fetched from the primary source in this session, not
taken from either document. Everything marked **new** is a mechanism or correction that appears
in neither `INDEPENDENT_REVIEW.md` nor `FINAL_APPROACH.md`.

---

## 0. Verdict

Both documents are sound and the combination is the right plan. `FINAL_APPROACH.md` is the
correct synthesis of the six drafts; `INDEPENDENT_REVIEW.md` correctly identifies its four real
problems (size, the JS-rendering over-correction, the unspecified composition mechanic, the
network-only time budget) and its fixes survive verification.

What this review adds:

1. **Seven factual corrections**, none fatal, one of which will bite on day one
   (`skills-ref validate` is not the command; the binary is `agentskills`).
2. **Six mechanisms neither document has**, all documented by the vendors, all cheap, and two of
   them (Bing `NOARCHIVE`/`NOCACHE`, Google `nosnippet` as an AI-features control) are exactly the
   kind of "documented mechanism, not inference" evidence the rubric's false-positive line rewards.
3. **Four design gaps** the review's cut line leaves open: what `render_diff.py` actually
   measures with no browser, how many model turns the judgment skills are allowed, what happens
   when the harness does not preserve the `skills/` layout, and the loopback guard that will
   block the fixture suite.
4. A **line-by-line validation** of the merged plan against the PS (§6).

Adopt `INDEPENDENT_REVIEW.md` §3–§5 and §8 as written. Apply the amendments in §5 of this
document before starting the contract (`marketplace.json` + schemas).

---

## 1. Verification ledger

| Claim (as made in the docs) | Source checked | Result |
|---|---|---|
| `allowed-tools` is a space-separated string, experimental | agentskills.io/specification | **Verified.** `glm_flash.txt`'s "malformed" claim is wrong; `INDEPENDENT_REVIEW` is right. |
| `compatibility` field exists, ≤500 chars, for "system packages, network access" | spec | **Verified.** Spec adds: "Most skills do not need the compatibility field" — so use it only on skills that actually need network/Python. |
| `metadata` values must be strings | spec | **Verified** ("a map from string keys to string values"). Quote `version: "1.0.0"`. |
| `name` must match parent directory, no consecutive hyphens, ≤64 | spec | **Verified.** |
| SKILL.md ≤500 lines / <5,000 tokens recommended | spec + best-practices | **Verified.** |
| Validator: `pip install skills-ref` then `skills-ref validate` | PyPI + installed it | **Partly wrong.** Package is `skills-ref` (v0.1.1, 2026-01-10) but the **binary is `agentskills`**. `skills-ref validate` does not exist. See §2.1. |
| Scripts: structured stdout, diagnostics to stderr, `--help`, exit codes, no prompts, predictable output size / `--output` flag | agentskills.io/skill-creation/using-scripts | **Verified verbatim.** The `--out` discipline in `INDEPENDENT_REVIEW §4.2` is literally the spec's recommendation. |
| Scripts run from the skill directory root; relative paths | using-scripts | **Verified.** Relevant to §3.3 below (cross-skill script paths). |
| OAI-SearchBot blocked ⇒ "will not be shown in ChatGPT search answers" | developers.openai.com/api/docs/bots | **Verified verbatim.** |
| ChatGPT-User: robots "may not apply"; "not used to determine whether content may appear in Search" | same | **Verified verbatim.** |
| `OAI-AdsBot` exists | same | **Verified.** |
| Anthropic: ClaudeBot / Claude-SearchBot / Claude-User all honour robots.txt | support.claude.com article | **Verified.** IP list at `claude.com/crawling/bots.json`. |
| PerplexityBot respects robots; Perplexity-User "generally ignores robots.txt" | docs.perplexity.ai | **Verified verbatim.** Both docs flatten this; encode it (§4.2). |
| Google: "no additional requirements… no special schema.org structured data" for AI Overviews / AI Mode | developers.google.com/search/docs/appearance/ai-features | **Verified verbatim.** Also: "You don't need to create new machine readable files, AI text files, or markup". |
| Google-Extended is a token, not a crawler; does not affect Search | google-common-crawlers | **Verified verbatim**: "doesn't have a separate HTTP request user agent string… does not impact a site's inclusion in Google Search". |
| Google does not use llms.txt | Search Engine Journal / Illyes at Search Central Live | **Verified** (second-hand, but multiple independent reports of the same on-record statement). |
| llms.txt ~300k-domain study null; model accuracy improved dropping it; log study | SE Ranking / Ahrefs (137k domains, 97% of llms.txt files got zero requests in May 2026) | **Verified** as reported. |
| "GPTBot fetches JS in ~11.5% / ClaudeBot ~23.8%, neither executes" | vercel.com/blog/the-rise-of-the-ai-crawler | **Verified — but the study is dated 17 Dec 2024**, not 2026, and it measured GPTBot, ClaudeBot, PerplexityBot, AppleBot. It did **not** measure `OAI-SearchBot` or `Claude-SearchBot`. See §2.2. |
| `cf-mitigated: challenge` header | Cloudflare challenge docs | **Verified.** Response content-type is always `text/html` when challenged — a second, free signal. |
| Soft 404 is a Google-recognised defect | Google http-network-errors doc | **Verified.** |

---

## 2. Corrections to `INDEPENDENT_REVIEW.md`

### 2.1 The validator command is wrong (will bite immediately)

The PS, the spec page, and both documents say `skills-ref validate ./skill`. The package
`skills-ref` installs an executable named **`agentskills`**. Confirmed by running it:

```
$ uvx --from skills-ref agentskills --help
Commands:
  read-properties  Read and print skill properties as JSON.
  to-prompt        Generate <available_skills> XML for agent prompts.
  validate         Validate a skill directory.

$ uvx --from skills-ref skills-ref --help
An executable named `skills-ref` is not provided by package `skills-ref`.
```

Use `uvx --from skills-ref agentskills validate skills/<name>` (or `pipx run`). Put the working
command in the README so a judge who tries the PS's wording and fails does not conclude the
skills are invalid. Also use `agentskills to-prompt skills/*` once — it shows exactly what a
harness sees at selection time, which is the test for the `description` fields.

### 2.2 The JS-rendering evidence is older and narrower than stated

§2.1 of the review cites "Vercel's crawler analysis and its 2026 follow-ups". The Vercel study is
**December 2024**; I found no first-party 2026 follow-up, only GEO-vendor blogs repeating it.
And Vercel measured `GPTBot`, `ClaudeBot`, `PerplexityBot` — the **training/index** bots — not
`OAI-SearchBot` or `Claude-SearchBot`. Third-party 2026 tests say OAI-SearchBot also does not
render, but no vendor documents it either way.

This matters because the review's own best sentence ("retrievable by Google AI surfaces and
Copilot… not retrievable by ChatGPT, Claude or Perplexity retrieval") should carry
per-surface confidence, not one confidence:

| Surface | Renders JS? | Evidence | Confidence to encode |
|---|---|---|---|
| Google AI Overviews / AI Mode | yes (Googlebot WRS) | Google docs | high |
| Bing / Copilot | yes (Bingbot renders) | Bing docs | high |
| Perplexity (PerplexityBot) | no | Vercel 2024 measurement | high |
| ChatGPT training (GPTBot) | no | Vercel 2024 | high |
| ChatGPT search (OAI-SearchBot) | no | third-party tests only | **medium** |
| Claude (ClaudeBot / Claude-SearchBot) | no / undocumented | Vercel 2024 for ClaudeBot only | high / **medium** |

Put this table in `references/provider_registry.json` with a `render_evidence` field and let
`affected_surfaces` inherit it.

**Vercel's caveat is also a check** (**new**): AI crawlers "may still index content included in
the initial HTML response, like JSON data or delayed React Server Components". So a fact present
in the raw response only inside `__NEXT_DATA__`, an RSC payload, or an inline state blob is
**partially readable**, not lost. Severity for that case is medium, and the acceptance test is
"the fact appears in visible raw text, not only in an inline script".

### 2.3 "Off-site" is over-read

§7 says every draft "quietly pulls [off-site] on-site… the wrong conclusion". Read the PS again:
*"Off-site discoverability — why the brand isn't found or cited by AI assistants"* is the
**discoverability half** (visibility in AI apps, i.e. off the site) as opposed to the
**engagement half** (on the site). It is not a mandate to audit third-party web presence.
Appendix D does make cross-web agreement relevant, so the three portable checks in §7 are still
worth building — but as part of entity/trust, not as a claimed missing half. Do not spend P1
budget on Wayback or `sameAs` resolution before the FP corpus is clean.

### 2.4 `render_diff.py` has no defined mechanism without a browser

The cut line keeps `render_diff.py` as P0 while assuming no headless browser. With no second
representation there is nothing to diff. What the script can actually measure from the raw
response alone — and should be named accordingly (`analyze_representation.py`):

- shell signals: near-empty `#root`/`#app`/`#__next`, `noscript` "enable JavaScript" text,
  `<title>` = "Loading…", body visible-word count below floor;
- **inline-state contrast** (**new**): strings inside `__NEXT_DATA__` / RSC / Redux / Apollo
  payloads that do **not** appear in the visible text — this is a no-browser proxy for the
  render gap and is highly specific (SSR pages have both; CSR shells have JSON only);
- **metadata contrast** (**new**): a fact present in `og:description`, `meta description`, or
  JSON-LD that is absent from visible raw text — same idea, different second representation;
- non-text lock-in: text-bearing images with empty `alt`, canvas/SVG-only figures, div-grids
  with ≥3 aligned columns and no `<table>`, video without transcript.

If a browser tool exists in the harness, use it to upgrade confidence; never require it.

### 2.5 The model-turn budget is still unquantified

§4.1 fixes the network budget (120 s) and says the model gets "≥150 s of headroom". That is not a
budget. Three judgment-only skills over 6–8 pages, each reading a SKILL.md and an excerpt file
and writing a findings file, is 3–5 tool calls each on a typical harness. At 10–30 s per model
turn that is 2–5 minutes on its own. Rules to write into the orchestrator:

- each judgment skill gets **one prepared input file** (`audit/excerpts/<skill>.json`, built by
  `collect_snapshot.py`) and produces **one output file** — one read, one judgment, one write;
- the orchestrator states a **hard cap of tool calls per specialist** (e.g. 3) and instructs the
  agent to emit partial findings with `not_evaluated` rather than exceed it;
- measure end-to-end on the harness you expect the judges to use (Claude Code is the safe
  assumption given the skill format) and print the measured wall-clock in the README.

### 2.6 The path-resolution composition needs a fallback

§3's "MARKETPLACE_ROOT = parent of this skill's parent" assumes the judge's harness preserves
the `skills/<name>/` layout. If the harness copies each skill folder into its own skills
directory (as Claude Code does for `~/.claude/skills/<name>/`), the parent's parent has no
`marketplace.json`. Write the resolution as an ordered fallback:

1. walk up from the orchestrator's own directory until a `marketplace.json` is found;
2. else, look for sibling directories named as in the manifest (`../access-discovery-audit`);
3. else, if the harness exposes the specialists as loaded skills, activate them by name;
4. else, run in **single-skill degraded mode**: the orchestrator's own scripts still produce a
   valid report with `coverage.specialists_resolved: 0` and the judgment checks marked
   `not_evaluated`. The PS accepts a one-skill marketplace as a floor; degraded mode is that
   floor, and it means a layout mismatch can never zero the submission.

Related (**new**): because specialist `description` fields are in the harness's selection
context alongside the entrypoint's, a generic prompt like "audit example.com" can trigger a
specialist instead of the orchestrator. End every specialist description with *"Normally invoked
by `audit-orchestrator`; use alone only when asked specifically about <concern>."*

### 2.7 The SSRF guard blocks the fixture suite

`FINAL_APPROACH §6 Step 1` rejects loopback and private-network destinations. §8.4 of the review
wants HTTP fixtures (robots 503, soft 404, redirects), which need a local server. Add an
`--allow-private` flag (default off) to every network script, and a 60-line stdlib
`http.server` fixture server under `tests/` that serves each fixture with its declared status
and headers. Without this the ten fixtures cannot exercise the access script at all.

### 2.8 Smaller points

- **UA probes and robots compliance.** Probing with `User-Agent: OAI-SearchBot` on a path that
  robots.txt disallows *for that token* technically violates "respect robots.txt". Probe only the
  homepage and only after confirming the token is allowed there; if it is disallowed, the
  finding is the robots rule itself and no probe is needed.
- **Heading `id` severity (§6.3) should be low, not medium.** Google AI Overviews and AI Mode
  link with `#:~:text=` scroll-to-text fragments (an analysis of 15.7 M AI Mode citations found
  ~48 % were text-fragment highlights). Stable anchors help other surfaces; they are not what
  Google traffic depends on. See §4.3 for the check this *does* justify.
- **`opportunities` count in `summary`.** Fine, but keep `summary.total_findings` equal to
  `len(findings)` exactly; a judge will check that arithmetic first.

---

## 3. Corrections to `FINAL_APPROACH.md` beyond what the review said

- **Its own sample report contradicts its own rule.** §9's example has
  `"external_retrieval_probe": "completed"` in `coverage`, one section after §7.7 says the probe
  stays out of the runtime. Drop the field or rename it `external_retrieval_probe: "not_run"`.
- **"Page-type-appropriate structured data" needs a do-not-recommend list.** Google restricted
  FAQPage rich results to government/health sites in August 2023, removed HowTo in September
  2023, and retired FAQ rich results entirely on 7 May 2026. A remediation that says "add
  FAQPage schema" is mechanism-unsound in 2026. Plain-HTML Q&A pairs are the fix; schema is not.
  Add to §16's "never say" list.
- **§3.10 and §3.12 are right; §6 Step 7's 240 s is wrong** — the review's 120 s stands.
- **`freshness-corroboration` seed list names `ndtv.com` / `economictimes`** with a caveat;
  fine, but the review's rule applies: never let a studied domain appear anywhere in `skills/`.

---

## 4. Mechanisms neither document has (all vendor-documented)

### 4.1 Bing `NOARCHIVE` / `NOCACHE` control Copilot inclusion — **new**

Microsoft's own webmaster blog (Sept 2023, still current policy): a page with `NOCACHE` may
appear in Bing Chat/Copilot only as title, snippet and URL; a page with `NOARCHIVE` is excluded
from Bing Chat/Copilot and AI training entirely, while still ranking in ordinary Bing results.
Publishers and paywalled sites very commonly ship `noarchive` for unrelated reasons. This is a
**deterministic, high-confidence, high-severity, surface-scoped** check that no draft has:

> `<meta name="robots" content="noarchive">` on `/pricing` → the page cannot be quoted in
> Microsoft Copilot answers (Bing documentation). Surfaces affected: Copilot. Fix: replace with
> `nocache` if the intent is to prevent caching, or remove it.

Parse `robots` meta and `X-Robots-Tag` for `noarchive`, `nocache`, `nosnippet`, `max-snippet`,
`data-nosnippet` **per surface**, using the same registry as the crawler-role table.

### 4.2 Google `nosnippet` / `max-snippet` are the AI Overviews control — **new as a quoted mechanism**

Both docs list `nosnippet` under access checks. Neither quotes the mechanism, and the quote is
the evidence: Google's AI-features page says *"To limit the information shown from your pages in
Search, use `nosnippet`, `data-nosnippet`, `max-snippet`, or `noindex` controls"* and *"AI is
built into Search… robots.txt directives for Googlebot is the control"*. So `max-snippet:0` or
`nosnippet` on a decision page is a **documented** removal from AI Overviews / AI Mode, with the
same confidence as a robots `Disallow`. Severity high; not critical (search listing survives).

### 4.3 The cited passage must survive a text-fragment landing — **new**

Since roughly half of Google AI Mode click-throughs land with `#:~:text=<quoted passage>`, the
engagement question becomes concrete: *is the quotable sentence on the page verbatim, in visible
text, unbroken by markup?* A price split across `<span>`s, a claim assembled by JS, or a passage
inside a collapsed `<details>` will not highlight, and the visitor lands on an un-scrolled page.
This is the deterministic mirror of the review's §6.5 and reuses the same generated questions:
for each expected answer passage, check that it exists as one contiguous text node run in raw
HTML. Cheap, and it ties the two halves of the PS together with one measurement.

### 4.4 `Perplexity-User` and `ChatGPT-User` differ from `Claude-User` — encode all three

Verified: OpenAI and Perplexity both say their user-triggered fetchers may ignore robots.txt;
Anthropic says all three of its agents honour it. Consequence for findings: a robots
`Disallow` against `Claude-User` removes Claude's live fetch; the same rule against
`ChatGPT-User` or `Perplexity-User` probably does nothing. Severity and wording must differ.
Also encode: `ChatGPT-User` "is not used to determine whether content may appear in Search" —
so blocking it does not affect ChatGPT search citations at all.

### 4.5 The "cf-mitigated" response is always `text/html`

A second, free signal for the WAF differential: a challenged response has content-type
`text/html` even when the request was for `robots.txt` or `sitemap.xml`. Use it to distinguish a
challenge from an origin 403.

### 4.6 The PS's own example layout validates the five-script cut

`hackathon.txt` §1 shows `crawl-render-audit/`, `freshness-corroboration/` and
`engagement-audit/` each containing **only** `SKILL.md`, with `scripts/` and `references/` only
under the orchestrator. Judgment-only specialists are not a compromise; they are the organisers'
own illustration. Say so in the README in one sentence.

---

## 5. Amendments to adopt before writing the contract

Apply on top of `INDEPENDENT_REVIEW.md` §3, §4.3, §5, §8, §11:

1. **Validator:** `uvx --from skills-ref agentskills validate` in the README and the test script.
2. **Provider registry** gains `render_evidence` (source + date + confidence) and per-surface
   snippet-control semantics (`noarchive`/`nocache` → Copilot; `nosnippet`/`max-snippet` →
   Google AI features; robots token → each crawler role; user-fetcher robots behaviour).
3. **Rename `render_diff.py` → `analyze_representation.py`** and specify its no-browser
   mechanisms (§2.4). Browser presence only upgrades confidence.
4. **Model-turn budget** in the orchestrator SKILL.md: one input file, one output file, ≤3 tool
   calls per judgment specialist; partial output over overrun.
5. **Composition fallback chain** (§2.6) including single-skill degraded mode; specialist
   descriptions defer to the orchestrator.
6. **`--allow-private` flag** on every network script plus a stdlib fixture server in `tests/`.
7. **UA probes** limited to robots-allowed paths for the probed token.
8. **Do-not-recommend list** adds FAQPage/HowTo schema, `llms.txt` as discoverability,
   Markdown-for-bots as a ranking factor, and any estimated Core Web Vital.
9. **Text-fragment survivability check** (§4.3) added to the referral-experience skill as a
   deterministic pre-check that `collect_snapshot.py` can compute.
10. **Report arithmetic guard** in `build_report.py`: counts equal array length, exactly one
    severity per finding, `opportunities` never counted as findings, findings sorted by severity
    then id so the output is stable across runs.

---

## 6. Validation of the merged plan against `hackathon.txt`

| PS requirement | Merged plan (review + amendments) | Status |
|---|---|---|
| One marketplace, `marketplace.json`, exactly one entrypoint | orchestrator; `build_report.py` asserts the manifest | ✅ |
| Every skill folder independently valid per spec | each takes URL *or* snapshot path; validate with `agentskills validate` | ✅ (command corrected) |
| Report floor: `site`, `audited_at`, counts-by-severity, findings with `id/title/severity/evidence/suggested_action` | JSON Schema in orchestrator `references/`; extras: `confidence`, `affected_surfaces`, `acceptance_test`, `opportunities`, `not_evaluated` | ✅ |
| Both halves: discoverability **and** engagement | discoverability: access, representation, entity, freshness; engagement: referral skill + soft-404, redirect-path, text-fragment, accordion, above-fold checks | ✅ (engagement now has deterministic checks, not only judgment) |
| Named failure modes: crawlability, JS-render gaps, invalid structured data, non-text lock-in, stale/uncorroborated, entity ambiguity, weak orientation / no context retention | each mapped to one specialist; "context retention" = visitor arrives with a question the page must confirm | ✅ |
| Proactive suggestions, "relevant and non-obvious" | `opportunities[]`; non-obvious set: training/retrieval robots split, `noarchive`→`nocache` swap, canonical descriptor sentence consistent across title/OG/schema/about, truthful `lastmod`, plain-HTML Q&A instead of FAQ schema | ✅ (llms.txt stays low, docs-sites only) |
| Prioritised by impact; non-expert actionable | findings sorted; human summary printed alongside JSON; every action carries owner/effort/acceptance test | ✅ |
| Recommend-only, read-only, no auth, respect robots.txt, no rate abuse | ≤3 concurrency, ~20–30 requests, robots-aware UA probes (§2.8), no IndexNow ping | ✅ |
| Portable, declares tool needs, self-contained manifest | stdlib-only Python, `compatibility` field on network skills, no external service at runtime (Wayback optional and never a finding) | ✅ |
| ≤50 MB, no weights | trivial | ✅ |
| <5 min typical | 120 s network + explicit model-turn cap + measured wall-clock in README | ✅ once measured — **unmeasured until built** |
| Deterministic, safe | scripts own all counts/parses; judgment findings require quoted evidence and cap at medium confidence; stable sort | ⚠️ judgment skills are inherently non-deterministic; mitigated, not eliminated — say so in README |
| Generalisation, no studied domains in skills | no host-specific logic; fixtures synthetic; FP corpus first | ✅ |
| README: what each skill does, how the entrypoint composes | three-sentence opener from the review §10 + composition fallback chain + validator command + measured runtime | ✅ |

**Residual risks, in order:**

1. Runtime on the judges' harness is unknown until measured. Build the orchestrator first and
   time it on a real site before writing a third specialist.
2. A harness with no shell would make all five scripts inert. `glm.txt`'s worry is real but the
   PS explicitly expects `scripts/`; mitigate by making the degraded mode (§2.6) still emit a
   schema-valid report from judgment alone.
3. False positives in the representation skill without a browser. The inline-state and metadata
   contrasts (§2.4) are specific, but the SSR-Next.js negative control in the FP corpus is the
   gate — do not ship the skill until that site comes back clean.

---

## 7. Where the six drafts stand after this pass

Unchanged from `INDEPENDENT_REVIEW §9`, with two additions:

- `gemini_researchreport.txt`'s harness→backend table remains unsourced; additionally its
  sample `check_edge_access.py` treats *any* 401/403 to *any* bot UA as critical with no
  browser-UA differential and probes `Google-Extended` as an HTTP UA — Google documents that it
  has no UA string. Do not reuse that script.
- `glm.txt`'s "no scripts" position is contradicted by the PS's own layout, but its point that
  judges read SKILL.md stands: the mechanism sentences in §4.1–§4.3 above belong in the SKILL.md
  bodies, with the vendor quote and URL, not only in `references/`.
