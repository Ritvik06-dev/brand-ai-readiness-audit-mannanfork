# PHASE 3 BRIEF — scripted specialists (access, representation, entity)

Read `GAMEPLAN.md` §7 first; this brief is the execution contract for the three parallel
drafters. Gate verdicts belong to the human owner (A).

## Deliverables per specialist

1. `SKILL.md` — **fill `SKILL_TEMPLATE.md` exactly** (section order, voice rules, authoring
   rules). No extra top-level sections. Mechanism sentences with vendor quote + URL live in the
   body. 80–160 lines.
2. `scripts/<script>.py` — stdlib-only Python 3.9+, snapshot-only reader.
   - access-discovery-audit → `scripts/probe_access.py`
   - representation-parity-audit → `scripts/analyze_representation.py`
   - entity-consistency-audit → `scripts/check_entities.py`
3. The script self-validates its output fragment: `from build_report import validate` (same
   skill's scripts dir — allowed; it is the one sanctioned same-dir import) against
   `../references/finding_fragment.json`… note: validate lives in the ORCHESTRATOR's scripts
   dir. The orchestrator's `references/finding_fragment.json` path is resolved relative to the
   marketplace root at runtime — copy nothing; the script takes
   `--fragment-schema <path>` with the orchestrator's path as default, resolved via the
   marketplace-root walk (same fallback chain as the orchestrator). If unresolvable, skip
   self-validation with a printed note rather than failing.

## KILL-LIST — none of these may appear (each one is a previously-fixed mistake)

1. **No `_fetch.py`, no vendored registry slices, no network I/O.** ALL network I/O lives in
   `collect_snapshot.py`. Every specialist is a snapshot-only reader. Standalone mode is one
   line of prose: "build a snapshot first" (the stale `access-discovery-audit/SKILL.md` stub
   line referencing vendored `_fetch.py` is dead — do not resurrect it).
2. **No `answerability` string anywhere** — the skill is `answer-coverage-audit`. Ship-grep now
   includes it: `grep -rn "answerability" skills/ README.md` must be empty.
3. **No unshipped-doc references** (`GAMEPLAN`, `BUILD_PLAN`, `SECOND_REVIEW`, `PHASE1_REVIEW`,
   `docs/`, `Build status`) in any shipped file.
4. **No host-specific logic.** Zero studied-domain strings under `skills/`.
5. **No `F-` id assignment** in specialists; the orchestrator's `build_report.py` owns ids.
6. **No synthesized measurements**: no estimated Core Web Vitals, no invented probe results.
   A check counts as run only when its observation is recorded; otherwise `not_evaluated`.
7. **No incident-shaped titles.** Titles follow the check's `pattern_template`; evidence follows
   `evidence_template` (counts with denominators + quotes); `affected_urls` carries instances.

## Contracts you consume (frozen; change only via recorded version bump)

- Input: `references/snapshot_schema.json` (site_type, capabilities, pages[] with page_class,
  claim_index, inline_state, probes, external_presence, sitemap, robots groups with roles).
- Output: `references/finding_fragment.json` (skill_id enum, check_id pattern, gate enum,
  observations, evidence_quality, candidate_finding with suggested_action incl.
  acceptance_test).
- Vocabulary: `references/check_catalog.json` v2 — your checks are ACC-*/REP-*/ENT-*; every
  check_id, gate, severity_band, negative_control, pattern_template, evidence_template is
  already defined. Do not invent ids; do not weaken a negative control.

## Per-skill notes (from GAMEPLAN §7 — the source of truth for scope)

- **access-discovery (reach)** — crawler-role robots policy (training blocks are policy, not
  outages); index controls per surface (`nosnippet`/`max-snippet`→AI Overviews,
  `noarchive`/`nocache`→Copilot, both vendor-documented); WAF differential (`cf-mitigated`,
  challenged responses are always `text/html`); canonical/redirect conflicts; robots 5xx (2+
  consecutive → high/high, single → needs_verification); sitemap validity where relevant;
  orphans; `llms.txt` low and docs-scoped. UA-probe differentials cap at medium confidence.
- **representation-parity (read)** — key facts absent from the raw response (surface-scoped:
  high, partial outage — Google AI surfaces and Copilot render, ChatGPT/Claude/Perplexity
  retrieval do not; per-surface confidence from `provider_registry.json` `render_evidence`);
  inline-state-only facts (medium, "partially readable", acceptance test = "appears in visible
  raw text, not only in an inline script"); metadata contrast; non-text lock-in; div-grid
  semantics; script-only links; hidden text with the sr-only/skip-link allowlist. One sentence
  naming Appendix F (email summarizers) as the same mechanism — no email skill.
- **entity-consistency (identify)** — invalid JSON-LD; structured-vs-visible conflicts; name
  consistency across title/OG/canonical/H1/schema/footer; `sameAs` resolution with owned-vs-
  independent classification (owned social never corroborates; timeouts never become findings);
  entity ambiguity as an explicit model judgment with the required evidence sentence. Never
  require Wikipedia, Wikidata, or `@graph`.

## Gate G3 (human verdict)

1. All three fragments from a real site feed `build_report.py` into a schema-valid report.
2. **Known-good control (early FP signal — do not wait for Phase 5):** run the full specialist
   path on a well-built docs site (`https://docs.python.org` is the default; `agentskills.io`
   is the standing smoke target). `tests/run_smoke.py` is the one-command entry; after the
   specialists land it grows `--with-specialists`. Expected: **zero ACC findings, and nothing
   above low** from the three specialists. Any critical/high on a known-good site = the gates
   are wrong; fix before drafting anything else.
3. `agentskills validate` passes on all three; `--help` output correct (it is a live
   interface); SKILL.md files follow the template with no voice drift.

## Process

- Draft in parallel against this brief + the frozen schemas; return one-line status, not file
  contents. Owner A reviews every SKILL.md against `SKILL_TEMPLATE.md` before integration and
  spot-checks the first three findings of each script against `pattern_template`.
- Specialists never recrawl and never touch the network. If a needed observation is missing
  from the snapshot, that check goes to `not_evaluated` with the reason — and the missing
  observation is proposed to owner A as a `collect_snapshot.py` change, not improvised.
