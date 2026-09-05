# Probe Protocol — how off-site visibility probes are phrased and recorded

This is the contract for any live retrieval-surface probe (offsite-visibility-audit, and the
human field study in `research/field-study/`). It describes method, not tools: the executing
agent uses whatever search capability the harness declared (`web_search`); scripts never call
engines. It does not go stale because it names no tool.

## The rules

1. **Evidence not assertion.** A probe counts as run only when its observation is recorded:
   engine, exact query string, timestamp (UTC), and result. No record → the check is
   `not_evaluated`, whatever the intent was.
2. **Never a score.** A sample of prompts is an observation set, not a visibility score. One
   run is one observation. Findings are phrased per the check's `evidence_template` with the
   recorded probe rows as evidence — never as "the brand ranks Nth" or "visibility is X%".
3. **Budget.** ≤ 6 probes per audit, drawn from the answer-coverage prompt set
   (`audit/excerpts/offsite-visibility-audit.json` → `extras.prompt_set`). Off-site probes are
   the first thing shed at the deadline; an unrun probe is `not_evaluated`, never inferred.
4. **Phrasing.** Probes are natural customer questions, not brand-leading searches. Prefer the
   market-derived questions from the prompt set verbatim — they are the demand the site did not
   choose. A probe phrased as `"Acme <brand-feature>"` measures navigational retrieval, not
   category visibility; use at most one such brand-anchored probe and label it.
5. **Outcome classes** (one per probe, in the recorded observation):
   `official-cited` · `third-party-cited` · `mentioned-not-cited` · `absent` ·
   `wrong-entity` · `fact-stated-wrongly` · `unhelpful-landing`.
6. **Citation capture.** Record every URL the answer cites (bounded: first 10), and whether the
   cited passage supports the answer. A citation to a page that does not contain the stated
   fact is `fact-stated-wrongly` evidence.
7. **Variability.** Answers vary with engine, prompt wording, locale, account state, and time.
   Repeat a probe only when the budget allows and record each run as its own row; never
   reconcile runs into one answer. Divergence between repeats is itself an observation
   (recorded in `notes`, never averaged away).
8. **Gate discipline.** OFF-\* findings follow the check's `evidence_template` (engine, query,
   timestamp in the evidence string). The misrepresentation case (`OFF-FACT-STATED-WRONG`)
   additionally quotes the official page's contradicting statement with its URL. Findings are
   capped at medium confidence unless a deterministic on-site observation corroborates them
   (severity_model rule 8).
9. **Capability gate.** Without a declared `web_search` capability, no probe runs: every OFF-\*
   check is `not_evaluated` with reason "no search capability declared; live probes not run",
   and the skill contributes snapshot-only observations (from `external_presence[]`) without
   inventing any probe result.
