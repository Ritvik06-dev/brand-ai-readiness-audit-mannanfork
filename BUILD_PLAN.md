# BUILD PLAN — Brand Retrieval Readiness Marketplace
### Adobe University Hackathon 2026 · Round 3 · built from `hackathon.txt` + `SECOND_REVIEW.md` → `INDEPENDENT_REVIEW.md` → `FINAL_APPROACH.md` (newest governs on conflict)

Budget: **~14 working days ≈ 3 calendar weeks**; if the real window is 2 calendar weeks, apply cut lines 1–3 from Day 1 and overlap Phases 3–4 harder. Mode: **agent-built in this repo, human runs the field study**.
Environment verified: Python 3.14 (stdlib-only target), `uvx --from skills-ref agentskills validate` works, outbound HTTPS works.

---

## 0. What we are building (frozen scope)

One marketplace, **7 skills, 5 scripts** — the `INDEPENDENT_REVIEW §4.3` cut-line shape with the
`SECOND_REVIEW §5` amendments applied. Judgment-only specialists are not a compromise: the PS's
own example layout gives three specialists nothing but a SKILL.md (SECOND_REVIEW §4.6).

```
brand-retrieval-readiness/            ← zip root
├── marketplace.json                  ← 7 skills, exactly one entrypoint:true
├── README.md                         ← REVIEW §10 three-sentence opener
├── skills/
│   ├── audit-orchestrator/           ← ENTRYPOINT
│   │   ├── SKILL.md                  ← composition w/ fallback chain, budgets, degraded mode
│   │   ├── scripts/collect_snapshot.py   ← ~40% of all code
│   │   ├── scripts/build_report.py       ← merge, IDs, dedup, arithmetic guard, validation
│   │   └── references/
│   │       ├── output_schema.json        ← final report JSON Schema
│   │       ├── finding_fragment.json     ← specialist output schema
│   │       ├── snapshot_schema.json
│   │       ├── severity_model.md         ← severity ⊥ confidence + reporting gate
│   │       ├── provider_registry.json    ← roles, robots semantics, render_evidence, sources
│   │       └── remediation_playbook.json ← keyed by check_id, incl. forbidden claims
│   ├── access-discovery-audit/       ← SKILL.md + scripts/probe_access.py        (P0, scripted)
│   │   └── vendored: scripts/_fetch.py + references/registry_crawler_roles.json (SYNC'd copies)
│   ├── representation-parity-audit/  ← SKILL.md + scripts/analyze_representation.py (P0, scripted)
│   │   └── vendored: references/render_surfaces.json (SYNC'd copy) — snapshot-only script
│   ├── entity-consistency-audit/     ← SKILL.md + scripts/check_entities.py      (P0, scripted)
│   │   └── vendored: scripts/_fetch.py (SYNC'd copy) — for sameAs resolution
│   ├── answerability-audit/          ← SKILL.md + references/question_archetypes.md (P1, judgment)
│   ├── freshness-consistency-audit/  ← SKILL.md (P1, judgment over claim index)
│   └── referral-experience-audit/    ← SKILL.md (P1, judgment + snapshot pre-computes)
├── tests/                            ← in the zip on purpose (SECOND_REVIEW §8.4): hygiene evidence
│   ├── fixture_server.py             ← stdlib http.server, serves fixtures w/ declared status/headers
│   ├── fixtures/                     ← 10 single-condition fixtures, expected findings AND non-findings
│   └── run_fixtures.py
└── evals/                            ← 6 prompt cases (FINAL_APPROACH §12)
```

Development-only, **never zipped**: `research/field-study/` (ledgers, corpus notes), `PARKED.md`.

**Settled decisions — do not relitigate during the build** (source docs are the authority):

| Decision | Value | Source |
|---|---|---|
| JS rendering claim | Surface-scoped: hydration-only facts retrievable by Google/Copilot, not by ChatGPT/Claude/Perplexity retrieval; per-surface `render_evidence` confidence | INDEP §2.1, SECOND §2.2 |
| Inline-state payloads | Fact only in `__NEXT_DATA__`/RSC/state blob = **medium**, "partially readable", not lost | SECOND §2.2 |
| Scripts/model split | Scripts own status, parses, counts, timeouts, schema; model owns passage completeness, contradiction, entity ambiguity | INDEP §10, FINAL §13 |
| Composition | Explicit file-path resolution + ordered fallback chain + **single-skill degraded mode**; specialist descriptions defer to orchestrator | INDEP §3, SECOND §2.6 |
| Budgets | 120 s network deadline, 8 s/request, ≤3 concurrency, 1 retry; ≤3 tool calls per judgment specialist, one input file + one output file each | INDEP §4.1, SECOND §2.5 |
| Context | Snapshot file **never** enters model context; scripts `--out` to disk, print small JSON; excerpts ≤1,500 chars per candidate answer location | INDEP §4.2 |
| Severity/confidence | Separate dimensions; critical requires high confidence; low-confidence → `needs_verification`; failed tool call ≠ site defect | FINAL §8 |
| Engagement | Soft-404 probe (status + body quality), path-preserving redirects, text-fragment survivability, accordion inversion, above-fold answer confirmation; `performance_risk` observation only, never synthesized CWV | INDEP §6, SECOND §4.3 |
| Off-site portable | sameAs owned-vs-independent resolution + entity-ambiguity-as-model-judgment + on-page claim-index contradiction (in entity + freshness skills, not claimed as a separate "half") | INDEP §7, SECOND §2.3 |
| Never recommend | FAQPage/HowTo schema (retired), llms.txt as discoverability, `@graph` mandatory, Wikidata required, estimated CWV, BLUF word-count laws, IndexNow-guarantees-citations | FINAL §16, SECOND §3/§5.8 |
| Generalization | Zero host-specific logic anywhere in `skills/`; tuning/validation domains split; fixtures synthetic | INDEP §8.5 |
| Naming | Skill `name` = directory name, quoted string metadata, `compatibility:` on network skills, `allowed-tools` space-separated string | SECOND §1 |
| Cross-skill deps | **None.** Each skill vendors the slices it needs (`scripts/_fetch.py`, registry subsets) with `SYNC:` headers pointing at the canonical file; no cross-skill imports ever; Phase 7 re-syncs the copies | build review 1 |
| Passage contiguity | Post-step, not pre-computed: answerability writes `audit/passages.json` → `collect_snapshot.py --passages` checks text-node contiguity → referral judges. Manifest order encodes the dependency | build review 1 |
| Interpreter floor | Python **3.9+**, stdlib-only (dev box runs 3.14 — 3.10+ syntax will creep in by accident); fixture suite must pass under a 3.9 interpreter | build review 1 |

---

## 1. Phase schedule

Days are working days; the human field-study workstream (§2) runs interleaved from Day 3.

### Phase 0 — Skeleton & toolchain (Day 1, ~2h)
- Create layout above; stub all 7 skill folders with placeholder SKILL.md (name↔directory discipline from the first minute).
- `uvx --from skills-ref agentskills validate` every stub — the working command goes in the README later.
- Write `PARKED.md` (empty) and the build decision rule: *a new check enters only if vendor-documented or measured on our corpus; everything else parks.*

**Gate G0:** all 7 stubs validate; manifest parses with exactly one `entrypoint: true`.

### Phase 1 — The contract (Day 1–2)
Everything downstream consumes these files; nothing else starts until they're frozen.

1. `marketplace.json` — final ids/paths.
2. `output_schema.json` — PS floor fields + `audit_status`, `coverage` (incl. `pages_discovered/selected`, `specialists_resolved`, `time_seconds`), `confidence`, `affected_surfaces`, `check_id`, `category`, `why_it_matters`, `suggested_action.{priority,effort,owner,acceptance_test}`, `opportunities[]`, `needs_verification[]`, `not_evaluated[]`, `limitations[]`, `human_summary`.
3. `finding_fragment.json` — what each specialist writes: `check_id`, observations (raw JSON numbers/booleans, no prose conclusions), `evidence_quality`, gate verdict, candidate finding, `not_evaluated` reasons.
4. `snapshot_schema.json` — per-URL captures + claim index + excerpts map + capability register.
5. `severity_model.md` — severity definitions, confidence definitions, reporting gate.
6. `provider_registry.json` — per provider/agent: `role` (training / search-index / user-fetcher), robots semantics **per role** (incl. `ChatGPT-User`/`Perplexity-User` may ignore robots vs `Claude-User` honours it), `render_evidence{source,date,confidence}` per surface, snippet controls (`noarchive`/`nocache`→Copilot; `nosnippet`/`max-snippet`/`data-nosnippet`→Google AI features), source URL + `last_verified: 2026-09`.
7. **Dependency contract** (build review 1): which slices each skill vendors so no skill ever imports across skill folders — access + entity get `scripts/_fetch.py` (SSRF guard, `--allow-private`, redirect cap, timeouts; robots via stdlib `urllib.robotparser`) and registry subsets; representation gets `references/render_surfaces.json` and its script is **snapshot-only**; judgment specialists are snapshot+excerpts-only by design. Every SKILL.md declares `compatibility: Requires Python 3.9+ (standard library only) and outbound HTTPS. A headless browser is optional and only raises confidence on render checks.`

**Gate G1:** a hand-written sample fragment round-trips through a stub `build_report.py` into a schema-valid report.

### Phase 2 — Snapshot collector + orchestrator spine (Day 2–4)
- `collect_snapshot.py`: safety preflight (http/https only, no credentials, private-range guard + `--allow-private`), robots fetch/parse (404 vs 5xx distinguished), bounded discovery → stratified 6–8 pages with template clustering, per-page capture (raw HTML, visible text, metadata, headings/landmarks, links+anchors, JSON-LD/microdata, tables/images/canvas/accordions/forms, timings), **claim index** (prices, dates, counts, plan names, versions, hours), bounded excerpts to `audit/excerpts/<skill>.json`, capability register, no-browser probes: soft-404 (`/<uuid>`), path-preserving redirects (http→https, www↔apex), robots-aware UA probes (homepage only, only if the probed token is allowed there — SECOND §2.8). Prints a small summary; the file is the artifact.
- `build_report.py`: read fragments → root-cause correlation candidates → assign F-IDs → severity-then-id stable sort → **arithmetic guard** (counts == len(findings); opportunities never counted) → schema validate → never-claim lint (**warns** into `lint_warnings[]`, never fails — quoted evidence or page prose can legitimately match trigger patterns) → human summary → exit codes.
- `audit-orchestrator/SKILL.md`: the §3 composition procedure verbatim-in-spirit with the fallback chain (walk-up to `marketplace.json` → sibling dirs → harness-loaded skill names → degraded mode with `specialists_resolved: 0`), all budgets, never-Read-the-snapshot rules, partial-report-over-overrun.

**Gate G2 (kill-risk #1) — two timed runs on a real small site, both schema-valid:**
- **G2a — degraded mode** (scripts only) → scripts-side wall-clock;
- **G2b — one mock judgment pass**: feed the real `audit/excerpts/answerability.json` to the model once against the answerability SKILL.md, time read + judgment + write; ×3 ≈ the judgment-side budget. Also validates excerpt quality/size.

If G2a + 3×G2b blows ~5 min, cut judgment-specialist scope *now*, before they're written. Do not write a third specialist until both timings exist.

### Phase 3 — P0 specialists (Day 4–7)
Each: SKILL.md (lean, mechanism sentences with vendor quote + URL in the body — SECOND §7) + script, fragment output only. Standalone modes follow the Phase-1 dependency contract: **dual-mode (URL or `--snapshot`)** where HTTP is intrinsic to the mechanism — access (robots/UA probes) and entity (`sameAs` resolution) — and **snapshot-only** where the input is captured page content — representation (raw HTML + extracted text live in the snapshot; its SKILL.md documents the minimal per-page shape from `snapshot_schema.json` so any harness can construct one without a second fetch stack).

- **access-discovery-audit** + `probe_access.py` — FINAL §7.1 check list + SECOND §4: per-role robots analysis, index controls per surface (`noarchive`/`nocache`→Copilot severity high surface-scoped; `nosnippet`/`max-snippet`→AI Overviews), canonical/redirect conflicts, WAF differential (`cf-mitigated` + always-`text/html` signal), sitemap contextual (404-robots ≠ 5xx-robots), `llms.txt` low/docs-only, orphan detection among sampled important URLs. UA-probe findings capped at medium confidence (spoofed-UA evidence rule).
- **representation-parity-audit** + `analyze_representation.py` — SECOND §2.4 mechanisms, no browser assumed: shell signals, **inline-state contrast**, **metadata contrast**, non-text lock-in (empty-alt text-bearing images, div-grids ≥3 aligned columns w/o `<table>`, canvas/SVG-only, video w/o transcript), hidden-text with `sr-only`/skip-link allowlist. `affected_surfaces` inherited from registry `render_evidence`; severity per the surface-scoped JS mechanism.
- **entity-consistency-audit** + `check_entities.py` — JSON-LD parse/validity, identity matrix (title/OG/canonical/H1/schema/about/footer legal name), structured-vs-visible claim conflicts, `sameAs` resolution with owned-vs-independent classification (timeouts never become findings), entity ambiguity as an explicit **model judgment step** with the required evidence sentence (INDEP §7.2).

Parallelizable: the three SKILL.md drafts and script bodies can go to parallel subagents once G1's schemas are frozen — but the snapshot interface, fragment schema, and integration stay with the main thread.

**Gate G3:** all skills validate; fragments from a real site feed a clean report.

### Phase 4 — Fixtures + false-positive gate (Day 5–8, overlaps Phase 3)
- `fixture_server.py` + 10 fixtures (INDEP §8.4 list: OAI-SearchBot-vs-GPTBot disallow is fixture #1), each declaring expected findings **and expected non-findings**; `run_fixtures.py` asserts both.
- FP control corpus: 8–10 clean sites spanning architectures (INDEP §8.1), **including the SSR Next.js negative control** — the gate for the representation skill.

**Gate G4 (kill-risk #2):** clean sites → zero critical, ≤1–2 high. If not, fix gates before adding a single new check. Fixture authoring and corpus runs are subagent-delegable; verdict review is not. The fixture suite must also pass under Python 3.9 — `uv python install 3.9 && uv run --python 3.9 tests/run_fixtures.py` (guards against accidental 3.10+ syntax; verified installable in this environment) — and this 3.9 compile/run check repeats in every later phase that touches scripts.

### Phase 5 — P1 judgment specialists (Day 7–10)
- **answerability-audit** — question archetypes reference; 5–8 questions mapped to expected URLs; completeness = subject + claim + units/timeframe + qualifier attached; cross-page contradiction from the claim index; boilerplate-vs-answer judgment over bounded excerpts only; writes **`audit/passages.json`** (question → page → candidate answer passage).
- **freshness-consistency-audit** — impossible dates, visible-vs-structured conflicts, sitemap `lastmod` vs `dateModified`, version selectors/deprecation/stale internal links, self-contradiction adjudication with quoted evidence on both sides; do-not-flag list per FINAL §7.5.
- **referral-experience-audit** — text-fragment survivability (from the passage post-step below), above-fold answer confirmation, accordion inversion (in-DOM-collapsed vs click-injected — opposite verdicts, INDEP §6.4), overlays/cons walls in raw HTML, soft-404 body quality, path-preserving redirect results, heading-`id` **low** severity, `performance_risk` observations only.

**Passage post-step (kills the circularity):** after answerability, the orchestrator runs `collect_snapshot.py --passages audit/passages.json` — the same HTML→text-node parser the collector already implements checks each candidate answer exists as one contiguous visible run in raw HTML, writing `audit/passages_checked.json` for referral-experience. `marketplace.json` array order is execution order: `access → representation → answerability → entity → freshness → referral`, which guarantees answerability precedes referral.
- Orchestrator gains `opportunities[]` generation and the 10-line human summary.

**Gate G5:** full 7-skill end-to-end on a mid-size real site; wall-clock < 5 min measured *with* turn caps; report arithmetic clean.

### Phase 6 — Calibration, freeze, holdout (Day 10–12)
- Live corpus ≈ **12** non-holdout sites (reduced from 28 so human labeling fits ~1 day alongside the field study — build review 1), chosen to span FINAL §10.4 archetypes at reduced depth; human-label every finding TP / FP / duplicate / severity-wrong / remedy-wrong / unverifiable.
- **Freeze**: check definitions, severity gates, playbook, schema, page budget.
- Sealed holdout: 8 domains, run once, report misses/FPs honestly.
- Degradation drills: no-browser, robots-blocked, robots-5xx, timeout mid-audit → must yield valid partial reports.

### Phase 7 — Polish & submission (Day 12–14)
- README: REVIEW §10 three-sentence opener, skill table, composition + fallback chain, corrected validator command, **measured runtime**, degraded-mode note, "what this marketplace will never claim" section.
- `remediation_playbook.json` keyed by `check_id` (mechanism rationale, options, applicability, owner, effort, acceptance test, forbidden claims).
- Refresh every `last_verified` in the registry.
- `evals/`: 6 cases (normal, vague, redirecting URL, unreachable URL, auth-request → refuse, non-audit prompt → no activation).
- Final checklist (§4 below).

---

## 2. Field study — human workstream (Day 3–10, ~6–8h total)

Failure-first protocol (INDEP §8.2), interleaved so signals can still become checks:

1. **Day 3–4:** pick 10 sites where you personally know a specific fact (price, SSO tier, limit, hours, return window). Run 8 question-pairs × 2 engines (Perplexity + ChatGPT-search or Google AI Mode) × 2 repeats ≈ 32 queries. Log into `research/field-study/query_ledger.csv` (FINAL §10.6 columns: engine, run, timestamp, exact query, brand mentioned, cited URL, answer correct/current, landing useful).
2. **Day 5:** diff cited vs uncited on pipeline outputs (raw-HTML fact presence, robots per role, JSON-LD types, first-80-words signal, empty `#root`, uniform `lastmod`, name in title-vs-schema-vs-H1, overlay in raw HTML, image-only hero alt).
3. **Day 8:** second pass on whatever Phase 5 has built — verify the marketplace's mechanism findings against observed misrepresentations (the "fact stated wrongly" case is the money case).
4. **Earn-a-check rule:** a signal becomes a check only if it repeatedly separates cited from uncited or explains a misrepresentation; then it enters via a versioned iteration with a fixture + FP re-run. Everything else → `PARKED.md`.

If ahead of schedule by Day 10: extend to the 12-pair matched design (FINAL §10.4). Never behind: skip the extension, not the gates.

---

## 3. Working method

- **Serial spine:** Phase 1 → 2 → 3 → 5 integration. The snapshot interface and fragment schema are the two APIs everything shares; they change only via a recorded version bump.
- **Delegated to subagents (parallel):** fixture authoring, FP/live corpus run reports, specialist SKILL.md/script drafting against frozen schemas, archetype-site hunting for the corpus, eval case drafting. Main thread keeps: schemas, `collect_snapshot.py`, `build_report.py`, orchestrator SKILL.md, all gate verdicts, final integration.
- **Change control:** any new mechanism must be vendor-documented (URL quoted in the skill body) or measured on our corpus; otherwise `PARKED.md`. No studied domain name may appear anywhere under `skills/` — enforced by grep in Phase 7.
- **Both reviews' "never claim" lists are report-lint rules**, not suggestions: `build_report.py` rejects/remarks any action text matching them (e.g. recommends FAQPage schema, claims llms.txt discoverability, synthesizes a CWV number).

---

## 4. Submission checklist (Phase 7 exit)

- [ ] `marketplace.json` lists 7 skills, exactly one `entrypoint: true`
- [ ] `uvx --from skills-ref agentskills validate` passes on all 7; `to-prompt` inspected — specialist descriptions defer to the orchestrator
- [ ] Every skill folder: valid SKILL.md, name = directory, quoted string metadata, `compatibility` where network/Python needed, `allowed-tools` declared
- [ ] SKILL.md files lean (≤500 lines each); check catalogs live in `references/`
- [ ] Report schema: PS floor fields + arithmetic guard verified on 3 real runs
- [ ] Measured wall-clock < 5 min on ≥3 sites, recorded in README
- [ ] Degraded mode demonstrated (specialists unresolved → valid report, `not_evaluated` populated)
- [ ] FP corpus clean (no critical, ≤1–2 high); fixtures all pass including expected non-findings, under both 3.14 and 3.9
- [ ] Vendored slices in sync with canonical sources (`SYNC:` diff check across `skills/`)
- [ ] Holdout run documented honestly
- [ ] No host-specific logic (`grep -rE` for studied domains in `skills/` = empty)
- [ ] Zip ≤ 50 MB, no model weights, includes `tests/` and `evals/`
- [ ] README: opener, composition, validator command, runtime, limitations

## 5. Cut lines (drop in this order when behind)

1. Field study 8 pairs → 6 pairs
2. Wayback CDX check (optional, low-confidence by design)
3. `evals/` traces → the 6 prompt cases without trace review
4. Live corpus 12 → 6 sites — **before** the holdout is ever touched
5. Sealed holdout → FP-corpus-only validation
6. Merge freshness into orchestrator judgment steps; **referral-experience never drops below a SKILL.md** — it is half the PS

## 6. Risk register

| # | Risk | Mitigation |
|---|---|---|
| 1 | Runtime on the judges' harness unknown | G2 timing on Day 4, turn caps in SKILL.md, degraded mode, measured numbers in README |
| 2 | Representation FPs without a browser | Inline-state + metadata contrasts are high-specificity; SSR Next.js negative control is the G4 gate |
| 3 | Context blowup kills the audit | Snapshot never Read; `--out` discipline; bounded excerpts; turn caps |
| 4 | Judgment skills non-deterministic | Scripts own all counts; quoted-evidence requirement; stable sort; disclosed in README |
| 5 | Scope creep / half-built marketplace | PARKED.md + vendor-documented-or-measured rule; G4 blocks new checks |
| 6 | Studied-domain leakage | Grep gate in Phase 7; tuning/validation domain split |
