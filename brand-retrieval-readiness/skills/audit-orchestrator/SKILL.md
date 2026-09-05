---
name: audit-orchestrator
description: Audit a website for AI-discoverability and on-site-engagement problems and emit a single evidence-backed audit report. Use when asked to audit a site or domain, or to diagnose why a brand is hard to find or misrepresented in AI assistants, or why visitors who arrive do not engage. The sole entrypoint of this marketplace; composes the six specialist skills in manifest order.
license: MIT
compatibility: Requires Python 3.9+ (standard library only) and outbound HTTPS. A headless browser is optional and only raises confidence on render checks.
allowed-tools: Bash Read Write Grep
metadata:
  version: "1.0.0"
---

# Audit Orchestrator (marketplace entrypoint)

This marketplace audits the assistant pipeline — **reach → read → extract → identify → trust →
land** — and reports, for each break, which stage failed, on which retrieval surfaces, with
quoted evidence and a stated confidence.

**Division of labor:** scripts own what must be exact — status codes, parses, counts, timeouts,
schema validation. You (the model) own what regex cannot judge — whether a passage stands alone
as an answer, whether two claims contradict, whether a name is ambiguous.

**Recommend-only.** This marketplace never modifies a website. Refuse any request to change,
authenticate to, or submit forms on the audited site.

## Inputs

- A public http(s) URL (required).
- Optional: an existing `snapshot.json` to re-report from.

All artifacts go to a working directory `./audit/`: `snapshot.json`, `excerpts/`, `findings/`,
`passages.json`, `passages_checked.json`, `report.json`. Create it as needed and run scripts
from there with explicit paths.

## Budgets (hard)

- **Network:** `collect_snapshot.py` enforces a 120 s deadline, 8 s per request, serial
  requests. Do not retry it; read its printed notes instead.
- **Off-site probes:** hard sub-budget of <= 6 queries, and the first thing shed at the
  deadline. Absence of a search capability means `not_evaluated`, never a finding.
- **Model turns:** each judgment specialist is ONE read (its excerpt file) + ONE judgment + ONE
  write (its fragment) — at most 3 tool calls each. Report build is at most 2 calls. Under time
  pressure, emit partial findings with `not_evaluated` — a valid partial report always beats an
  overrun.
- **Context:** NEVER read `audit/snapshot.json` — it contains raw HTML and will overflow your
  context. Only scripts touch it. You read excerpt files and script stdout only. Any script
  output larger than a screen means you called it wrong.

## Procedure

1. **Preflight.** Normalize the URL (add `https://` if missing; drop fragments). Refuse
   non-http(s) URLs, URLs with credentials, and private/loopback hosts — unless the user
   explicitly declared a local test fixture, in which case pass `--allow-private`. Refuse
   authenticated-area or site-altering requests entirely.

2. **Classify and declare.** Conservatively classify the site (multiple allowed, max 3):
   `saas, ecommerce, local-business, docs-developer, publisher, gov-edu, marketplace-platform,
   org-portfolio` — this gates page sampling, question archetypes, in-scope claim types, and
   which checks apply. Declare the capabilities you actually have as comma-separated flags.
   Then run:
   `python3 <orchestrator>/scripts/collect_snapshot.py --url <URL> --out ./audit/snapshot.json --site-type <types> --capabilities web_fetch[,web_search][,browser][,subagents]`
   Scripts take declared facts as flags and never probe for tools. It validates its own output,
   prints a small summary, and writes `audit/excerpts/<skill>.json` for each judgment
   specialist. Read only the printed summary. If it reports unreachable or deadline problems,
   continue with what was captured and record it.

3. **Enumerate specialists.** Resolve `MARKETPLACE_ROOT` (fallback chain below) and read
   `marketplace.json`. Specialists run in **manifest order** (skip this entrypoint).

4. **Scripted specialists** (access-discovery-audit, representation-parity-audit,
   entity-consistency-audit): run the script named in that skill's SKILL.md with
   `--snapshot ./audit/snapshot.json --out ./audit/findings/<skill-id>.json`. Read only its
   printed summary. If a specialist cannot be resolved, note it and continue.

5. **Judgment specialists** (in manifest order):
   - `answer-coverage-audit`: read `audit/excerpts/answer-coverage-audit.json` ONCE, follow its
     SKILL.md, write `audit/findings/answer-coverage-audit.json` AND `audit/passages.json`
     (questions from two sources: `site-derived` and `market-derived`; market-derived questions
     with no answering page feed `opportunities[]`, not findings).
   - Then run the post-step:
     `python3 <orchestrator>/scripts/collect_snapshot.py --passages ./audit/passages.json --snapshot ./audit/snapshot.json --out ./audit/passages_checked.json`
     (it also writes the offsite prompt-set excerpt).
   - `freshness-consistency-audit`: read `audit/excerpts/freshness-consistency-audit.json`
     once; write its fragment.
   - `offsite-visibility-audit` (wave 2): read `audit/excerpts/offsite-visibility-audit.json`
     (the prompt set) once. Run live probes ONLY if `web_search` was declared and the deadline
     allows — off-site probes are the first thing shed. Without search, reason over the
     snapshot's `external_presence[]` only; never invent probe results.
   - `referral-experience-audit` (wave 2): read `audit/excerpts/referral-experience-audit.json`
     once, plus `audit/passages_checked.json`; write its fragment.

6. **Report.** Run:
   `python3 <orchestrator>/scripts/build_report.py --site <host> --out ./audit/report.json --snapshot ./audit/snapshot.json --fragment ./audit/findings/<each>.json`
   It assigns finding IDs, dedups root causes, backfills `not_evaluated`, lints forbidden
   claims, validates the report schema, and prints the human summary.

7. **Emit.** Present the human summary verbatim, then the report JSON. State `audit_status`,
   `coverage`, and every `not_evaluated` check explicitly — "not evaluated" is never a defect
   and never silently dropped.

## Parallel dispatch (when the harness supports subagents)

If your environment can run subagents concurrently, dispatch each specialist as its own task —
it is substantially faster and the audit is bounded at 5 minutes. Give each one: the
marketplace root, the snapshot path, its excerpt path, the path to its SKILL.md, and its output
path. Require it to return ONLY a one-line status. Never the fragment contents, never page text.

- **Wave 1 (no dependencies):** access-discovery, representation-parity, entity-consistency,
  freshness-consistency, answer-coverage
- **Post-step:** `collect_snapshot.py --passages audit/passages.json`
- **Wave 2 (needs wave 1):** referral-experience (needs passages_checked),
  offsite-visibility (needs the prompt set)

If subagents are unavailable, run the same waves in order in this session. A specialist that
fails or times out contributes `not_evaluated` entries. It never fails the audit.

## Composition fallback chain (resolving MARKETPLACE_ROOT)

Try in order; use the first that works:

1. Walk up from this skill's own directory until a directory containing `marketplace.json` is
   found; specialists live at the manifest's declared paths.
2. Else, if sibling skill directories exist next to this skill (`../<specialist-id>/`), use
   them directly.
3. Else, if the harness has the specialist skills installed by id, activate each by name and
   follow its SKILL.md (all specialists are snapshot-mode capable).
4. Else **single-skill degraded mode**: run steps 1–2 and 6 only, passing `--degraded` to
   `build_report.py`. Perform the judgment checks yourself at reduced scope directly from the
   excerpt files (answer completeness, claim conflicts, landing confirmation), writing
   fragments in the `finding_fragment.json` shape under the corresponding specialist's
   `skill_id`, and record the degraded mode in the report's limitations. A one-skill
   marketplace is a valid floor — a degraded run must still emit a schema-valid report.

## Severity and confidence

Read `references/severity_model.md` before writing any candidate finding. In short: severity
and confidence are separate; `critical` requires high confidence; low-confidence hypotheses go
to `needs_verification`, never findings; a failed tool call is never a site defect; findings
name the affected retrieval surfaces from `references/provider_registry.json`.

## Output

One JSON report against `references/output_schema.json` at `./audit/report.json`, plus the
human summary in chat. Every finding carries evidence (URL + observation + method), a
suggested action with an acceptance test, and honest coverage. Do not invent scores; there is
no universal AI-readiness number.
