# SKILL.md template — every specialist fills this skeleton exactly

Judges read the seven specialist files side by side. One voice, one section order, one style of
evidence. Fill every `<placeholder>`; delete nothing; do not add top-level sections. Target
length when filled: 80–160 lines — lean body, catalogs live in `references/`.

---
```markdown
---
name: <skill-id>
description: <What it does> <when to use it — implied intents, not tool names>. Normally
  invoked by audit-orchestrator; use alone only when asked specifically about <concern>.
license: MIT
[compatibility: Requires Python 3.9+ (standard library only)[ and outbound HTTPS].]   # scripted/network skills only
[allowed-tools: Bash Read]                                                            # scripted skills only
metadata:
  version: "1.0.0"
---

# <Human title> (<stage>)

<One paragraph: the mechanism this skill guards. What breaks, for whom, and why it matters.
If a vendor documents the mechanism, the quote + URL belong HERE in the body, not only in
references/. Example sentence shape: "OpenAI documents that sites disallowing OAI-SearchBot
'will not be shown in ChatGPT search answers' (developers.openai.com/api/docs/bots).">

## When to use

- <implied intents that activate this skill>
- <explicit out-of-scope: what a user might wrongly invoke this for>

## Inputs

- Primary: `--snapshot <path>` — the shared snapshot from `collect_snapshot.py`. Consume only:
  <list the exact fields this skill reads>.
- Standalone: if no snapshot exists, run
  `../audit-orchestrator/scripts/collect_snapshot.py --url <URL>` first (or ask the user to).
  This skill performs no network I/O of its own.
- [Judgment skills:] the prepared excerpt file `audit/excerpts/<skill-id>.json` (one read,
  one judgment, one write; at most 3 tool calls).

## Procedure

1. <deterministic step — name the check_id it implements>
2. <... every check from check_catalog.json appears here with its check_id and its gate:
   which observations, on which pages, with what evidence class, satisfy the finding gate>

## Findings (authoring rules)

- Titles follow the check's `pattern_template`; evidence follows `evidence_template` — counts
  with denominators and quotes; `affected_urls` carries the instances. Titles state site- or
  template-level patterns, never one visitor's incident.
- When NOT to flag (negative controls): <the check's negative_control restated in plain words,
  per check>.
- Severity and confidence are separate; follow `../audit-orchestrator/references/severity_model.md`.
  Semantic judgments are capped at medium confidence unless a deterministic observation
  corroborates them. A failed tool call is never a site defect — `not_evaluated` with a reason.

## Output

- [Scripted skills:] `--out <path>` writes the finding fragment shaped by
  `../audit-orchestrator/references/finding_fragment.json` (the script self-validates it).
  Stdout: a small summary only. Exit 0 = wrote fragment; 1 = validation failure; 2 = could
  not analyze (still writes a fragment with not_evaluated entries).
- [Judgment skills:] write the fragment yourself to the orchestrator's
  `audit/findings/<skill-id>.json`, same shape. Never assign `F-` ids; the orchestrator does.
```

Voice rules (all seven files):
- Second person for the agent ("read once", "write one file"); declarative for mechanisms.
- No exclamation marks, no marketing adjectives, no unexplained acronyms.
- Every mechanism sentence carries its vendor quote + URL or its measured basis.
- Every check_id named in the Procedure resolves to `check_catalog.json`.
