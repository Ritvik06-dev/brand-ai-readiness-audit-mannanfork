# Severity & Confidence Model

Severity and confidence answer different questions and are **separate dimensions — never
multiplied** (overrules `grok.txt`; FINAL_APPROACH §8).

- **Severity:** *If true*, how much does this affect important discovery, correctness, or task
  completion?
- **Confidence:** How strongly does the available evidence establish that it *is* true?

## Severity

| Level | Definition | Typical shape |
|---|---|---|
| `critical` | A broad, confirmed blocker across important public surfaces, or a condition that makes most intended content unavailable/ineligible | Requires **high** confidence (reporting gate) |
| `high` | Important pages/facts cannot reliably be retrieved, attributed, kept current, or used by a relevant retrieval surface | One important page-class or one major surface affected |
| `medium` | Retrieval or task completion works but is materially degraded, or limited to part of the site; inline-state-only facts ("partially readable"); one minor surface affected | Bounded loss with a workaround or partial reach |
| `low` | Bounded hygiene issue or an evidence-backed optimization opportunity | Heading anchors, docs-site `llms.txt`, naming drift on one page |

### Surface-scoping rule

Findings name **which retrieval surfaces** are affected (from `provider_registry.json`
`render_evidence`). A fact present only after hydration is a **partial outage**: retrievable by
Google AI surfaces and Copilot (rendering crawlers), not by ChatGPT/Claude/Perplexity retrieval
→ typically **high, not critical**, with `affected_surfaces` populated. A fact present only
inside an inline state payload (`__NEXT_DATA__`, RSC, Redux/Apollo state) is **partially
readable** → **medium**, acceptance test: "the fact appears in visible raw text, not only in an
inline script."

## Confidence

| Level | Definition | Typical evidence |
|---|---|---|
| `high` | Repeated direct measurement, or a direct representation comparison (raw vs rendered vs extracted vs metadata) | `direct-measurement`, `direct-representation-comparison` |
| `medium` | One indirect measurement plus corroborating signals, or a semantic judgment with quoted evidence | `indirect-corroborated`, `semantic-judgment` |
| `low` | Hypothesis requiring owner logs, another tool, or another environment | `hypothesis` |

A spoofed-User-Agent differential proves a UA-dependent response **from the auditor's IP**, not
that the genuine verified crawler is blocked → cap such findings at **medium** confidence and
word them as *suspected* edge discrimination (mention owner-side verification via provider IP
lists in the remediation; never fetch them at runtime).

## Reporting gate (hard rules)

1. **`critical` requires `confidence: high`.** No exceptions.
2. Low-confidence hypotheses are never emitted as findings — they go to `needs_verification`.
3. A failed tool call, timeout, or unavailable capability is **never** a site defect; it goes to
   `coverage.capabilities_unavailable` / `not_evaluated`.
4. Every finding carries exact URL/path, the observation, and the method in `evidence`.
5. A robots `Disallow` against a **training** bot (GPTBot, ClaudeBot, Google-Extended) is a
   policy choice, not a visibility outage — `low` at most, framed as policy, never as a
   citation-loss finding.
6. `robots.txt` returning **404** means "no crawl restrictions" — not a defect. A **5xx** on
   robots.txt is a real crawl-delay condition: **two or more consecutive 5xx across the audit →
   `high` severity / `high` confidence**; a single occurrence → `needs_verification`, never a
   finding (PHASE1_REVIEW §4.3). The collector records every attempt; the access gate reads the count.
7. Root causes over symptoms: correlated observations that share one mechanism (e.g., empty
   shell + raw pricing absent + nav-only extraction = **one** finding) are merged by the
   orchestrator; downstream effects become `affected_urls`/`affected_surfaces`, not separate
   findings.

## Suggested-action priority

`priority` mirrors severity of the resolved mechanism, adjusted by site type and effort:

- fix the **root cause** before cosmetic improvements;
- every action carries `effort` (`small|medium|large`), an `owner` where inferable, and an
  **`acceptance_test`** — a concrete, reproducible check that proves the fix resolved the
  mechanism;
- actions must never claim guaranteed rankings, citations, or specific AI-surface outcomes;
  see `remediation_playbook.json` forbidden-claims list (Phase 5+).

## Arithmetic invariants (enforced by `build_report.py`)

- `summary.total_findings == len(findings)` exactly; opportunities are never counted as findings.
- Exactly one severity per finding; findings sorted by severity then id so output is stable
  across runs.
- Every `check_id` in findings resolves to a defined check; no invented ids.
