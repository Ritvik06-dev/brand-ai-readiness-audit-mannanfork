---
name: answer-coverage-audit
description: Judge whether the questions a category's customers actually ask are answered by complete, extractable passages on the site - using a two-source prompt set (site-derived and market-derived questions), checking for unanswered category-standard questions, answers missing subject/units/timeframe, qualifiers detached from their claims, comparison data trapped in unlabelled grids, and boilerplate swamping the answer. Normally invoked by audit-orchestrator; use alone only when asked specifically about answer-coverage or content-extractability concerns.
license: MIT
metadata:
  version: "1.0.0"
---

# Answer Coverage Audit (extract)

> **Status:** stub — the full judgment procedure and `references/question_archetypes.md` land
> with the Phase 4 build. This file fixes the name, the two-source prompt set contract, and the
> interfaces (`audit/passages.json`, fragment).

## When to use

Stub - see description.

## Inputs

Bounded excerpts from the shared snapshot (`audit/excerpts/answer-coverage-audit.json`): per page
`url`, `page_class`, `title`, `heading_tree`, `main_content_excerpts` (<=1,500 chars per candidate
location with `char_offset`), and the `claim_index` subset.

## Procedure (contract - full procedure lands in Phase 4)

1. Classify the site's likely customer intents from the snapshot's `site_type` and observed
   pages; generate the question set from TWO sources: **site-derived** (what these pages claim
   to answer) and **market-derived** (what a customer in this category would ask regardless of
   what the site chose to publish). Cap the set at 5-8 questions; record `source` per question.
2. Map every question to its expected page and best candidate answer passage (verbatim).
3. Write `audit/passages.json` (shape: `references/excerpts_schema.json` -> `passages_file`).
   Market-derived questions with no answering page are the orchestrator's `opportunities[]`
   input - a missing topic is not a defect.
4. Write the finding fragment to the orchestrator's `audit/findings/` path.

## Output

Finding fragment per the orchestrator's `finding_fragment.json` (checks: ANS-* per
`check_catalog.json`; titles are site-level patterns, evidence carries counts with denominators)
plus `audit/passages.json`.
