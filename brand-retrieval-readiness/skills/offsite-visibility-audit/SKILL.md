---
name: offsite-visibility-audit
description: Probe how retrieval surfaces answer the site's inferred prompt set — is the brand mentioned, is the official page cited, is a third party cited instead, is the fact stated correctly, is a different entity resolved — with every observation recording engine, query, timestamp and result; without a search capability it degrades to snapshot-only reasoning over the site's external presence and never invents probe results. Normally invoked by audit-orchestrator; use alone only when asked specifically about off-site visibility concerns.
license: MIT
metadata:
  version: "1.0.0"
---

# Off-site Visibility Audit (cite)

This skill guards the **cite** stage: the site can be reached, read, and identified, and its
landing works — yet retrieval surfaces may still answer the category's questions with someone
else's page. That is the discoverability half of the problem statement, observed directly.
Google states there are "no additional requirements to appear in AI Overviews or AI Mode" —
which is exactly why this skill observes outcomes instead of promising mechanisms: the audit
cannot make a surface cite you, but it can record whether it does, and connect the miss to the
on-site stage that caused it (a missing answer passage, an ambiguous name, a stale fact).

Capability-gated by design: live probes run only when the harness declares `web_search`
(probes are attempted when search is available, hard sub-budget of six queries, first thing
shed at the deadline). Absence of capability means `not_evaluated` — never silence, never
invention.

## When to use

- Someone asks whether AI surfaces mention their brand at all, cite them, or cite a competitor.
- A known misrepresentation needs connecting to its on-site cause (pair with the owning skill;
  do not double-report — see negative controls).
- Out of scope: whether the site's own pages can be fetched and extracted (the pipeline stages
  before cite), and the visitor's landing experience (referral-experience-audit).

## Inputs

- Prepared excerpt file `audit/excerpts/offsite-visibility-audit.json` (one read): the prompt
  set (`extras.prompt_set` — question, `source`, question_id; written by answer-coverage and
  the `--passages` post-step), `extras.external_presence` (declared external links with
  resolution status and owned-vs-independent classification), and `extras.search_declared`.
- `references/probe_protocol.md` — the probe method: phrasing, recording, outcome classes,
  budget, variability rules. It binds everything below.
- Runtime contract: one read, one judgment, one write — at most 3 tool calls. Off-site probes
  are the first thing shed at the deadline; an unrun probe is `not_evaluated`, never inferred.

## Procedure

1. **Read the capability gate.** `extras.search_declared` is the only switch. Without it:
   emit every OFF-\* check as `not_evaluated` with the protocol's reason ("no search
   capability declared; live probes not run"), contribute the snapshot-only observations below,
   and finish. Do not approximate a probe from external presence.
2. **Select ≤ 6 probes** from the prompt set, weighted toward market-derived questions (they
   are the demand the site did not choose). At most one brand-anchored probe, labeled as
   navigational.
3. **Run and record** each probe per `references/probe_protocol.md`: engine, exact query,
   UTC timestamp, cited URLs (first 10), outcome class. One run is one observation; never
   reconcile repeats into a single answer.
4. **Gate the checks** from the recorded rows:
   - **OFF-BRAND-ABSENT** — prompts where no answer mentions the brand.
   - **OFF-THIRD-PARTY-PREFERRED** — prompts where a third party is cited though an official
     page answers the same question (that precondition is what separates this from
     ANS-QUESTION-UNANSWERED's cause).
   - **OFF-FACT-STATED-WRONG** — the money case: an answer states a fact the official page
     contradicts; quote both, with the official URL.
   - **OFF-WRONG-ENTITY** — the prompt resolves to a different entity sharing the name;
     record the observed effect and pair it with ENT-AMBIGUOUS-NAME (on-site cause) — report
     the cause once, cite the effect there.
5. **Snapshot-only observations (degraded mode):** without search, the OFF-\* checks stay in
   `not_evaluated` with the protocol's reason — the fragment's four entries plus a limitations
   note via the orchestrator's limitation surfacing is the complete output. The prepared
   `external_presence` data is entity-consistency-audit's to report (corroboration is its
   check): record nothing here that would double-report it, and never fabricate a pass gate
   for a check that did not run.
6. **Write** the fragment to the orchestrator's `audit/findings/` path.

## Findings (authoring rules)

- Titles follow each check's `pattern_template`; evidence follows `evidence_template` — every
  finding names engine, query, timestamp, and the recorded result rows. Titles state the
  pattern across the probe set ("The brand is absent from category-standard answers"),
  never one prompt's story.
- When NOT to flag (negative controls), in plain words, per check:
  - OFF-BRAND-ABSENT: no search capability, empty prompt set, or probes shed at the deadline —
    `not_evaluated`, never inferred from absence of evidence.
  - OFF-THIRD-PARTY-PREFERRED: no official page answers the question (that precondition
    belongs to ANS-QUESTION-UNANSWERED — pair the findings), or the third party is genuinely
    the better source for the prompt.
  - OFF-FACT-STATED-WRONG: the stated value matches the official page, or the official page is
    genuinely ambiguous or absent on the fact (ambiguous source material is an ANS finding,
    not misrepresentation).
  - OFF-WRONG-ENTITY: the probe output is unambiguous, or the ambiguity is already reported by
    ENT-AMBIGUOUS-NAME with its own evidence — cite that finding, do not re-report it.
- Severity and confidence are separate; follow
  `../audit-orchestrator/references/severity_model.md`. Probe findings are capped at medium
  confidence unless a deterministic on-site observation corroborates them (rule 8); one run is
  one observation — a single uncited prompt is never `high` on its own, and a probe sample is
  never a visibility score.

## Output

- The finding fragment to the orchestrator's `audit/findings/` path, shaped by
  `../audit-orchestrator/references/finding_fragment.json`. Never assign `F-` ids; the
  orchestrator does. Every recorded probe row appears in the relevant result's `observations`
  so the report's evidence is reconstructible. This skill carries no `opportunities[]` —
  market-derived demand with no answering page is answer-coverage's channel.
