# Phase 0–1 Review — skeleton + contract
### Against `BUILD_PLAN.md`, `SECOND_REVIEW.md`, `INDEPENDENT_REVIEW.md`, and `hackathon.txt` (2026-09-03)

Scope of what exists: `marketplace.json`, README stub, seven SKILL.md stubs, and the orchestrator's
five `references/` files. No scripts, no fixtures, no sample fragments. Three commits.

---

## 0. Verdict

**Phase 0 is done properly. Phase 1 is not frozen — it was never exercised.** The commit labelled
"G1 preliminary pass" is a one-line change to `clusters` in `snapshot_schema.json`; there is no
`build_report.py` stub and no sample fragment anywhere in the tree, so the gate as defined in
`BUILD_PLAN.md` ("a hand-written sample fragment round-trips through a stub `build_report.py` into
a schema-valid report") did not run.

I ran it. A realistic fragment **fails** `finding_fragment.json`; a realistic report passes
`output_schema.json`. Beyond that one hard defect, the contract is missing four interfaces that
Phase 2's `collect_snapshot.py` (≈40% of all code) will consume. Fix §2 before writing a line of
Phase 2; §3 should land in the same pass because they all touch `snapshot_schema.json`.

---

## 1. What checks out (verified in this session)

| Item | Result |
|---|---|
| `uvx --from skills-ref agentskills validate` on all seven skills | all **Valid** (the CLI takes one path at a time — loop it) |
| `marketplace.json`: exactly one `entrypoint: true`; every `path` exists; ids = directory names | ✅ |
| All five reference JSON files parse | ✅ |
| `name` = directory; `metadata.version` quoted string; `compatibility` only on skills that run scripts or touch the network | ✅ per spec |
| Specialist descriptions end with the "Normally invoked by `audit-orchestrator`…" deferral | ✅ (SECOND §2.6) |
| `severity_model.md` faithfully encodes severity ⊥ confidence, the reporting gate, the surface-scoping rule, the inline-state "partially readable" medium | ✅ |
| Registry: `Perplexity-User` "generally ignores robots.txt rules" | ✅ **verified verbatim today** at docs.perplexity.ai |
| Registry: Bing `NOCACHE` / `NOARCHIVE` semantics | ✅ verified against the Sept 2023 Bing Webmaster Blog post — but the registry entry has **no URL** (see §4) |
| `.gitignore` excludes `audit/`; `research/` lives outside the zip root | ✅ |
| Manifest order `access → representation → answerability → entity → freshness → referral` encodes the answerability-before-referral dependency | ✅ |

---

## 2. Blocking — fix before Phase 2 starts

### 2.1 `finding_fragment.json` rejects `acceptance_test` (and `effort`, `owner`)

`candidate_finding.suggested_action` has `additionalProperties: false` and allows only `summary`
and `priority`. The specialist — the only component with the page in front of it — therefore
cannot write the site-specific acceptance test that `INDEPENDENT_REVIEW §5` called the single best
idea in the plan and that `output_schema.json` expects on every finding. As frozen, either the
playbook supplies a generic test (weaker, and the playbook is scheduled for Phase 7) or
`build_report.py` invents one.

**Fix:** add `effort`, `owner`, `acceptance_test` (all optional) to the fragment's
`suggested_action`. `build_report.py` fills from the playbook only when absent.

Round-trip result, for the record:

```
finding_fragment.json: 1 error
  results[0].candidate_finding.suggested_action: 'acceptance_test' was unexpected
output_schema.json: 0 errors
```

### 2.2 There is no check catalog, and `check_id` is the join key for everything

`check_id` links fragments → dedup → `not_evaluated` → lint → playbook → `category`.
`severity_model.md` says *"every `check_id` in findings resolves to a defined check; no invented
ids"* — but nothing defines any. The playbook is scheduled for Phase 7, and Phase 3 plans to hand
three specialists to parallel subagents "once G1's schemas are frozen." Three drafters with no
catalog will produce three id vocabularies.

**Fix:** `references/check_catalog.json` now, ~25–30 entries, one per check:

```json
{
  "check_id": "REP-KEY-FACT-LOSS",
  "skill_id": "representation-parity-audit",
  "category": "representation-parity",
  "mechanism": "one sentence, vendor-attributed where possible",
  "evidence_required": "direct-representation-comparison",
  "severity_band": ["medium", "high"],
  "negative_control": "SSR page whose #__next contains the same fact in visible text",
  "affected_surfaces_default": ["chatgpt_search", "perplexity_retrieval", "claude_search"]
}
```

The `negative_control` field is the "when NOT to flag" a judge reading the skill will look for.
Playbook prose (options, owner, acceptance-test template) can still land later — the ids, gates
and negative controls cannot.

### 2.3 The three judgment-skill interfaces are undefined

`snapshot_schema.json` declares an `excerpts_manifest` pointing at `audit/excerpts/<skill>.json`,
and the plan routes `audit/passages.json` → `collect_snapshot.py --passages` →
`audit/passages_checked.json`. **None of those three files has a shape.** They are the entire
input/output surface of the three judgment specialists and the thing G2b is supposed to time.

**Fix:** one `references/excerpts_schema.json` covering all three. Minimum for an excerpt file:
`skill_id`, `budget_chars`, `pages[]` each with `url`, `title`, `heading_tree` (level/text/id),
`main_content_excerpt` (≤1,500 chars per candidate location, with `char_offset`), `claim_index`
subset, and per-skill extras (referral: the probe results; freshness: sitemap dates). For
`passages.json`: `questions[]` with `question_id`, `question`, `expected_page`, `candidate_passage`
(verbatim), `qualifier_present`.

### 2.4 "Stdlib-only" and "schema validate" contradict each other

`jsonschema` is not in the standard library. `build_report.py` is specified as stdlib-only *and*
as validating against `output_schema.json`. On the dev box it happens to be installed
(4.26.0); on the judge's machine there is no such guarantee, and a `ModuleNotFoundError` in the
report builder zeroes the submission.

**Fix (recommended):** vendor a ~150-line draft-07 *subset* validator into
`build_report.py` supporting only the keywords the schemas actually use (`type`, `enum`, `const`,
`required`, `properties`, `additionalProperties`, `items`, `maxItems`, `pattern`, `minimum`,
`minLength`, `maxLength`, in-file `$ref`). Keep the JSON Schema files as the documented contract
and as the dev-time test oracle (real `jsonschema` in `tests/`). Alternative: PEP 723 inline deps
with `uv run`, which the agentskills spec endorses — but that assumes `uv` on the judge's box.
Don't.

---

## 3. Should fix in the same pass — `snapshot_schema.json` gaps

### 3.1 Sitemap `lastmod` is not captured

The freshness skill's headline check (`lastmod` uniformity, `lastmod` vs `dateModified`) has no
data: the schema holds `robots.sitemaps_declared` and `discovery.sitemap_urls_count` and nothing
else. Add a `sitemap` object (`url`, `http_status`, `parse_ok`, `entries_count`,
`lastmod_present_count`, `lastmod_distinct_count`, `lastmod_sample[]`) and a per-page
`sitemap_lastmod` so the comparison is local to the page.

### 3.2 Per-page response headers are absent

`FINAL_APPROACH §6 Step 3` lists response headers; the schema has only `x_robots_tag`. The WAF
differential needs `server`/`cf-ray`; freshness can use `last-modified`; access wants
`cache-control`, `content-language`, `link` (canonical/alternate via header). Add a bounded
`headers` map (allow-listed keys) per page and per probe.

### 3.3 Move *all* network I/O into `collect_snapshot.py`; drop the vendoring plan

`BUILD_PLAN` "Cross-skill deps" vendors `_fetch.py` into two specialists with `SYNC:` headers and a
Phase 7 diff check, so that access and entity can run in standalone URL mode. That is two copies
of the SSRF guard, two deadlines, and a drift check, for a capability the PS does not require —
"each skill folder must independently satisfy the spec" means a valid `SKILL.md`, not a second
fetch stack.

**Recommendation (reverses a "settled" decision — your call):** the collector already performs
UA probes, the soft-404 probe and redirect probes. Add `sameAs`/external-presence resolution to it
(`external_presence[]`: `url`, `declared_in`, `status`, `owned_vs_independent`, `brand_name_match`)
and every specialist becomes snapshot-only. Standalone mode for any specialist is then one line:
*"If no snapshot exists, run `../audit-orchestrator/scripts/collect_snapshot.py --url <URL>` first
(or ask the user to)."* One network stack, one 120 s deadline, one place to enforce robots-aware
probing, nothing to sync. The three P0 scripts become pure readers of one file, which is also the
easiest thing to fixture-test.

### 3.4 Smaller schema points

- `hreflang` is `string[]`; it should be `{lang, href}[]` — the locale-discovery check needs both.
- `claim_index.type` could use `phone` and `address` for the local-business archetype; optional.
- `output_schema.not_evaluated[].check_id` is unpatterned while the fragment's is patterned — align.
- Add `report_schema_version` (and the marketplace version) to the report root; trivial, and it
  lets a judge see which contract a report was built against.
- `affected_surfaces` is free `string[]` — make it an enum of the **citation** surfaces (see §4.1)
  so a specialist cannot name `chatgpt_training` as an affected surface.

---

## 4. Registry corrections

### 4.1 Surface naming is inconsistent

`render_evidence` names `chatgpt_training` and `chatgpt_search` separately (correct), but calls the
ClaudeBot entry `claude_retrieval` — ClaudeBot is Anthropic's **training** bot per the registry's
own `crawler_roles`. Rename to `claude_training`, keep `claude_search` (undocumented, medium), and
decide explicitly whether live-fetch agents (`ChatGPT-User`, `Claude-User`, `Perplexity-User`) are
surfaces a finding can name. Suggested enum for `affected_surfaces`:
`google_ai_overviews_ai_mode`, `bing_copilot`, `chatgpt_search`, `perplexity_retrieval`,
`claude_search`, plus `*_live_fetch` variants if you want them. Training surfaces stay as evidence
only.

### 4.2 Bing `noarchive`/`nocache` entries have no source URL

The registry's own maintenance note says every behaviour must trace to a URL. Add
`https://blogs.bing.com/webmaster/september-2023/Announcing-new-options-for-webmasters-to-control-usage-of-their-content-in-Bing-Chat`
to both entries. Verified wording: NOCACHE → "may be included in Bing Chat answers, with only
URL/Snippet/Title displayed"; NOARCHIVE → "will not be included in Bing Chat answers, not be linked
to in the answers"; both "will still appear in Bing's search results."

### 4.3 `severity_model.md` rule 6 has no severity

"A 5xx on robots.txt is a real crawl-delays condition — evidence-backed finding." At what
severity and confidence, and after how many observations? Two consecutive 5xx across the audit →
`high` / `high`; one → `needs_verification`. Write it down; the access script will otherwise pick.

---

## 5. Hygiene to add to the Phase 7 checklist now

- Every stub body and the README carry a `> **Build status (Phase 0)**` line that references
  `BUILD_PLAN.md`, which is not shipped. Add `grep -rn "Build status\|BUILD_PLAN" skills/ README.md`
  = empty to the checklist.
- No skill declares `allowed-tools` yet (checklist item). Fine for stubs; add with the scripts.
- The README's skill table names `probe_access.py`, `analyze_representation.py`,
  `check_entities.py` — none exist. Fine while marked Phase 0; make sure the Phase 7 README is
  generated from what actually ships.

---

## 6. Corrections to `BUILD_PLAN.md`

1. **Redefine G1 so it can fail.** "`tests/sample_fragment.json` validates against
   `finding_fragment.json`; stub `build_report.py` converts it; the output validates against
   `output_schema.json`; the arithmetic guard passes; all under Python 3.9." Re-run and re-commit
   before Phase 1 is marked done. A gate that can't fail isn't a gate.
2. **Split the playbook.** Catalog (ids, gates, negative controls, default surfaces) → Phase 1.
   Playbook prose (options, owner, effort, acceptance-test templates, forbidden claims) → Phase 5–7.
3. **Phase 3 parallelisation is gated on the catalog**, not only on the schemas.
4. **Delete the "Cross-skill deps / vendored slices" row** if §3.3 is adopted; replace with
   "all network I/O in `collect_snapshot.py`; specialists are snapshot-only readers."
5. Add the stdlib validator decision (§2.4) to the Phase 2 `build_report.py` line.

---

## 7. Suggested order for the fix pass (half a day)

1. `finding_fragment.json`: allow `effort`/`owner`/`acceptance_test`.
2. `check_catalog.json`: ids + category + evidence + severity band + negative control.
3. `excerpts_schema.json`: excerpt files, `passages.json`, `passages_checked.json`.
4. `snapshot_schema.json`: `sitemap`, per-page `headers`, `hreflang` pairs, `external_presence[]`,
   `sitemap_lastmod`; `affected_surfaces` enum in `output_schema.json`.
5. `provider_registry.json`: rename `claude_retrieval`, add the Bing URL, decide live-fetch surfaces.
6. `severity_model.md`: rule 6 severity.
7. Write `tests/sample_fragment.json` + stub `build_report.py` with the vendored validator; run G1
   for real; commit "Phase 1: G1 passed".

Then Phase 2.
